"""
多策略量化交易平台 - 主入口
含 SEPA / CAN SLIM / 海龟 / 价值等独立策略体系
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="FinQuanta — AI 量化交易平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.components import CUSTOM_CSS

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---- Sidebar ----
with st.sidebar:
    st.title("📈 多策略量化平台")
    st.caption("趋势 / 价值 / 波段 多策略独立验证")
    st.divider()

    st.markdown("#### AI 助手")
    _ai_p = st.session_state.get("ai_provider_sel", "DeepSeek")
    _ai_m = st.session_state.get("ai_model_sel", "deepseek-chat")
    st.caption(f"当前: {_ai_p} / {_ai_m}")
    st.page_link("pages/5_AI助手.py", label="配置 AI 模型 →", icon="🤖")

    st.divider()
    st.markdown("#### 📤 微信推送")
    with st.expander("微信推送设置（Server酱）", expanded=False):
        from signal_push import get_push_config, save_push_config, push_signal
        _pcfg = get_push_config()

        st.caption("通过 Server酱 将突破信号推送到你的微信。")
        _sc_key = st.text_input(
            "Server酱 SendKey",
            value=_pcfg.get("serverchan_key", ""),
            type="password",
            placeholder="SCTxxxxxxxxxxxxx",
            key="push_cfg_sc_key",
        )
        st.caption("3 步获取：① 打开 [sct.ftqq.com](https://sct.ftqq.com/) ② 微信扫码登录 ③ 复制 SendKey")

        sc1, sc2 = st.columns(2)
        if sc1.button("💾 保存", key="push_cfg_save", width="stretch"):
            new_cfg = dict(_pcfg)
            new_cfg["serverchan_key"] = _sc_key.strip()
            if save_push_config(new_cfg):
                st.success("SendKey 已保存！")
            else:
                st.error("保存失败。")

        if sc2.button("🔔 测试推送", key="push_cfg_test", width="stretch"):
            test_result = push_signal(
                "测试推送", "这是一条来自量化交易平台的测试消息。",
                channels=["serverchan"],
            )
            if test_result.get("serverchan"):
                st.success("微信推送成功，请查看微信！")
            elif "serverchan" in test_result:
                st.error("推送失败，请检查 SendKey 是否正确。")
            else:
                st.info("请先填写 SendKey 并保存。")

    st.divider()
    st.markdown(
        "**功能导航**\n"
        "- 📡 选股雷达\n"
        "- 💼 模拟仓\n"
        "- 📊 回测分析\n"
        "- 🧭 对比总览\n"
        "- 📉 个股分析\n"
        "- 🤖 AI 助手"
    )

# ---- Main Page: Dashboard ----
st.title("多策略量化交易平台")
st.markdown("##### 策略分层：海外大师 / 国内游资 / 国内私募 / 国内机构，分离回测与横向验证")

# Market Status
try:
    from services.stock_service import get_market_regime
    regime = get_market_regime()
    market_ok = regime["market_ok"]
    dist_count = regime["dist_count"]

    if market_ok:
        st.success(f"🟢 市场环境健康 — 分布日: {dist_count}/5，适合执行买入策略")
    else:
        st.warning(f"🔴 市场环境偏弱 — 分布日: {dist_count}/5，建议减仓或暂停买入")
except Exception as e:
    st.info("市场数据加载中...")

# Portfolio Quick View
col1, col2, col3, col4 = st.columns(4)
try:
    from services.portfolio_service import get_portfolio, get_portfolio_summary
    state = get_portfolio()
    if state.positions:
        summary = get_portfolio_summary(state)
        col1.metric("总资产", f"¥{summary['total_equity']:,.0f}",
                     f"{summary['total_return']:+.2f}%")
        col2.metric("持仓市值", f"¥{summary['position_value']:,.0f}",
                     f"仓位 {summary['position_ratio']:.0f}%")
        col3.metric("可用现金", f"¥{summary['cash']:,.0f}")
        col4.metric("持仓数", f"{summary['num_positions']} 只",
                     f"浮动盈亏 ¥{summary['unrealized_pnl']:+,.0f}")
    else:
        col1.metric("总资产", "¥1,000,000")
        col2.metric("持仓市值", "¥0")
        col3.metric("可用现金", "¥1,000,000")
        col4.metric("持仓数", "0 只")
except Exception:
    col1.metric("总资产", "-")
    col2.metric("持仓市值", "-")
    col3.metric("可用现金", "-")
    col4.metric("持仓数", "-")

st.divider()

# Feature Cards
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("### 📡 选股雷达")
    st.markdown("趋势模板 + VCP 形态 + RS 评级\n\n自动扫描全市场，发现突破候选")
    st.page_link("pages/1_选股雷达.py", label="进入选股 →", icon="📡")

with c2:
    st.markdown("### 💼 模拟仓管理")
    st.markdown("买入/卖出 + 风控检查 + 盈亏跟踪\n\n100 万模拟资金，实战验证策略")
    st.page_link("pages/2_模拟仓.py", label="管理持仓 →", icon="💼")

with c3:
    st.markdown("### 📊 回测分析")
    st.markdown("历史数据回测 + 资金曲线 + 风险指标\n\n验证策略在不同市场环境下的表现")
    st.page_link("pages/3_回测分析.py", label="运行回测 →", icon="📊")

c4, c5, c6 = st.columns(3)
with c4:
    st.markdown("### 📉 个股分析")
    st.markdown("交互式 K 线 + VCP 检测 + 趋势判断\n\n深度分析个股技术形态和买入时机")
    st.page_link("pages/4_个股分析.py", label="分析个股 →", icon="📉")

with c5:
    st.markdown("### 🤖 AI 助手")
    st.markdown("自然语言交互 + 智能选股问答\n\n\"帮我选股\"、\"分析603881\"、\"买入2000股\"")
    st.page_link("pages/5_AI助手.py", label="对话 AI →", icon="🤖")

with c6:
    st.markdown("### 🧭 对比总览")
    st.markdown(
        "选股对比 + 回测对比 + 准确率验证\n\n"
        "同页联动看策略覆盖、收益回撤与实践可信度"
    )
    st.page_link("pages/6_对比总览.py", label="进入总览 →", icon="🧭")
