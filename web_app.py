"""
FinQuanta Web 版 - Streamlit 在线应用。

产品策略上，Web 端优先通过 API 访问平台能力；当前版本仍保留本地模式
兼容回退，便于单机验证和渐进式服务化改造。

启动: streamlit run web_app.py --server.port 8501 --server.address 0.0.0.0
"""
import streamlit as st
import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse
import numpy as np
import time
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_server.config import settings as api_settings
from core.runtime.mode import resolve_runtime_mode_context
from web_ui.desktop_parity import (
    render_arena,
    render_manual_portfolio,
    render_ops_center,
    render_short_term,
)

# 与 PyQt6 桌面端标签顺序一致
DESKTOP_NAV_PAGES = [
    "📈 总览",
    "📡 选股",
    "📉 个股",
    "⚡ 短期选股",
    "💼 手动仓",
    "🤖 AI仓",
    "🏆 策略竞技场",
    "💬 AI助手",
    "🦀 OpenClaw",
    "🛰 运行中心",
    "⚙️ 设置",
]

RUNTIME_CONTEXT = resolve_runtime_mode_context(
    runtime_mode=api_settings.runtime_mode,
    db_backend=api_settings.db_backend,
    api_base=api_settings.api_base,
)

st.set_page_config(
    page_title="FinQuanta — AI 量化交易平台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.session_state.setdefault("ops_registry_token", "")
st.session_state.setdefault("ops_center_cache", {})
st.session_state.setdefault(
    "ops_center_cache_ttl_seconds",
    max(1, int(getattr(api_settings, "web_ops_center_cache_ttl", 5) or 5)),
)

def _db():
    from desktop.data_access import RepoCompatConnection

    return RepoCompatConnection()


def _api_call(method: str, path: str, payload: dict | None = None):
    """
    轻量 API 客户端：优先用于产品化验证。
    默认访问本机 9000 端口，如失败由页面自行回退到本地模块。
    """
    base = st.session_state.get("api_base", "http://127.0.0.1:9000")
    token = st.session_state.get("api_token", "")
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method.upper(), headers=headers)
    host = (urllib.parse.urlparse(base).hostname or "").lower()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if host in {"127.0.0.1", "localhost", "0.0.0.0"} else urllib.request.build_opener()
    with opener.open(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_platform_mode() -> bool:
    return bool(RUNTIME_CONTEXT.is_platform_mode)


def _guard_platform_mode(feature: str, exc: Exception):
    if _is_platform_mode():
        raise RuntimeError(f"{feature} requires API in platform mode: {exc}") from exc


def _get_ops_center_payload_throttled(force_refresh: bool = False):
    now_ts = time.time()
    token = str(st.session_state.get("ops_registry_token", "") or "")
    ttl_seconds = int(st.session_state.get("ops_center_cache_ttl_seconds", 5) or 5)
    cache = st.session_state.get("ops_center_cache", {})
    cached_payload = cache.get("payload") if isinstance(cache, dict) else None
    cache_token = str(cache.get("requested_token", "") or "") if isinstance(cache, dict) else ""
    fetched_at_ts = float(cache.get("fetched_at_ts", 0) or 0) if isinstance(cache, dict) else 0.0
    cache_age = now_ts - fetched_at_ts

    if (
        not force_refresh
        and isinstance(cached_payload, dict)
        and cache_token == token
        and cache_age < ttl_seconds
    ):
        payload = dict(cached_payload)
        payload["client_cache_hit"] = True
        payload["client_cache_age_seconds"] = round(cache_age, 2)
        return payload

    path = "/api/ops/center"
    if token:
        path = f"/api/ops/center?registry_token={urllib.parse.quote(token)}"
    payload = _api_call("GET", path).get("data", {})
    st.session_state["ops_center_cache"] = {
        "requested_token": token,
        "fetched_at_ts": now_ts,
        "payload": payload,
    }
    payload = dict(payload) if isinstance(payload, dict) else {}
    payload["client_cache_hit"] = False
    payload["client_cache_age_seconds"] = 0.0
    return payload


# ─── 导航 ───
with st.sidebar:
    st.markdown("### 🔐 API 登录")
    st.session_state.setdefault("api_base", api_settings.api_base)
    st.session_state.setdefault("api_token", "")
    st.caption(
        f"运行模式: {'平台模式' if RUNTIME_CONTEXT.is_platform_mode else '本地模式'} | "
        f"后端: {RUNTIME_CONTEXT.db_backend}"
    )
    api_base = st.text_input("API 地址", value=st.session_state["api_base"])
    st.session_state["api_base"] = api_base
    user = st.text_input("用户名", value="admin")
    pwd = st.text_input("密码", value="admin123", type="password")
    c1, c2 = st.columns(2)
    if c1.button("登录API", use_container_width=True):
        try:
            resp = _api_call("POST", "/api/auth/login", {"username": user, "password": pwd})
            if resp.get("ok"):
                st.session_state["api_token"] = resp.get("token", "")
                st.success(f"已登录：{resp.get('role','')}")
            else:
                st.error(resp.get("message", "登录失败"))
        except Exception as e:
            if _is_platform_mode():
                st.error(f"平台模式下必须连接 API：{e}")
            else:
                st.warning(f"API 不可用，页面将回退本地模式：{e}")
    if c2.button("查看身份", use_container_width=True):
        try:
            resp = _api_call("GET", "/api/auth/profile")
            st.info(json.dumps(resp.get("data", {}), ensure_ascii=False))
        except Exception as e:
            st.warning(f"未获取到身份：{e}")
    if st.button("检查API依赖", use_container_width=True):
        try:
            dep = _api_call("GET", "/health/deps")
            st.info(json.dumps(dep, ensure_ascii=False))
        except Exception as e:
            st.warning(f"依赖检查失败：{e}")

page = st.sidebar.radio("导航", DESKTOP_NAV_PAGES)

# ═══════════════════════════════════════
# 📈 总览
# ═══════════════════════════════════════
if page == "📈 总览":
    st.title("📈 FinQuanta 总览")

    try:
        try:
            api_resp = _api_call("GET", "/api/snapshot/system")
            snap = api_resp.get("data", {})
        except Exception as e:
            _guard_platform_mode("snapshot overview", e)
            from core.application.snapshot_service import get_system_snapshot
            snap = get_system_snapshot()
        comp = snap.get("ai_portfolios", {})
        market = snap.get("market_state", {})
        risk = snap.get("risk", {})

        st.subheader("五仓对比")
        modes = [
            ("💼 手动仓", "manual_portfolio"),
            ("🟣 完全自主", "full_auto"),
            ("🔵 AI推荐", "auto"),
            ("📌 自定义", "custom"),
            ("⚛️ 量子仓", "quantum"),
        ]

        # 手动仓数据：优先读取统一快照，避免平台模式下本地 DB 依赖。
        manual_data = snap.get("manual_portfolio_raw", {}) if isinstance(snap, dict) else {}
        m_cash = manual_data.get("cash", 1_000_000)
        m_pos = manual_data.get("positions", [])

        cols = st.columns(5)
        for i, (label, mode) in enumerate(modes):
            with cols[i]:
                if mode == "manual_portfolio":
                    m_snap = snap.get("manual_portfolio", {})
                    eq = m_snap.get("equity", m_cash + sum(p.get("entry_price", 0) * p.get("shares", 0) for p in m_pos))
                    ret = m_snap.get("return_pct", (eq - 1_000_000) / 1_000_000 * 100)
                    n = m_snap.get("total_trades", m_snap.get("positions", len(m_pos)))
                else:
                    c = comp.get(mode, {})
                    eq = c.get("equity", 1_000_000)
                    ret = c.get("return_pct", 0)
                    n = c.get("total_trades", 0)
                st.metric(label, f"¥{eq:,.0f}", f"{ret:+.2f}%")
                st.caption(f"交易 {n} 笔")

    except Exception as e:
        st.warning(f"加载对比数据失败: {e}")

    # 市场环境
    st.subheader("市场环境")
    try:
        if market.get("state") == "strong_trend":
            st.success(f"🟢 强趋势市 | {market.get('reason','')}")
        elif market.get("state") == "rotation":
            st.info(f"🔵 轮动市 | {market.get('reason','')}")
        elif market.get("state") == "risk_off":
            st.error(f"🔴 风险收缩市 | {market.get('reason','')}")
        else:
            st.warning(f"🟡 中性市 | {market.get('reason','')}")
        if market.get("sector_top3"):
            st.caption(f"强势板块：{', '.join(market['sector_top3'][:3])}")
    except Exception:
        st.info("市场数据加载中...")

    # 组合风险
    st.subheader("组合风险")
    try:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("VaR(95%)", f"¥{abs(risk.get('var95', 0)):,.0f}")
        c2.metric("VaR(99%)", f"¥{abs(risk.get('var99', 0)):,.0f}")
        c3.metric("最大单股敞口", f"{risk.get('max_exposure', 0):.0%}")
        c4.metric("集中度HHI", f"{risk.get('hhi', 0):.3f}")
    except Exception:
        st.info("风控数据计算中...")

# ═══════════════════════════════════════
# 📡 选股雷达
# ═══════════════════════════════════════
elif page == "📡 选股":
    st.title("📡 选股")

    # 最近扫描结果
    candidates = []
    updated_at = ""
    try:
        api_resp = _api_call("GET", "/api/scan/latest")
        data = api_resp.get("data", {})
        candidates = data.get("items", [])
        updated_at = data.get("updated_at", "")
    except Exception as e:
        _guard_platform_mode("scan latest", e)
        from desktop.scan_store import get_scan_results_meta, resolve_scan_results

        rows, meta, _ = resolve_scan_results()
        candidates = rows
        updated_at = meta.get("written_at", "")

    if candidates:
        st.caption(f"最近扫描时间: {updated_at[:19] if updated_at else '-'} | 共 {len(candidates)} 只候选")

        import pandas as pd
        df = pd.DataFrame(candidates)
        if not df.empty:
            cols_show = [c for c in ["代码", "名称", "板块", "评分", "价格", "建议买入"] if c in df.columns]
            st.dataframe(df[cols_show], use_container_width=True, height=500)
    else:
        st.info("暂无扫描结果，请在桌面端执行扫描或通过 OpenClaw 全流程运行")

    # 手动触发扫描
    if st.button("🔍 运行扫描（SEPA策略）"):
        with st.spinner("扫描中..."):
            try:
                try:
                    _api_call("POST", "/api/scan/run", {"dry_run": False})
                except Exception as e:
                    _guard_platform_mode("scan run", e)
                    from desktop.daemon_scheduler import DaemonScheduler
                    ds = DaemonScheduler()
                    ds._task_scan_stocks()
                st.success("扫描完成，请刷新页面查看结果")
                st.rerun()
            except Exception as e:
                st.error(f"扫描失败: {e}")

# ═══════════════════════════════════════
# 🤖 AI仓
# ═══════════════════════════════════════
elif page == "🤖 AI仓":
    st.title("🤖 AI 自主交易模拟仓")

    try:
        import pandas as pd
        try:
            summary_resp = _api_call("GET", "/api/portfolio/summary")
            positions_resp = _api_call("GET", "/api/portfolio/positions")
            rec_resp = _api_call("GET", "/api/portfolio/recommendations")
            summary_data = summary_resp.get("data", {})
            positions_data = positions_resp.get("data", {})
            rec_data = rec_resp.get("data", {})
            recommendations = rec_data.get("items", [])
            raw_recommendations = rec_data.get("raw_items", [])
            verification_summary = rec_data.get("verification_summary", {})
            guardrail_summary = rec_data.get("guardrail_summary", {})
            execution_plan = rec_data.get("execution_plan", {})
            comp = summary_data.get("ai", {})
            manual_summary = summary_data.get("manual", {})
            ai_states = positions_data.get("ai_states", {})
            manual_positions = positions_data.get("manual_positions", [])
            prices = comp.get("prices", {})
        except Exception as e:
            _guard_platform_mode("portfolio summary", e)
            from desktop.ai_portfolio import get_state, get_comparison
            from core.application.snapshot_service import get_system_snapshot

            comp = get_comparison()
            snap = get_system_snapshot()
            manual_summary = snap.get("manual_portfolio", {})
            ai_states = snap.get("ai_states", {})
            manual_positions = snap.get("manual_portfolio_raw", {}).get("positions", [])
            prices = comp.get("prices", {})
            recommendations = []
            raw_recommendations = []
            verification_summary = {}
            guardrail_summary = {}
            execution_plan = {}

        # 四仓对比表
        rows_data = []
        for mode, label in [("full_auto", "🟣完全自主"), ("auto", "🔵AI推荐"),
                            ("custom", "📌自定义"), ("quantum", "⚛️量子")]:
            c = comp.get(mode, {})
            rows_data.append({
                "仓位": label,
                "总资产": f"¥{c.get('equity', 0):,.0f}",
                "收益率": f"{c.get('return_pct', 0):+.2f}%",
                "平仓胜率": f"{c.get('win_rate', 0):.1f}%",
                "浮盈占比": f"{c.get('open_win_rate', 0):.1f}%",
                "交易数": c.get("total_trades", 0),
                "盈亏": f"¥{c.get('total_pnl', 0):+,.0f}",
            })
        st.dataframe(pd.DataFrame(rows_data), use_container_width=True)
        st.caption("手动仓请见左侧「💼 手动仓」标签。")

        # 持仓明细
        st.subheader("全仓持仓")
        all_pos = []
        mode_labels = {"full_auto": "🟣完全自主", "auto": "🔵AI推荐",
                       "custom": "📌自定义", "quantum": "⚛️量子"}
        merged_states = dict(ai_states)
        for mode in ["full_auto", "auto", "custom", "quantum"]:
            state = merged_states.get(mode, {})
            for p in state.get("positions", []) or []:
                ep = p.get("entry_price", 0)
                px = prices.get(p["code"], ep)
                pnl = (px - ep) / ep * 100 if ep > 0 else 0
                all_pos.append({
                    "仓位": mode_labels.get(mode, mode),
                    "代码": p["code"], "名称": p.get("name", ""),
                    "买入价": f"{ep:.2f}", "现价": f"{px:.2f}",
                    "盈亏%": f"{pnl:+.2f}%",
                    "股数": p.get("shares", 0),
                })
        if all_pos:
            st.dataframe(pd.DataFrame(all_pos), use_container_width=True)
        else:
            st.info("暂无持仓")

        if verification_summary or guardrail_summary:
            st.subheader("验证守门摘要")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("通过候选", verification_summary.get("verified_count", 0))
            c2.metric("存疑候选", verification_summary.get("questionable_count", 0))
            c3.metric("高风险候选", verification_summary.get("rejected_count", 0))
            c4.metric("拦截买入", guardrail_summary.get("blocked_buy_count", 0))
            c5.metric("存疑放行", guardrail_summary.get("annotated_buy_count", 0))

        if execution_plan:
            st.subheader("协调者分流摘要")
            blocked_items = execution_plan.get("blocked", []) or []
            c1, c2, c3 = st.columns(3)
            c1.metric("执行模式", execution_plan.get("mode", "normal"))
            c2.metric("分流拦截", execution_plan.get("blocked_count", len(blocked_items)))
            c3.metric("策略参数数", len(execution_plan.get("policy", {}) or {}))
            if blocked_items:
                block_rows = [
                    {
                        "动作": item.get("action", ""),
                        "代码": item.get("code", ""),
                        "名称": item.get("name", ""),
                        "原因": item.get("reason", ""),
                    }
                    for item in blocked_items
                ]
                st.dataframe(pd.DataFrame(block_rows), use_container_width=True, height=180)

        if raw_recommendations or recommendations:
            st.subheader("原始决策 vs 守门后决策")

            def _fmt_decisions(items: list[dict]) -> str:
                if not items:
                    return "无"
                labels = []
                for item in items[:8]:
                    action = str(item.get("action", "") or "").upper()
                    code = str(item.get("code", "") or "")
                    labels.append(f"{action} {code}".strip())
                if len(items) > 8:
                    labels.append(f"...共{len(items)}条")
                return " / ".join(labels)

            st.code(
                "\n".join(
                    [
                        f"原始决策: {_fmt_decisions(raw_recommendations)}",
                        f"守门后决策: {_fmt_decisions(recommendations)}",
                        f"守门摘要: 拦截买入 {guardrail_summary.get('blocked_buy_count', 0)} 条，"
                        f"存疑放行 {guardrail_summary.get('annotated_buy_count', 0)} 条",
                        f"分流摘要: 模式 {execution_plan.get('mode', 'normal')}，"
                        f"分流拦截 {execution_plan.get('blocked_count', 0)} 条",
                    ]
                )
            )

        if recommendations:
            st.subheader("最新 AI 推荐")
            rec_rows = []
            for item in recommendations[:20]:
                rec_rows.append({
                    "动作": item.get("action", ""),
                    "代码": item.get("code", ""),
                    "名称": item.get("name", ""),
                    "验证": item.get("verification", ""),
                    "验证分": item.get("verification_score", ""),
                    "理由": item.get("reason", ""),
                    "分配": item.get("allocation_pct", ""),
                })
            if rec_rows:
                st.dataframe(pd.DataFrame(rec_rows), use_container_width=True)

    except Exception as e:
        st.error(f"加载失败: {e}")

# ═══════════════════════════════════════
# ⚡ 短期选股
# ═══════════════════════════════════════
elif page == "⚡ 短期选股":
    render_short_term(_api_call, _guard_platform_mode)

# ═══════════════════════════════════════
# 💼 手动仓
# ═══════════════════════════════════════
elif page == "💼 手动仓":
    render_manual_portfolio(_api_call, _guard_platform_mode)

# ═══════════════════════════════════════
# 🏆 策略竞技场
# ═══════════════════════════════════════
elif page == "🏆 策略竞技场":
    render_arena(_api_call, _guard_platform_mode)

# ═══════════════════════════════════════
# 🦀 OpenClaw
# ═══════════════════════════════════════
elif page == "🦀 OpenClaw":
    st.title("🦀 OpenClaw 智能中枢")
    tab1, tab2 = st.tabs(["📡 数据源/快照", "🔄 全流程/学习"])

    with tab1:
        st.subheader("📡 数据源状态")
        try:
            import pandas as pd
            try:
                sources = _api_call("GET", "/api/openclaw/sources").get("data", [])
            except Exception as e:
                _guard_platform_mode("openclaw sources", e)
                from desktop.openclaw_engine import get_data_sources_status
                sources = get_data_sources_status()
            st.dataframe(pd.DataFrame(sources), use_container_width=True)

            try:
                api_resp = _api_call("GET", "/api/snapshot/system")
                snap = api_resp.get("data", {})
            except Exception as e:
                _guard_platform_mode("openclaw snapshot", e)
                from core.application.snapshot_service import get_system_snapshot
                snap = get_system_snapshot()
            c1, c2, c3 = st.columns(3)
            c1.metric("全仓总资产", f"¥{snap.get('totals',{}).get('equity', 0):,.0f}")
            c2.metric("总持仓数", snap.get("totals", {}).get("positions", 0))
            c3.metric("总可用现金", f"¥{snap.get('totals',{}).get('cash', 0):,.0f}")
        except Exception as e:
            st.warning(f"加载失败: {e}")

    with tab2:
        st.subheader("🔄 全流程管线")
        if st.button("🚀 启动全流程", type="primary"):
            with st.spinner("全流程执行中（约1-3分钟）..."):
                try:
                    try:
                        api_resp = _api_call("POST", "/api/openclaw/pipeline/run", {"dry_run": False})
                        result = api_resp.get("data", {})
                    except Exception as e:
                        _guard_platform_mode("openclaw pipeline run", e)
                        from desktop.openclaw_engine import run_full_pipeline
                        result = run_full_pipeline()
                    for s in result.get("steps", []):
                        icon = "✅" if s["status"] == "ok" else "❌"
                        st.write(f"{icon} **{s['name']}**: {s.get('summary', s.get('error', ''))}")
                    st.success("全流程完成！")
                except Exception as e:
                    st.error(f"执行失败: {e}")

        st.subheader("🎯 自主进化")
        if st.button("🧠 立即学习"):
            with st.spinner("学习中..."):
                try:
                    try:
                        api_resp = _api_call("POST", "/api/openclaw/learn/run", {"dry_run": False})
                        result = api_resp.get("data", {})
                        api_w = _api_call("GET", "/api/openclaw/weights")
                        weights = api_w.get("data", {})
                    except Exception as e:
                        _guard_platform_mode("openclaw learn", e)
                        from desktop.openclaw_learner import evaluate_and_learn, get_strategy_weights
                        result = evaluate_and_learn()
                        weights = get_strategy_weights()
                    st.write("**策略权重:**")
                    import pandas as pd
                    w_data = [{"策略": k, "权重": f"{v['weight']:.2f}",
                               "准确率": f"{v['accuracy']:.1f}%",
                               "5日均涨": f"{v['avg_pnl_5d']:+.2f}%"}
                              for k, v in weights.items()]
                    st.dataframe(pd.DataFrame(w_data), use_container_width=True)
                    for l in result.get("learnings", []):
                        st.write(f"• {l['module']}: {l['finding']}")
                except Exception as e:
                    st.error(f"学习失败: {e}")


# ═══════════════════════════════════════
# 📉 个股分析
# ═══════════════════════════════════════
elif page == "📉 个股":
    st.title("📉 个股")

    stock_tab, verify_tab = st.tabs(["📉 行情分析", "✅ 走势验证"])
    with verify_tab:
        try:
            if st.button("🔄 校准走势", key="verify_calibrate_btn"):
                with st.spinner("校准中..."):
                    try:
                        r = _api_call("POST", "/api/verify/calibrate").get("data", {})
                    except Exception as e:
                        _guard_platform_mode("verify calibrate", e)
                        from desktop.trend_verify import calibrate

                        r = calibrate()
                    st.success(f"校准完成: 更新 {r.get('updated', 0)}/{r.get('total', 0)} 条")
            try:
                stats = _api_call("GET", "/api/verify/summary").get("data", {})
                records = _api_call("GET", "/api/verify/records").get("data", [])
            except Exception as e:
                _guard_platform_mode("verify summary", e)
                from desktop.trend_verify import get_records, get_accuracy_stats

                stats = get_accuracy_stats()
                records = get_records(100)
            if stats.get("total", 0) > 0:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总信号", stats["total"])
                c2.metric("准确率", f"{stats['accuracy']:.1f}%")
                c3.metric("1日均涨", f"{stats.get('avg_pnl_1d', 0):+.2f}%")
                c4.metric("5日均涨", f"{stats['avg_pnl_5d']:+.2f}%")
            if records:
                import pandas as pd

                df = pd.DataFrame(records)
                cols = [
                    c
                    for c in [
                        "code",
                        "name",
                        "board",
                        "signal_date",
                        "score",
                        "pnl_1d",
                        "pnl_5d",
                        "correct",
                        "analysis",
                    ]
                    if c in df.columns
                ]
                st.dataframe(df[cols], use_container_width=True, height=400)
        except Exception as e:
            st.error(f"走势验证加载失败: {e}")

    with stock_tab:
        code = st.text_input("股票代码", placeholder="输入6位代码，如 600519", key="stock_code_input")
        if code and len(code) == 6 and code.isdigit():
            try:
                try:
                    summary = _api_call("GET", f"/api/stock/{code}").get("data", {})
                    kline = _api_call("GET", f"/api/stock/{code}/kline").get("data", {})
                    verify_rows = _api_call("GET", f"/api/stock/{code}/verify").get("data", [])
                    items = kline.get("items", [])
                    name = summary.get("name", code)
                except Exception as e:
                    _guard_platform_mode("stock analysis", e)
                    conn = _db()
                    rows = conn.execute(
                        "SELECT date, open, high, low, close, volume FROM daily_kline "
                        "WHERE code=? ORDER BY date DESC LIMIT 120",
                        (code,),
                    ).fetchall()
                    name_row = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,)).fetchone()
                    conn.close()
                    name = name_row[0] if name_row else code
                    rows = rows[::-1]
                    items = [
                        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
                        for r in rows
                    ]
                    verify_rows = []
                    summary = {}

                if items:
                    import pandas as pd
                    df = pd.DataFrame(items)
                    df.columns = ["日期", "开盘", "最高", "最低", "收盘", "成交量"]

                    st.subheader(f"{code} {name}")

                    price = float(summary.get("latest_price", df["收盘"].iloc[-1]))
                    pct = float(summary.get("change_pct", 0))

                    c1, c2, c3 = st.columns(3)
                    c1.metric("最新价", f"¥{price:.2f}", f"{pct:+.2f}%")
                    c2.metric("最高", f"¥{float(summary.get('high_60d', df['最高'].max())):.2f}")
                    c3.metric("最低", f"¥{float(summary.get('low_60d', df['最低'].min())):.2f}")

                    import plotly.graph_objects as go
                    fig = go.Figure(data=[go.Candlestick(
                        x=df["日期"], open=df["开盘"], high=df["最高"],
                        low=df["最低"], close=df["收盘"],
                        increasing_line_color="#ef5350",
                        decreasing_line_color="#26a69a",
                    )])
                    fig.update_layout(
                        template="plotly_dark",
                        height=500,
                        xaxis_rangeslider_visible=True,
                        margin=dict(l=40, r=20, t=20, b=40),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    if verify_rows:
                        st.subheader("该股走势验证记录")
                        vdf = pd.DataFrame(verify_rows)
                        cols = [c for c in ["signal_date", "strategy", "board", "pnl_1d", "pnl_2d", "pnl_5d", "analysis"] if c in vdf.columns]
                        if cols:
                            st.dataframe(vdf[cols], use_container_width=True, height=240)
                else:
                    st.warning("暂无数据，请先刷新 K 线")
            except Exception as e:
                st.error(f"加载失败: {e}")

# ═══════════════════════════════════════
# 🛰 运行中心
# ═══════════════════════════════════════
elif page == "🛰 运行中心":
    st.title("🛰 运行中心")
    force_refresh = st.button("刷新运行中心", use_container_width=False)
    try:
        import pandas as pd
        ops_center = _get_ops_center_payload_throttled(force_refresh=force_refresh)
        registry = ops_center.get("registry", {})
        next_token = str(registry.get("meta", {}).get("change_token", "") or "")
        if next_token:
            st.session_state["ops_registry_token"] = next_token
        tasks = ops_center.get("tasks", [])
        events = ops_center.get("events", [])
        try:
            daemon_status = _api_call("GET", "/api/openclaw/daemon/status").get("data", {})
        except Exception:
            daemon_status = {}
        agents = list(registry.get("agents", []) or [])
        if not agents and int(registry.get("agent_count", 0) or 0) > 0:
            try:
                agents = _api_call("GET", "/api/registry/agents").get("data", [])
            except Exception:
                agents = []
        if daemon_status:
            st.json(daemon_status)
        st.write("**最近任务运行**")
        st.dataframe(pd.DataFrame(tasks), use_container_width=True, height=250)
        st.write("**最近系统事件**")
        st.dataframe(pd.DataFrame(events), use_container_width=True, height=250)
        if agents:
            st.write(f"**智能体注册表**（{len(agents)} 个）")
            st.dataframe(pd.DataFrame(agents), use_container_width=True, height=240)
    except Exception as e:
        st.warning(f"运行中心加载失败: {e}")

# ═══════════════════════════════════════
# 💬 AI助手
# ═══════════════════════════════════════
elif page == "💬 AI助手":
    st.title("💬 AI 助手")

    st.session_state.setdefault("chat_msgs", [])
    st.session_state.setdefault("ai_session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))

    session_loaded = False
    sessions = []
    try:
        sess_resp = _api_call("GET", "/api/assistant/sessions")
        sessions = sess_resp.get("data", {}).get("items", [])
    except Exception:
        sessions = []

    if sessions:
        session_options = {"当前会话": st.session_state["ai_session_id"]}
        for s in sessions:
            label = f"{s.get('last_time', '')[:16]} | {s.get('first_question', '') or s.get('session_id', '')}"
            session_options[label] = s.get("session_id", "")
        selected_label = st.selectbox("历史会话", list(session_options.keys()))
        selected_sid = session_options[selected_label]
        if selected_sid != st.session_state["ai_session_id"]:
            try:
                msg_resp = _api_call("GET", f"/api/assistant/session/{selected_sid}")
                st.session_state["chat_msgs"] = msg_resp.get("data", {}).get("messages", [])
                st.session_state["ai_session_id"] = selected_sid
                session_loaded = True
            except Exception:
                pass

    c1, c2 = st.columns([1, 1])
    if c1.button("新建会话", use_container_width=True):
        st.session_state["ai_session_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state["chat_msgs"] = []
    if c2.button("查看上下文摘要", use_container_width=True):
        try:
            ctx = _api_call("GET", "/api/assistant/context").get("data", {})
            st.info((ctx.get("context_text", "") or "")[:2500])
        except Exception as e:
            st.warning(f"暂未获取到上下文摘要：{e}")

    if not st.session_state["chat_msgs"] and not session_loaded:
        try:
            msg_resp = _api_call("GET", f"/api/assistant/session/{st.session_state['ai_session_id']}")
            st.session_state["chat_msgs"] = msg_resp.get("data", {}).get("messages", [])
        except Exception:
            pass

    for msg in st.session_state.chat_msgs:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("输入问题，如「帮我分析600519」")
    if prompt:
        st.session_state.chat_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("AI 思考中..."):
                try:
                    try:
                        data = _api_call(
                            "POST",
                            "/api/assistant/ask",
                            {"prompt": prompt, "session_id": st.session_state["ai_session_id"]},
                        ).get("data", {})
                        response = data.get("reply", "")
                        st.session_state["ai_session_id"] = data.get("session_id", st.session_state["ai_session_id"])
                    except Exception as e:
                        _guard_platform_mode("assistant ask", e)
                        from desktop.ai_trader import _call_llm
                        response = _call_llm(
                            prompt,
                            system="你是FinQuanta量化交易平台的AI助手，帮助用户分析股票、解读策略、回答量化交易问题。"
                        )
                    st.write(response)
                    st.session_state.chat_msgs.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"AI 调用失败: {e}")

# ═══════════════════════════════════════
# ⚙️ 设置
# ═══════════════════════════════════════
elif page == "⚙️ 设置":
    st.title("⚙️ 设置")

    st.subheader("AI 模型配置")
    try:
        try:
            cfg = _api_call("GET", "/api/settings/ai").get("data", {})
        except Exception as e:
            _guard_platform_mode("settings ai get", e)
            conn = _db()
            r = conn.execute("SELECT value FROM kv_store WHERE key='ai_config'").fetchone()
            conn.close()
            cfg = json.loads(r[0]) if r else {}
    except Exception:
        cfg = {}

    provider = st.selectbox(
        "Provider",
        ["DeepSeek", "OpenAI", "Gemini", "Claude", "自定义"],
        index=max(0, ["DeepSeek", "OpenAI", "Gemini", "Claude", "自定义"].index(cfg.get("provider", "DeepSeek")))
        if cfg.get("provider", "DeepSeek") in ["DeepSeek", "OpenAI", "Gemini", "Claude", "自定义"]
        else 0,
    )
    default_model = cfg.get("model", "deepseek-chat")
    model = st.selectbox(
        "Model",
        ["deepseek-chat", "gpt-4o", "gemini-pro", "claude-3-sonnet", "qwen-max", "moonshot-v1-8k"],
        index=max(
            0,
            ["deepseek-chat", "gpt-4o", "gemini-pro", "claude-3-sonnet", "qwen-max", "moonshot-v1-8k"].index(default_model)
            if default_model in ["deepseek-chat", "gpt-4o", "gemini-pro", "claude-3-sonnet", "qwen-max", "moonshot-v1-8k"]
            else 0,
        ),
    )
    key = st.text_input("API Key", value=cfg.get("api_key", ""), type="password")
    base_url = st.text_input("Base URL", value=cfg.get("base_url", "https://api.deepseek.com/v1"))

    if st.button("💾 保存"):
        try:
            try:
                _api_call(
                    "POST",
                    "/api/settings/ai",
                    {"api_key": key, "base_url": base_url, "model": model, "provider": provider},
                )
            except Exception as e:
                _guard_platform_mode("settings ai save", e)
                conn = _db()
                conn.execute(
                    "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                    (
                        "ai_config",
                        json.dumps({"api_key": key, "base_url": base_url, "model": model, "provider": provider}),
                    ),
                )
                conn.commit()
                conn.close()
            st.success("配置已保存")
        except Exception as e:
            st.error(f"保存失败: {e}")

    st.subheader("推送配置")
    try:
        try:
            pcfg = _api_call("GET", "/api/settings/push").get("data", {})
        except Exception as e:
            _guard_platform_mode("settings push get", e)
            from signal_push import get_push_config
            pcfg = get_push_config()
    except Exception:
        pcfg = {}

    sc_key = st.text_input("Server酱 Key", value=pcfg.get("serverchan_key", ""), type="password")
    wc_url = st.text_input("企业微信 Webhook", value=pcfg.get("wecom_webhook", ""), type="password")

    c1, c2 = st.columns(2)
    if c1.button("💾 保存推送"):
        try:
            try:
                _api_call("POST", "/api/settings/push", {"serverchan_key": sc_key, "wecom_webhook": wc_url})
            except Exception as e:
                _guard_platform_mode("settings push save", e)
                from signal_push import save_push_config, get_push_config
                pcfg = get_push_config()
                pcfg["serverchan_key"] = sc_key
                pcfg["wecom_webhook"] = wc_url
                save_push_config(pcfg)
            st.success("推送配置已保存")
        except Exception as e:
            st.error(f"保存失败: {e}")
    if c2.button("🔔 测试推送"):
        try:
            try:
                result = _api_call(
                    "POST",
                    "/api/settings/push/test",
                    {"title": "FinQuanta Web测试", "content": "这是来自Web版的测试消息"},
                ).get("data", {})
            except Exception as e:
                _guard_platform_mode("settings push test", e)
                from signal_push import push_signal
                result = push_signal("FinQuanta Web测试", "这是来自Web版的测试消息")
            if result.get("wecom") or result.get("serverchan"):
                st.success("推送成功！")
            else:
                st.warning("推送失败，请检查配置")
        except Exception as e:
            st.error(f"测试失败: {e}")

    st.subheader("API 生产安全")
    try:
        import pandas as pd

        security = _api_call("GET", "/api/admin/security-check").get("data", {})
        security_status = str(security.get("status", "-") or "-")
        security_summary = str(security.get("summary", "") or "")
        if security_status == "ready":
            st.success(f"安全自检: {security_status} | {security_summary or '认证配置可用于生产'}")
        elif security_status == "error":
            st.error(f"安全自检: {security_status} | {security_summary}")
        else:
            st.warning(f"安全自检: {security_status} | {security_summary}")

        s1, s2, s3 = st.columns(3)
        s1.metric("默认密码", "未修改" if security.get("default_admin_password") else "已修改")
        role_counts = security.get("role_counts", {}) or {}
        s2.metric("管理员账号", int(role_counts.get("admin", 0) or 0))
        tokens = security.get("tokens", {}) or {}
        s3.metric("异常/过期 Token", int(tokens.get("expired", 0) or 0) + int(tokens.get("invalid", 0) or 0))

        findings = security.get("findings", []) or []
        if findings:
            st.dataframe(pd.DataFrame(findings), use_container_width=True, height=180)
        if st.button("清理过期/异常 Token"):
            result = _api_call("POST", "/api/admin/tokens/cleanup-expired").get("data", {})
            st.success(
                "已清理 Token: "
                f"删除 {result.get('deleted', 0)} | "
                f"过期 {result.get('expired', 0)} | 异常 {result.get('invalid', 0)}"
            )
            st.rerun()
    except Exception as e:
        if _is_platform_mode():
            st.error(f"安全自检需要管理员 API 权限：{e}")
        else:
            st.info(f"连接 API 后可查看管理员安全自检：{e}")
