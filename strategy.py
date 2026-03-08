"""
SEPA 策略主逻辑 (对应《股票魔法师》完整流程)

选股流程: 市场环境判断 → 趋势模板 → VCP形态 → 基本面 → 入场信号
入场条件: VCP枢纽点突破 + 放量 + 紧密收盘确认
"""
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

from config import StrategyConfig, MarketRegimeConfig
from trend_template import TrendTemplate
from vcp_detector import VCPDetector
from fundamental import FundamentalFilter
from risk_manager import RiskManager


@dataclass
class Signal:
    """交易信号"""
    code: str
    date: str
    action: str       # buy / sell
    price: float
    reason: str
    rs_rating: float = 0
    pivot_price: float = 0
    shares: int = 0


class MarketRegimeFilter:
    """
    市场环境过滤器 (第9章: 顺势而为)

    通过跟踪大盘指数的「分布日」来判断市场强弱:
    - 分布日 = 指数下跌 > 0.2% 且成交量放大
    - 25个交易日内出现 5+ 个分布日 → 市场转弱，停止买入
    - 连续3天放量上涨 → 确认反弹，恢复买入
    """

    def __init__(self, config: MarketRegimeConfig | None = None):
        self.config = config or MarketRegimeConfig()

    def compute_regime(self, index_df: pd.DataFrame) -> pd.DataFrame:
        """
        给指数数据添加市场状态列。
        返回带 'market_ok' (bool) 列的 DataFrame。
        """
        if index_df.empty or len(index_df) < 30:
            df = index_df.copy()
            df["market_ok"] = True
            return df

        df = index_df.copy()
        df = df.sort_values("date").reset_index(drop=True)

        pct = df["close"].pct_change()
        vol_ma20 = df["volume"].rolling(20).mean()
        volume_up = df["volume"] > vol_ma20

        # 分布日: 下跌 > 阈值 且 放量
        df["distribution_day"] = (pct < -self.config.distribution_drop_pct) & volume_up

        # 25日窗口内分布日计数
        df["dist_count"] = (
            df["distribution_day"]
            .astype(int)
            .rolling(self.config.distribution_window, min_periods=1)
            .sum()
        )

        # 反弹确认: 连续N天上涨 + 放量
        up_vol = (pct > 0) & volume_up
        df["rally_streak"] = self._consecutive_count(up_vol)

        # 市场状态判断
        market_ok = pd.Series(True, index=df.index)
        in_correction = False

        for i in range(len(df)):
            if df["dist_count"].iloc[i] >= self.config.max_distribution_days:
                in_correction = True
            if in_correction and df["rally_streak"].iloc[i] >= self.config.rally_confirmation_days:
                in_correction = False
            market_ok.iloc[i] = not in_correction

        df["market_ok"] = market_ok
        return df

    @staticmethod
    def _consecutive_count(series: pd.Series) -> pd.Series:
        """计算连续 True 的天数"""
        result = pd.Series(0, index=series.index)
        count = 0
        for i in range(len(series)):
            if series.iloc[i]:
                count += 1
            else:
                count = 0
            result.iloc[i] = count
        return result


class SEPAStrategy:
    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()
        self.trend_template = TrendTemplate(self.config.trend)
        self.vcp_detector = VCPDetector(self.config.vcp)
        self.fundamental_filter = FundamentalFilter(self.config.fundamental)
        self.risk_manager = RiskManager(self.config.risk)
        self.market_filter = MarketRegimeFilter(self.config.market)

    # ------------------------------------------------------------------
    # 选股模式：当日一次性筛选
    # ------------------------------------------------------------------

    def screen_stocks(
        self,
        all_data: dict[str, pd.DataFrame],
        financial_df: pd.DataFrame | None = None,
        get_finance_fn=None,
    ) -> list[dict[str, Any]]:
        """
        执行完整的 SEPA 选股流程:
        1. 趋势模板筛选
        2. VCP 形态识别 + 紧密收盘确认
        3. 基本面过滤
        """
        # 步骤 1: 趋势模板
        trend_passed = self.trend_template.screen(all_data)
        print(f"[趋势模板] 通过: {len(trend_passed)} / {len(all_data)} 只")

        if trend_passed.empty:
            return []

        passed_codes = trend_passed["code"].tolist()

        # 步骤 2: VCP 形态检测 + 紧密收盘
        vcp_candidates = []
        for code in passed_codes:
            df = all_data[code]
            vcp_result = self.vcp_detector.detect(df)
            if vcp_result["has_vcp"]:
                tight = self._check_tight_closes(df)
                rs_rating = float(
                    trend_passed.loc[trend_passed["code"] == code, "rs_rating"].iloc[0]
                )
                vcp_candidates.append({
                    "code": code,
                    "rs_rating": rs_rating,
                    "close": float(df["close"].iloc[-1]),
                    "tight_closes": tight,
                    **vcp_result,
                })

        print(f"[VCP形态]  通过: {len(vcp_candidates)} 只")

        if not vcp_candidates:
            return []

        # 步骤 3: 基本面过滤
        if get_finance_fn is not None:
            vcp_codes = [c["code"] for c in vcp_candidates]
            fundamental_passed = self.fundamental_filter.screen(vcp_codes, get_finance_fn)
            vcp_candidates = [c for c in vcp_candidates if c["code"] in fundamental_passed]
            print(f"[基本面]   通过: {len(vcp_candidates)} 只")
        elif financial_df is not None and not financial_df.empty:
            vcp_codes = [c["code"] for c in vcp_candidates]
            quick_passed = self.fundamental_filter.quick_filter(financial_df, vcp_codes)
            vcp_candidates = [c for c in vcp_candidates if c["code"] in quick_passed]
            print(f"[基本面快筛] 通过: {len(vcp_candidates)} 只")

        # 排序: 有紧密收盘的优先，然后按 RS Rating
        vcp_candidates.sort(key=lambda x: (x["tight_closes"], x["rs_rating"]), reverse=True)
        return vcp_candidates

    # ------------------------------------------------------------------
    # 回测模式：逐日生成信号
    # ------------------------------------------------------------------

    def generate_signals_for_backtest(
        self,
        all_data: dict[str, pd.DataFrame],
        index_df: pd.DataFrame | None = None,
    ) -> tuple[dict[str, pd.DataFrame], pd.DataFrame | None]:
        """
        为回测准备数据:
        1. 对每只股票计算趋势模板、VCP信号、紧密收盘
        2. 对大盘指数计算市场环境状态
        返回 (signal_data, market_regime_df)
        """
        rs_ratings = self.trend_template._compute_rs_ratings(all_data)

        result = {}
        items = [(c, d) for c, d in all_data.items() if len(d) >= 300]
        for code, df in tqdm(items, desc="生成信号"):
            enriched = self._enrich_with_indicators(df)
            enriched["rs_rating"] = rs_ratings.get(code, 0)

            # 确保 code 列存在（回测涨跌停判断需要）
            if "code" not in enriched.columns:
                enriched["code"] = code

            # VCP 扫描（已优化：仅在 trend_pass=True 的日期检测）
            enriched = self.vcp_detector.scan_signals(enriched)

            # 紧密收盘标记
            enriched["tight_closes"] = self._compute_tight_closes_series(enriched)

            # 综合买入信号: 趋势通过 + VCP突破
            # 紧密收盘作为增强信号（提高优先级），不作为硬性条件
            enriched["buy_signal"] = (
                enriched["trend_pass"]
                & enriched["vcp_signal"]
            )

            result[code] = enriched

        # 市场环境
        market_df = None
        if index_df is not None and not index_df.empty:
            market_df = self.market_filter.compute_regime(index_df)

        return result, market_df

    # ------------------------------------------------------------------
    # 紧密收盘确认 (第8章: 买入确认)
    # ------------------------------------------------------------------

    def _check_tight_closes(self, df: pd.DataFrame) -> bool:
        """
        检查突破前是否有紧密收盘:
        近 N 天的收盘价在一个很窄的范围内（<1.5%），
        说明供需达到平衡，突破时更有效。
        """
        n = self.config.vcp.tight_close_days
        if len(df) < n + 1:
            return False

        recent_closes = df["close"].iloc[-(n + 1):-1].values
        if len(recent_closes) < n:
            return False

        high_close = np.max(recent_closes)
        low_close = np.min(recent_closes)
        if low_close <= 0:
            return False

        spread = (high_close - low_close) / low_close
        return spread <= self.config.vcp.tight_close_range

    def _compute_tight_closes_series(self, df: pd.DataFrame) -> pd.Series:
        """向量化计算每日的紧密收盘标记"""
        n = self.config.vcp.tight_close_days
        result = pd.Series(False, index=df.index)

        if len(df) < n + 1:
            return result

        close = df["close"]
        rolling_max = close.shift(1).rolling(n).max()
        rolling_min = close.shift(1).rolling(n).min()
        spread = (rolling_max - rolling_min) / rolling_min

        result = spread <= self.config.vcp.tight_close_range
        result = result.fillna(False)
        return result

    # ------------------------------------------------------------------
    # 指标增强
    # ------------------------------------------------------------------

    def _enrich_with_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加均线、趋势判断和辅助指标"""
        df = df.copy()
        cfg = self.config.trend

        df["ma50"] = df["close"].rolling(cfg.ma_short).mean()
        df["ma150"] = df["close"].rolling(cfg.ma_mid).mean()
        df["ma200"] = df["close"].rolling(cfg.ma_long).mean()
        df["ma200_shift"] = df["ma200"].shift(cfg.ma_long_uptrend_days)

        n = cfg.trading_days_per_year
        df["week52_low"] = df["low"].rolling(n).min()
        df["week52_high"] = df["high"].rolling(n).max()

        # 50日均量(用于放量判断和高潮顶检测)
        df["vol_ma50"] = df["volume"].rolling(50).mean()

        # 20日平均振幅(用于高潮顶检测)
        df["spread_ma20"] = (df["high"] - df["low"]).rolling(20).mean()

        # 趋势模板8大条件逐日判断
        df["trend_pass"] = (
            (df["close"] > df["ma150"])
            & (df["close"] > df["ma200"])
            & (df["ma150"] > df["ma200"])
            & (df["ma200"] > df["ma200_shift"])
            & (df["ma50"] > df["ma150"])
            & (df["ma50"] > df["ma200"])
            & (df["close"] > df["ma50"])
            & (df["close"] > df["week52_low"] * cfg.above_52w_low_pct)
            & (df["close"] >= df["week52_high"] * cfg.within_52w_high_pct)
        )

        return df
