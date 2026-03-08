"""
A股数据获取模块
使用 akshare 获取股票列表、日线行情、基本面数据，并缓存到本地。
"""
import os
import time
import json
import sys
import logging
import urllib.request
from datetime import datetime, timedelta
from functools import wraps

import akshare as ak
import pandas as pd
from tqdm import tqdm

from config import DataConfig

logger = logging.getLogger(__name__)

_AK_TIMEOUT = 15
_AK_MAX_RETRIES = 2
_AK_RETRY_DELAY = 1.5


def _ak_retry(func):
    """对 Akshare 调用自动重试（含超时检测）的装饰器。"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        import signal as _signal
        last_exc = None
        for attempt in range(_AK_MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                logger.warning("ak_retry: %s attempt %d failed: %s", func.__name__, attempt + 1, e)
                if attempt < _AK_MAX_RETRIES:
                    time.sleep(_AK_RETRY_DELAY * (attempt + 1))
        raise last_exc
    return wrapper


@_ak_retry
def _ak_stock_list():
    return ak.stock_zh_a_spot_em()


@_ak_retry
def _ak_daily_hist(symbol, start_date, end_date):
    return ak.stock_zh_a_hist(symbol=symbol, period="daily",
                              start_date=start_date, end_date=end_date, adjust="qfq")


@_ak_retry
def _ak_financial_data():
    return ak.stock_zh_a_spot_em()


@_ak_retry
def _ak_index_daily(symbol):
    return ak.stock_zh_index_daily_em(symbol=symbol)


@_ak_retry
def _ak_financial_report(code):
    return ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")


class DataFetcher:
    def __init__(self, config: DataConfig | None = None):
        self.config = config or DataConfig()
        os.makedirs(self.config.cache_dir, exist_ok=True)

    def _log_source_hit(self, data_type: str, source: str, detail: str = "") -> None:
        path = os.path.join(self.config.cache_dir, "data_source_hits.log")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} | {data_type:<8} | {source:<10} | {detail}\n"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 股票列表
    # ------------------------------------------------------------------

    def get_stock_list(self, force_refresh: bool = False) -> pd.DataFrame:
        """获取全部 A 股列表，排除 ST 和次新股"""
        cache_path = os.path.join(self.config.cache_dir, "stock_list.csv")
        if not force_refresh and self._cache_valid(cache_path, hours=24):
            return pd.read_csv(cache_path, dtype={"code": str})

        try:
            df = _ak_stock_list()
            df = df.rename(columns={"代码": "code", "名称": "name"})
            df = df[["code", "name"]]
        except Exception:
            # 网络/代理异常时回退旧缓存，避免页面直接报错中断。
            if os.path.exists(cache_path):
                try:
                    return pd.read_csv(cache_path, dtype={"code": str})
                except Exception:
                    pass
            return pd.DataFrame(columns=["code", "name"])

        if self.config.exclude_st:
            df = df[~df["name"].str.contains(r"ST|\*ST", na=False)]

        # 只保留沪深主板、创业板、科创板
        df = df[df["code"].str.match(r"^(00|30|60|68)")]

        df.to_csv(cache_path, index=False)
        return df

    # ------------------------------------------------------------------
    # 日线行情
    # ------------------------------------------------------------------

    def get_daily_data(self, code: str, force_refresh: bool = False) -> pd.DataFrame:
        """获取单只股票日线数据"""
        cache_path = os.path.join(self.config.cache_dir, f"daily_{code}.csv")
        if not force_refresh and self._cache_valid(cache_path, hours=12):
            df = pd.read_csv(cache_path, parse_dates=["date"])
            self._log_source_hit("daily", "cache", code)
            return df

        source_tag = "ak"
        df = pd.DataFrame()
        try:
            df = _ak_daily_hist(code, self.config.start_date, self.config.end_date)
        except Exception:
            df = pd.DataFrame()

        # ak 返回空表也继续走后备链路，避免“空返回但不回退”。
        if df is None or df.empty:
            source_tag = "tencent"
            df = self._get_daily_data_tencent(code)
        if df is None or df.empty:
            source_tag = "tushare"
            df = self._get_daily_data_tushare(code)
        if df is None or df.empty:
            if os.path.exists(cache_path):
                try:
                    cached = pd.read_csv(cache_path, parse_dates=["date"])
                    self._log_source_hit("daily", "cache_fallback", code)
                    return cached
                except Exception:
                    pass
            self._log_source_hit("daily", "failed", code)
            return pd.DataFrame()

        if source_tag == "ak":
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnover",
            })
        else:
            for col in ["amount", "amplitude", "pct_change", "change", "turnover"]:
                if col not in df.columns:
                    df[col] = 0

        df["date"] = pd.to_datetime(df["date"])
        df["code"] = code
        df = df.sort_values("date").reset_index(drop=True)

        df.to_csv(cache_path, index=False)
        self._log_source_hit("daily", source_tag, code)
        return df

    def _get_daily_data_tencent(self, code: str) -> pd.DataFrame:
        """腾讯 K 线兜底（qfqday）。"""
        if not code.isdigit() or len(code) != 6:
            return pd.DataFrame()
        prefix = "sh" if code.startswith("6") else "sz"
        symbol = f"{prefix}{code}"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,600,qfq"
        try:
            req = urllib.request.Request(url, headers={"Referer": "https://gu.qq.com/"})
            text = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
            obj = json.loads(text)
            data = obj.get("data", {}).get(symbol, {})
            rows = data.get("qfqday") or data.get("day") or []
            if not rows:
                return pd.DataFrame()
            recs = []
            for r in rows:
                if len(r) < 6:
                    continue
                recs.append({
                    "date": r[0],
                    "open": float(r[1]),
                    "close": float(r[2]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "volume": float(r[5]),
                })
            return pd.DataFrame(recs)
        except Exception:
            return pd.DataFrame()

    def _get_daily_data_tushare(self, code: str) -> pd.DataFrame:
        """Tushare Pro 日线兜底（需要环境变量 TUSHARE_TOKEN）。"""
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if not token:
            return pd.DataFrame()
        try:
            import tushare as ts
        except Exception:
            return pd.DataFrame()

        try:
            ts.set_token(token)
            pro = ts.pro_api()
            ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
            df = pro.daily(
                ts_code=ts_code,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
            )
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={
                "trade_date": "date",
                "pct_chg": "pct_change",
                "vol": "volume",
            })
            # Tushare vol 单位是“手”，统一转为“股”近似对齐。
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0) * 100
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
            df["open"] = pd.to_numeric(df["open"], errors="coerce").fillna(0)
            df["high"] = pd.to_numeric(df["high"], errors="coerce").fillna(0)
            df["low"] = pd.to_numeric(df["low"], errors="coerce").fillna(0)
            df["close"] = pd.to_numeric(df["close"], errors="coerce").fillna(0)
            df["change"] = pd.to_numeric(df.get("change", 0), errors="coerce").fillna(0)
            df["pct_change"] = pd.to_numeric(df.get("pct_change", 0), errors="coerce").fillna(0)
            return df[["date", "open", "close", "high", "low", "volume", "amount", "pct_change", "change"]]
        except Exception:
            return pd.DataFrame()

    def get_all_daily_data(
        self, stock_list: pd.DataFrame, force_refresh: bool = False
    ) -> dict[str, pd.DataFrame]:
        """批量获取日线数据"""
        result = {}
        codes = stock_list["code"].tolist()
        iterator = codes
        # 某些 Streamlit/Windows 终端上下文里 tqdm 可能抛 OSError(22)。
        use_tqdm = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
        if use_tqdm:
            try:
                iterator = tqdm(codes, desc="下载日线数据")
            except Exception:
                iterator = codes

        for code in iterator:
            df = self.get_daily_data(code, force_refresh=force_refresh)
            if not df.empty and len(df) >= self.config.min_listing_days:
                result[code] = df
            # 仅在强制刷新（走网络）时限速；缓存命中时不额外等待。
            if force_refresh:
                time.sleep(0.05)
        return result

    # ------------------------------------------------------------------
    # 基本面数据
    # ------------------------------------------------------------------

    def get_financial_data(self, force_refresh: bool = False) -> pd.DataFrame:
        """获取 A 股基本面数据（市盈率、ROE 等）"""
        cache_path = os.path.join(self.config.cache_dir, "financial.csv")
        if not force_refresh and self._cache_valid(cache_path, hours=24):
            return pd.read_csv(cache_path, dtype={"code": str})

        try:
            df = _ak_financial_data()
            df = df.rename(columns={
                "代码": "code",
                "名称": "name",
                "市盈率-动态": "pe_dynamic",
                "市净率": "pb",
                "总市值": "total_mv",
                "流通市值": "circ_mv",
            })
            cols_keep = ["code", "name", "pe_dynamic", "pb", "total_mv", "circ_mv"]
            cols_keep = [c for c in cols_keep if c in df.columns]
            df = df[cols_keep]
            df.to_csv(cache_path, index=False)
            return df
        except Exception:
            if os.path.exists(cache_path):
                try:
                    return pd.read_csv(cache_path, dtype={"code": str})
                except Exception:
                    pass
            return pd.DataFrame()

    def get_stock_financial_report(self, code: str) -> pd.DataFrame:
        """获取个股财务指标（用于基本面过滤）"""
        cache_path = os.path.join(self.config.cache_dir, f"finance_{code}.csv")
        if self._cache_valid(cache_path, hours=72):
            return pd.read_csv(cache_path)

        try:
            df = _ak_financial_report(code)
            if df is not None and not df.empty:
                df.to_csv(cache_path, index=False)
                return df
        except Exception:
            pass
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 基准指数
    # ------------------------------------------------------------------

    def get_index_data(
        self, symbol: str = "000300", name: str = "沪深300",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """获取基准指数日线数据"""
        cache_path = os.path.join(self.config.cache_dir, f"index_{symbol}.csv")
        if not force_refresh and self._cache_valid(cache_path, hours=12):
            return pd.read_csv(cache_path, parse_dates=["date"])

        source_tag = "ak"
        try:
            df = _ak_index_daily(f"sh{symbol}")
            df = df.rename(columns={
                "date": "date",
                "open": "open",
                "close": "close",
                "high": "high",
                "low": "low",
                "volume": "volume",
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            df.to_csv(cache_path, index=False)
            self._log_source_hit("index", source_tag, symbol)
            return df
        except Exception:
            source_tag = "tencent"

        # 回退：腾讯指数K线
        try:
            t_symbol = f"sh{symbol}"
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={t_symbol},day,,,600,qfq"
            req = urllib.request.Request(url, headers={"Referer": "https://gu.qq.com/"})
            text = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
            obj = json.loads(text)
            data = obj.get("data", {}).get(t_symbol, {})
            rows = data.get("qfqday") or data.get("day") or []
            if rows:
                recs = []
                for r in rows:
                    if len(r) < 6:
                        continue
                    recs.append({
                        "date": r[0],
                        "open": float(r[1]),
                        "close": float(r[2]),
                        "high": float(r[3]),
                        "low": float(r[4]),
                        "volume": float(r[5]),
                    })
                if recs:
                    df = pd.DataFrame(recs)
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date").reset_index(drop=True)
                    df.to_csv(cache_path, index=False)
                    self._log_source_hit("index", source_tag, symbol)
                    return df
        except Exception:
            pass

        # 末级回退：旧缓存
        if os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path, parse_dates=["date"])
                self._log_source_hit("index", "cache_fallback", symbol)
                return df
            except Exception:
                pass
        self._log_source_hit("index", "failed", symbol)
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_valid(path: str, hours: int = 24) -> bool:
        """检查缓存文件是否存在且在有效期内"""
        if not os.path.exists(path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        return datetime.now() - mtime < timedelta(hours=hours)
