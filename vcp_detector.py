"""
VCP（Volatility Contraction Pattern）波动收缩形态识别
基于《股票魔法师》第8章，识别基底构建中波动率逐步收窄、成交量递减的形态。

两种工作模式:
  1. detect() - 单次检测最新数据，用于选股
  2. scan_signals() - 向量化扫描，用于回测（高性能）
"""
import numpy as np
import pandas as pd

from config import VCPConfig


class VCPDetector:
    def __init__(self, config: VCPConfig | None = None):
        self.config = config or VCPConfig()

    # ------------------------------------------------------------------
    # 选股模式: 单次检测
    # ------------------------------------------------------------------

    def detect(self, df: pd.DataFrame) -> dict:
        """检测单只股票当前是否出现 VCP 形态"""
        lookback = self.config.lookback_days
        if len(df) < lookback + 50:
            return self._no_vcp()

        recent = df.iloc[-lookback:].copy().reset_index(drop=True)
        close = recent["close"].values
        high = recent["high"].values
        low = recent["low"].values
        volume = recent["volume"].values

        segment_vols = self._compute_segment_volatilities(high, low)
        if len(segment_vols) < 3:
            return self._no_vcp()

        slope = self._volatility_trend(segment_vols)
        if slope >= 0:
            return self._no_vcp()

        contractions = self._count_contractions(segment_vols)
        if contractions < self.config.min_contractions:
            return self._no_vcp()

        vol_contracting = self._volume_contracting(volume)

        pivot_window = min(self.config.contraction_window, len(close))
        pivot_price = float(np.max(close[-pivot_window:]))

        latest_close = float(df["close"].iloc[-1])
        latest_volume = float(df["volume"].iloc[-1])
        avg_volume_50 = float(df["volume"].iloc[-50:].mean()) if len(df) >= 50 else 1

        tolerance = self.config.pivot_tolerance
        breakout = (
            latest_close >= pivot_price * (1 - tolerance)
            and latest_volume > avg_volume_50 * self.config.breakout_volume_ratio
        )

        return {
            "has_vcp": True,
            "contractions": [round(v, 4) for v in segment_vols],
            "num_contractions": contractions,
            "volume_contracting": vol_contracting,
            "pivot_price": round(pivot_price, 2),
            "breakout_today": breakout,
            "latest_close": latest_close,
            "vol_slope": round(slope, 6),
        }

    # ------------------------------------------------------------------
    # 回测模式: 向量化信号扫描（高性能）
    # ------------------------------------------------------------------

    def scan_signals(self, df: pd.DataFrame, check_interval: int = 1) -> pd.DataFrame:
        """
        向量化 VCP 突破信号检测，用于回测。
        条件:
          1. 波动率收缩: 近 40 天波动率 < 前 40 天波动率 × 0.8
          2. 价格突破: 收盘价 >= 20 日最高收盘价 × (1 - tolerance)
          3. 放量: 成交量 > 50 日均量 × 倍数
          4. (如果存在) trend_pass = True
        """
        df = df.copy()

        lookback = self.config.lookback_days
        half = lookback // 3

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        spread = high - low
        midprice = (high + low) / 2
        midprice = midprice.replace(0, np.nan)
        rel_spread = spread / midprice

        vol_recent = rel_spread.rolling(half, min_periods=half).mean()
        vol_early = rel_spread.shift(half).rolling(half, min_periods=half).mean()

        vol_ratio = vol_recent / vol_early.replace(0, np.nan)
        vol_contraction = vol_ratio < self.config.volume_decline_ratio

        # shift(1) 排除当日，防止回测中前视偏差。
        close_high_20 = close.shift(1).rolling(self.config.contraction_window, min_periods=1).max()
        tolerance = self.config.pivot_tolerance
        near_high = close >= close_high_20 * (1 - tolerance)

        vol_ma50 = volume.shift(1).rolling(50, min_periods=20).mean()
        volume_surge = volume > vol_ma50 * self.config.breakout_volume_ratio

        signal = vol_contraction & near_high & volume_surge

        if "trend_pass" in df.columns:
            signal = signal & df["trend_pass"]

        df["vcp_signal"] = signal.fillna(False)
        return df

    # ------------------------------------------------------------------
    # 核心算法（用于 detect）
    # ------------------------------------------------------------------

    def _compute_segment_volatilities(self, high: np.ndarray, low: np.ndarray) -> list[float]:
        window = self.config.contraction_window
        step = window // 2
        n = len(high)
        if n < window * 2:
            return []

        vols = []
        for start in range(0, n - window + 1, step):
            end = min(start + window, n)
            seg_high = np.max(high[start:end])
            seg_low = np.min(low[start:end])
            mid = (seg_high + seg_low) / 2
            if mid > 0:
                vols.append((seg_high - seg_low) / mid)
        return vols

    def _volatility_trend(self, vols: list[float]) -> float:
        n = len(vols)
        if n < 3:
            return 0.0
        x = np.arange(n, dtype=float)
        y = np.array(vols)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x ** 2) - np.sum(x) ** 2)
        return float(slope)

    def _count_contractions(self, vols: list[float]) -> int:
        if len(vols) < 2:
            return 0
        count = 0
        for i in range(1, len(vols)):
            if vols[i - 1] > 0 and vols[i] / vols[i - 1] <= 0.9:
                count += 1
        return count

    def _volume_contracting(self, volume: np.ndarray) -> bool:
        n = len(volume)
        if n < 20:
            return False
        first_third = np.mean(volume[: n // 3])
        last_third = np.mean(volume[-(n // 3):])
        if first_third == 0:
            return False
        return last_third / first_third <= self.config.volume_decline_ratio

    def _no_vcp(self) -> dict:
        return {
            "has_vcp": False,
            "contractions": [],
            "num_contractions": 0,
            "volume_contracting": False,
            "pivot_price": 0.0,
            "breakout_today": False,
            "latest_close": 0.0,
            "vol_slope": 0.0,
        }
