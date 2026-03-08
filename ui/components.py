"""可复用 UI 组件"""
import streamlit as st


def metric_card(label: str, value: str, delta: str = "", delta_color: str = "normal"):
    """指标卡片"""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def colored_pnl(pnl_pct: float) -> str:
    """盈亏百分比着色"""
    if pnl_pct > 0:
        return f"🟢 +{pnl_pct:.2f}%"
    elif pnl_pct < 0:
        return f"🔴 {pnl_pct:.2f}%"
    return f"⚪ {pnl_pct:.2f}%"


def market_status_badge(is_ok: bool, dist_count: int = 0) -> str:
    """市场状态标签"""
    if is_ok:
        return "🟢 市场健康（适合买入）"
    return f"🔴 市场偏弱（分布日={dist_count}，谨慎操作）"


def trend_check_item(label: str, passed: bool):
    """趋势条件检查项"""
    icon = "✅" if passed else "❌"
    st.markdown(f"{icon} {label}")


CUSTOM_CSS = """
<style>
    .stMetric { border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; }
    .stock-table { font-size: 14px; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    .main .block-container { max-width: 1200px; padding-top: 2rem; }
    section[data-testid="stSidebar"] { width: 280px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 4px 4px 0 0;
        padding: 8px 20px;
    }
</style>
"""
