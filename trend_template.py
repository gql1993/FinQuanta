"""
Minervini 趋势模板筛选
实现 Stage 2 上升趋势的 8 大条件 + 相对强度 (RS) 评级计算。
"""
import numpy as np
import pandas as pd

from config import TrendTemplateConfig


class TrendTemplate:
    def __init__(self, config: TrendTemplateConfig | None = None):
        self.config = config or TrendTemplateConfig()

    # ------------------------------------------------------------------
    # 单只股票检测
    # ------------------------------------------------------------------

    def check(self, df: pd.DataFrame) -> dict:
        """
        对单只股票 DataFrame 检查趋势模板 8 大条件。
        返回 dict: {condition_1: bool, ..., condition_8: bool, passed: bool}
        """
        if len(df) < self.config.ma_long + self.config.ma_long_uptrend_days:
            return self._fail_result()

        close = df["close"].values
        low = df["low"].values
        high = df["high"].values

        ma50 = self._sma(close, self.config.ma_short)
        ma150 = self._sma(close, self.config.ma_mid)
        ma200 = self._sma(close, self.config.ma_long)

        latest_close = close[-1]
        latest_ma50 = ma50[-1]
        latest_ma150 = ma150[-1]
        latest_ma200 = ma200[-1]

        n_year = self.config.trading_days_per_year
        week52_low = float(np.min(low[-n_year:]))
        week52_high = float(np.max(high[-n_year:]))

        # 条件 1: 股价 > 150日均线 且 > 200日均线
        c1 = latest_close > latest_ma150 and latest_close > latest_ma200

        # 条件 2: 150日均线 > 200日均线
        c2 = latest_ma150 > latest_ma200

        # 条件 3: 200日均线至少上升 1 个月
        c3 = self._ma_rising(ma200, self.config.ma_long_uptrend_days)

        # 条件 4: 50日均线 > 150日均线 且 > 200日均线
        c4 = latest_ma50 > latest_ma150 and latest_ma50 > latest_ma200

        # 条件 5: 股价 > 50日均线
        c5 = latest_close > latest_ma50

        # 条件 6: 股价 > 52周最低价 × 125%
        c6 = latest_close > week52_low * self.config.above_52w_low_pct

        # 条件 7: 股价 >= 52周最高价 × 75%
        c7 = latest_close >= week52_high * self.config.within_52w_high_pct

        # 条件 8 需要全市场 RS 数据，这里先置 True，由 batch 方法补充
        c8 = True

        passed = all([c1, c2, c3, c4, c5, c6, c7, c8])

        return {
            "condition_1_above_ma150_200": c1,
            "condition_2_ma150_gt_ma200": c2,
            "condition_3_ma200_rising": c3,
            "condition_4_ma50_gt_ma150_200": c4,
            "condition_5_above_ma50": c5,
            "condition_6_above_52w_low_25pct": c6,
            "condition_7_within_52w_high_25pct": c7,
            "condition_8_rs_rating": c8,
            "passed": passed,
            "ma50": latest_ma50,
            "ma150": latest_ma150,
            "ma200": latest_ma200,
            "week52_low": week52_low,
            "week52_high": week52_high,
        }

    # ------------------------------------------------------------------
    # 批量筛选 (含 RS Rating)
    # ------------------------------------------------------------------

    def screen(
        self, all_data: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        对全市场股票做趋势模板筛选，包含 RS Rating 计算。
        返回通过筛选的股票 DataFrame。
        """
        # 第一步: 计算全市场 RS Rating
        rs_scores = self._compute_rs_ratings(all_data)

        results = []
        for code, df in all_data.items():
            res = self.check(df)
            rs = rs_scores.get(code, 0)
            res["condition_8_rs_rating"] = rs >= self.config.rs_rating_min
            res["passed"] = res["passed"] and res["condition_8_rs_rating"]
            res["code"] = code
            res["rs_rating"] = rs
            res["close"] = float(df["close"].iloc[-1])
            results.append(res)

        result_df = pd.DataFrame(results)
        passed_df = result_df[result_df["passed"]].copy()
        passed_df = passed_df.sort_values("rs_rating", ascending=False)
        return passed_df.reset_index(drop=True)

    # ------------------------------------------------------------------
    # RS Rating 计算
    # ------------------------------------------------------------------

    def _compute_rs_ratings(
        self, all_data: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """
        计算全市场相对强度评级（0-99）。
        方法：6 个月涨幅 40% 权重 + 3 个月涨幅 20% + 1 个月涨幅 20% + 近1周 20%
        然后在全市场中取百分位排名。
        使用前一日收盘价（close[-2]），避免回测中的前视偏差。
        """
        scores = {}
        for code, df in all_data.items():
            if len(df) < 131:
                continue
            close = df["close"].values
            # 使用前一日收盘价，避免当日数据前视。
            current = close[-2]

            m6 = close[-131] if len(close) >= 131 else close[0]
            m3 = close[-66] if len(close) >= 66 else close[0]
            m1 = close[-23] if len(close) >= 23 else close[0]
            w1 = close[-6] if len(close) >= 6 else close[0]

            ret_6m = (current - m6) / m6 if m6 > 0 else 0
            ret_3m = (current - m3) / m3 if m3 > 0 else 0
            ret_1m = (current - m1) / m1 if m1 > 0 else 0
            ret_1w = (current - w1) / w1 if w1 > 0 else 0

            raw_score = ret_6m * 0.4 + ret_3m * 0.2 + ret_1m * 0.2 + ret_1w * 0.2
            scores[code] = raw_score

        if not scores:
            return {}

        all_scores = sorted(scores.values())
        n = len(all_scores)
        ratings = {}
        for code, s in scores.items():
            # 使用 left 和平均排名来处理并列值。
            left = np.searchsorted(all_scores, s, side="left")
            right = np.searchsorted(all_scores, s, side="right")
            avg_rank = (left + right) / 2.0
            ratings[code] = round(avg_rank / n * 99)

        return ratings

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(data: np.ndarray, period: int) -> np.ndarray:
        """简单移动平均"""
        return pd.Series(data).rolling(window=period).mean().values

    @staticmethod
    def _ma_rising(ma: np.ndarray, days: int) -> bool:
        """判断均线在最近 N 天是否整体上升"""
        recent = ma[-days:]
        if np.any(np.isnan(recent)):
            return False
        return float(recent[-1]) > float(recent[0])

    @staticmethod
    def _fail_result() -> dict:
        return {
            f"condition_{i}": False for i in range(1, 9)
        } | {"passed": False}
