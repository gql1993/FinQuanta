"""
基本面过滤模块
基于 Minervini 的基本面标准，筛选 EPS 增长、营收增长、ROE 等指标合格的股票。
"""
import pandas as pd
import numpy as np

from config import FundamentalConfig


class FundamentalFilter:
    def __init__(self, config: FundamentalConfig | None = None):
        self.config = config or FundamentalConfig()

    # ------------------------------------------------------------------
    # 基于实时行情表的快速过滤
    # ------------------------------------------------------------------

    def quick_filter(
        self, financial_df: pd.DataFrame, stock_codes: list[str]
    ) -> list[str]:
        """
        使用市场概览数据做粗筛（PE > 0 表示盈利）。
        当无法获取详细财报时使用此方法。
        """
        if financial_df.empty:
            return stock_codes

        df = financial_df[financial_df["code"].isin(stock_codes)].copy()

        if "pe_dynamic" in df.columns:
            df = df[pd.to_numeric(df["pe_dynamic"], errors="coerce") > 0]

        return df["code"].tolist()

    # ------------------------------------------------------------------
    # 详细财报筛选
    # ------------------------------------------------------------------

    def check_stock(self, finance_df: pd.DataFrame) -> dict:
        """
        检查单只股票的财务数据是否满足基本面条件。
        finance_df: 来自 akshare 的财务摘要数据

        返回: {"passed": bool, "details": {...}}
        """
        if finance_df.empty or len(finance_df) < 2:
            return {"passed": False, "details": {"reason": "数据不足"}}

        details = {}

        # 尝试解析关键财务字段
        eps_growth_q = self._parse_growth(finance_df, "基本每股收益")
        revenue_growth = self._parse_growth(finance_df, "营业总收入")
        roe = self._parse_latest(finance_df, "净资产收益率")
        profit_margin = self._parse_latest(finance_df, "销售净利率")

        # 检查各项条件
        checks = []

        if eps_growth_q is not None:
            details["eps_growth_quarterly"] = round(eps_growth_q, 4)
            checks.append(eps_growth_q >= self.config.min_quarterly_eps_growth)
        else:
            details["eps_growth_quarterly"] = None

        if revenue_growth is not None:
            details["revenue_growth"] = round(revenue_growth, 4)
            checks.append(revenue_growth >= self.config.min_revenue_growth)
        else:
            details["revenue_growth"] = None

        if roe is not None:
            details["roe"] = round(roe, 4)
            checks.append(roe >= self.config.min_roe)
        else:
            details["roe"] = None

        if profit_margin is not None:
            details["profit_margin"] = round(profit_margin, 4)
            checks.append(profit_margin >= self.config.min_profit_margin)
        else:
            details["profit_margin"] = None

        # 如果数据充足则要求全部通过，否则宽容处理
        if not checks:
            passed = False
        elif len(checks) >= 3:
            passed = all(checks)
        else:
            passed = all(checks)

        details["passed"] = passed
        return {"passed": passed, "details": details}

    # ------------------------------------------------------------------
    # 批量筛选
    # ------------------------------------------------------------------

    def screen(
        self,
        stock_codes: list[str],
        get_finance_fn,
    ) -> list[str]:
        """
        批量检查基本面，返回通过的股票代码列表。
        get_finance_fn: callable(code) -> pd.DataFrame
        """
        passed = []
        for code in stock_codes:
            try:
                finance_df = get_finance_fn(code)
                result = self.check_stock(finance_df)
                if result["passed"]:
                    passed.append(code)
            except Exception:
                continue
        return passed

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_growth(df: pd.DataFrame, col_keyword: str) -> float | None:
        """从财务摘要中解析同比增长率"""
        matching = [c for c in df.columns if col_keyword in c]
        if not matching:
            return None

        col = matching[0]
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(values) < 2:
            return None

        current = values.iloc[0]
        previous = values.iloc[1]
        if previous == 0 or pd.isna(previous):
            return None
        return (current - previous) / abs(previous)

    @staticmethod
    def _parse_latest(df: pd.DataFrame, col_keyword: str) -> float | None:
        """从财务摘要中解析最新值"""
        matching = [c for c in df.columns if col_keyword in c]
        if not matching:
            return None

        col = matching[0]
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if values.empty:
            return None
        val = values.iloc[0]
        # 如果是百分比形式（如 15.3），转为小数
        if abs(val) > 1:
            val = val / 100.0
        return float(val)
