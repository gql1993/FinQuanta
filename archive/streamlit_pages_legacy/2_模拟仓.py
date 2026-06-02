"""模拟仓管理 - 买入/卖出/风控/盈亏跟踪"""
import streamlit as st
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="模拟仓", page_icon="💼", layout="wide")

from services.portfolio_service import (
    get_portfolio, save, execute_buy, execute_sell,
    get_portfolio_summary, calc_position_size, fetch_live_prices,
    check_trading_day,
)
from services.stock_service import (
    get_stock_names, get_multi_period_pnl,
    get_realtime_prices, get_realtime_quotes, get_daily_data, sepa_risk_assessment, get_config, get_data_source_logs,
)
from ui.charts import plot_portfolio_pie, plot_multi_period_bar

st.title("💼 模拟仓管理")


def _cache_freshness(state) -> tuple[float | None, str]:
    cache_dir = get_config().data.cache_dir
    latest_ts = None
    latest_file = ""

    # 1) 优先使用本页实时行情刷新时间，最能代表“当前页数据新鲜度”。
    quote_ts = st.session_state.get("_price_ts", 0)
    if quote_ts:
        latest_ts = float(quote_ts)
        latest_file = "live_quotes(session)"

    # 2) 再看当前持仓对应的日线缓存，避免被无关股票缓存误导。
    try:
        pos_codes = [p.get("code", "") for p in (state.positions or [])]
        for code in pos_codes:
            if not code:
                continue
            p = os.path.join(cache_dir, f"daily_{code}.csv")
            if os.path.exists(p):
                ts = os.path.getmtime(p)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                    latest_file = os.path.basename(p)
    except Exception:
        pass

    # 3) 兜底看通用缓存文件。
    for fn in ["stock_list.csv", "financial.csv"]:
        p = os.path.join(cache_dir, fn)
        if os.path.exists(p):
            ts = os.path.getmtime(p)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_file = fn
    if latest_ts is None:
        return None, "未检测到本地缓存文件"
    age_h = (datetime.now().timestamp() - latest_ts) / 3600.0
    dt_str = datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M:%S")
    return age_h, f"最新缓存：{dt_str}（{latest_file}）"

# Trading status
_can_trade, _td_msg = check_trading_day()
if _can_trade:
    st.success(f"📅 {_td_msg} — 可下单交易")
else:
    st.warning(f"📅 {_td_msg} — 当前不可交易")

state = get_portfolio()
try:
    names_map = get_stock_names()
except Exception:
    names_map = {}
    st.warning("股票名称映射加载失败，已降级为仅代码显示，不影响持仓管理。")


def _quote_from_daily_cache(code: str, fallback_name: str = "", force_refresh: bool = False) -> dict | None:
    """离线兜底：用本地日线缓存近两日收盘价构造行情。"""
    try:
        df = get_daily_data(code, force_refresh=force_refresh)
    except Exception:
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    try:
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2]) if len(df) >= 2 else last_close
    except Exception:
        return None
    return {
        "name": fallback_name or names_map.get(code, ""),
        "open": last_close,
        "prev_close": prev_close,
        "price": last_close,
        "high": last_close,
        "low": last_close,
    }


def _fetch_live_quotes_safe(codes: list[str], positions: list[dict], force_refresh_daily: bool = False) -> dict[str, dict]:
    """在线优先；失败/缺失时回退本地缓存价，保证页面不中断。"""
    quotes: dict[str, dict] = {}
    try:
        quotes = get_realtime_quotes(codes) or {}
    except Exception:
        quotes = {}

    pos_name = {p.get("code", ""): p.get("name", "") for p in positions}
    entry_map = {p.get("code", ""): float(p.get("entry_price", 0) or 0) for p in positions}
    for code in codes:
        q = quotes.get(code)
        price_ok = bool(q and q.get("price", 0) and float(q.get("price", 0)) > 0)
        prev_ok = bool(q and q.get("prev_close", 0) and float(q.get("prev_close", 0)) > 0)
        if price_ok and prev_ok:
            continue
        fb = _quote_from_daily_cache(code, pos_name.get(code, ""), force_refresh=force_refresh_daily)
        if fb is None:
            fb = _quote_from_daily_cache(code, pos_name.get(code, ""), force_refresh=True)
        if fb is not None:
            if not price_ok:
                if q is None:
                    quotes[code] = fb
                else:
                    quotes[code] = dict(q)
                    quotes[code]["price"] = fb["price"]
                    if not prev_ok:
                        quotes[code]["prev_close"] = fb["prev_close"]
            elif not prev_ok:
                quotes[code] = dict(q)
                quotes[code]["prev_close"] = fb["prev_close"]
        elif not price_ok:
            ep = entry_map.get(code, 0)
            if ep > 0:
                quotes[code] = {
                    "name": pos_name.get(code, ""),
                    "open": ep, "prev_close": ep,
                    "price": ep, "high": ep, "low": ep,
                }
    return quotes

# Layout mode switch for different window sizes
layout_mode = st.radio(
    "布局模式",
    options=["标准", "紧凑"],
    horizontal=True,
    key="sim_layout_mode",
)
is_compact = layout_mode == "紧凑"

# Auto-fetch real-time quotes (price + prev_close) on page load
import time as _time
_price_age = _time.time() - st.session_state.get("_price_ts", 0)
_need_refresh = state.positions and (_price_age > 60 or "live_quotes" not in st.session_state)

if _need_refresh:
    with st.spinner("获取实时行情..."):
        codes = [p["code"] for p in state.positions]
        st.session_state["live_quotes"] = _fetch_live_quotes_safe(codes, state.positions, force_refresh_daily=False)
        st.session_state["live_prices"] = {c: q["price"] for c, q in st.session_state["live_quotes"].items()}
        st.session_state["_price_ts"] = _time.time()
        st.session_state["_manual_force_refresh"] = False

if st.sidebar.button("🔄 刷新行情", width="stretch"):
    with st.spinner("获取实时行情..."):
        codes = [p["code"] for p in state.positions]
        st.session_state["live_quotes"] = _fetch_live_quotes_safe(codes, state.positions, force_refresh_daily=True)
        st.session_state["live_prices"] = {c: q["price"] for c, q in st.session_state["live_quotes"].items()}
        refreshed_daily = 0
        for c in codes:
            try:
                ddf = get_daily_data(c, force_refresh=True)
                if ddf is not None and not ddf.empty:
                    refreshed_daily += 1
            except Exception:
                continue
        st.session_state["_daily_refresh_count"] = refreshed_daily
        st.session_state["_price_ts"] = _time.time()
        st.session_state["_manual_force_refresh"] = True

force_daily_refresh = bool(st.session_state.pop("_manual_force_refresh", False))
if st.session_state.get("_daily_refresh_count", None) is not None:
    st.caption(f"本次强制刷新日线成功：{st.session_state.get('_daily_refresh_count', 0)} 只")

_age_h, _fresh_msg = _cache_freshness(state)
if _age_h is None:
    st.error(f"⚠️ 数据新鲜度：{_fresh_msg}，当前页面可能无法更新实时结果。")
elif _age_h >= 18:
    st.error(f"⚠️ 数据新鲜度偏旧（{_age_h:.1f} 小时）：{_fresh_msg}")
elif _age_h >= 6:
    st.warning(f"⚠️ 数据新鲜度一般（{_age_h:.1f} 小时）：{_fresh_msg}")
else:
    st.success(f"🟢 数据新鲜度良好（{_age_h:.1f} 小时）：{_fresh_msg}")

with st.expander("🧾 数据源命中日志（最近50条）", expanded=False):
    _logs = get_data_source_logs(limit=50)
    if _logs:
        st.code("\n".join(_logs), language="text")
    else:
        st.caption("暂无命中日志。")

live_prices = st.session_state.get("live_prices", {})
live_quotes = st.session_state.get("live_quotes", {})
prev_close_prices = {c: q["prev_close"] for c, q in live_quotes.items() if q.get("prev_close") and float(q.get("prev_close", 0)) > 0}

# 对所有持仓补全 live_prices / prev_close，确保 summary 不全是 0。
_repaired = False
for p in state.positions:
    code = p.get("code", "")
    if not code:
        continue
    lp = live_prices.get(code, 0)
    pc = prev_close_prices.get(code, 0)
    need_price = not lp or float(lp) <= 0
    need_prev = not pc or float(pc) <= 0
    if need_price or need_prev:
        fb = _quote_from_daily_cache(code, p.get("name", ""), force_refresh=force_daily_refresh)
        if fb is None:
            fb = _quote_from_daily_cache(code, p.get("name", ""), force_refresh=True)
        if fb is not None:
            if need_price:
                live_prices[code] = fb.get("price", p.get("entry_price", 0))
                _repaired = True
            if need_prev:
                prev_close_prices[code] = fb.get("prev_close", 0)
                _repaired = True
        elif need_price:
            ep = float(p.get("entry_price", 0) or 0)
            if ep > 0:
                live_prices[code] = ep
                if need_prev:
                    prev_close_prices[code] = ep
                _repaired = True

summary = get_portfolio_summary(state, live_prices, prev_close_prices)

# Cache per-position risk assessment so table/expanders share one calculation.
risk_cache: dict[str, list[dict]] = {}
if summary["positions"]:
    for pos_data, raw_pos in zip(summary["positions"], state.positions):
        code = pos_data["代码"]
        q = live_quotes.get(code, {})
        rt_price = live_prices.get(code, pos_data["现价"])
        risk_cache[code] = sepa_risk_assessment(
            code=code,
            entry_price=pos_data["买入价"],
            stop_loss=pos_data["止损"],
            shares=pos_data["股数"],
            entry_date=pos_data["买入日"],
            realtime_price=rt_price,
            quote=q,
            partial_sold=raw_pos.get("partial_sold", False),
        )

# ---- Account Summary (同花顺 style) ----
main_size = "1.55rem" if is_compact else "2rem"
sub_size = "0.95rem" if is_compact else "1.1rem"
st.markdown(f"""
<style>
.acct-box {{ border: 1px solid #e0e0e0; border-radius: 10px; padding: 16px 20px;
            background: linear-gradient(135deg, #fafafa 0%, #f0f4ff 100%); }}
.acct-main {{ font-size: {main_size}; font-weight: bold; }}
.acct-pos  {{ color: #ef5350; }}
.acct-neg  {{ color: #26a69a; }}
.acct-head {{ display:flex; align-items:flex-end; gap:24px; flex-wrap:wrap; }}
.acct-sub {{ font-size:{sub_size}; }}
@media (max-width: 1280px) {{
  .acct-main {{ font-size: 1.6rem; }}
  .acct-sub  {{ font-size: 1rem; }}
}}
@media (max-width: 960px) {{
  .acct-main {{ font-size: 1.3rem; }}
  .acct-sub  {{ font-size: 0.95rem; }}
}}
</style>
""", unsafe_allow_html=True)

pnl_color = "acct-pos" if summary["total_return"] >= 0 else "acct-neg"

st.markdown(f"""
<div class="acct-box">
  <div class="acct-head">
    <span class="acct-main {pnl_color}">总资产 ¥{summary['total_equity']:,.2f}</span>
    <span class="acct-sub">总收益 <span class="{pnl_color}">{summary['total_return']:+.2f}%</span></span>
  </div>
</div>
""", unsafe_allow_html=True)

metrics = [
    ("总市值", f"¥{summary['position_value']:,.2f}", None),
    ("总成本", f"¥{summary['total_cost']:,.2f}", None),
    ("可用资金", f"¥{summary['available_cash']:,.2f}", None),
    ("可取资金", f"¥{summary['available_cash']:,.2f}", None),
    ("浮动盈亏", f"¥{summary['unrealized_pnl']:+,.2f}", f"{summary['unrealized_pnl_pct']:+.2f}%"),
    ("当日参考盈亏", f"¥{summary['today_pnl']:+,.2f}", None),
    ("仓位比例", f"{summary['position_ratio']:.1f}%", None),
    ("持仓数", f"{summary['num_positions']}/{summary['max_positions']}", None),
    ("已实现盈亏", f"¥{summary['realized_pnl']:+,.2f}", None),
    ("累计盈亏", f"¥{summary['total_pnl']:+,.2f}", None),
    ("初始资金", f"¥{summary['initial_capital']:,.0f}", None),
    ("资金利用率", f"{summary['position_ratio']:.1f}%", None),
]

metric_cols = 4 if is_compact else 3
for i in range(0, len(metrics), metric_cols):
    cols = st.columns(metric_cols)
    for col, (label, value, delta) in zip(cols, metrics[i:i+metric_cols]):
        col.metric(label, value, delta)

st.divider()

# ---- Tabs ----
tab_pos, tab_pnl, tab_buy, tab_sell, tab_history = st.tabs(
    ["📊 持仓", "📈 盈亏分析", "🛒 买入", "📤 卖出", "📋 交易记录"])

# ---- Positions Tab ----
with tab_pos:
    if summary["positions"]:
        pos_enriched = []
        for pos_data, raw_pos in zip(summary["positions"], state.positions):
            code = pos_data["代码"]
            alerts = risk_cache.get(code, [])
            process_alert = alerts[0] if alerts else {}
            title = process_alert.get("title", "")
            if isinstance(title, str) and "交易流程阶段：" in title:
                phase = title.split("交易流程阶段：", 1)[-1].strip()
            else:
                phase = "未判定"
            next_action = process_alert.get("action", "观望")
            pos_enriched.append({
                "pos_data": pos_data,
                "raw_pos": raw_pos,
                "phase": phase,
                "next_action": next_action,
            })

        phase_options = sorted({x["phase"] for x in pos_enriched})
        selected_phases = st.multiselect(
            "阶段筛选器",
            options=phase_options,
            default=phase_options,
            help="筛选要查看的交易阶段（如减仓保护/卖出执行）",
        )
        filtered_positions = [x for x in pos_enriched if x["phase"] in selected_phases]

        col_table, col_pie = st.columns([3, 1])

        with col_table:
            df = pd.DataFrame([x["pos_data"] for x in filtered_positions])
            if not df.empty:
                df["当前阶段"] = [x["phase"] for x in filtered_positions]
                df["下一步动作"] = [x["next_action"] for x in filtered_positions]

            def color_pnl(val):
                if isinstance(val, (int, float)):
                    if val > 0:
                        return "color: #ef5350; font-weight: bold"
                    elif val < 0:
                        return "color: #26a69a; font-weight: bold"
                return ""

            if df.empty:
                st.info("当前筛选条件下暂无持仓。")
            else:
                pnl_cols = [c for c in ["浮动盈亏", "盈亏%", "当日盈亏", "当日%"] if c in df.columns]
                styled = df.style.map(color_pnl, subset=pnl_cols)
                st.dataframe(styled, width="stretch", hide_index=True,
                             height=min(len(df) * (32 if is_compact else 38) + 40,
                                        420 if is_compact else 500))

        with col_pie:
            fig = plot_portfolio_pie(state.positions, live_prices, state.cash)
            st.plotly_chart(fig, width="stretch")

        # Quick-nav buttons to stock detail page
        st.markdown("###### 点击查看个股详情")
        btn_cols = st.columns(max(1, min(len(filtered_positions), 6)))
        for idx, row in enumerate(filtered_positions):
            pos = row["pos_data"]
            col_idx = idx % len(btn_cols)
            label = f"{pos['代码']} {pos['名称']}"
            if btn_cols[col_idx].button(label, key=f"pos_detail_{pos['代码']}", width="stretch"):
                st.session_state["detail_code"] = pos["代码"]
                st.switch_page("pages/4_个股分析.py")

        # SEPA Risk Assessment
        st.divider()
        st.markdown("#### ⚠️ SEPA 策略风控研判")
        st.caption("基于《股票魔法师》各章策略规则综合分析，给出买入/卖出/持有建议及理由")

        _level_icons = {"danger": "🔴", "warning": "🟡", "success": "🟢", "info": "🔵"}
        _has_alerts = False

        for row in filtered_positions:
            pos_data = row["pos_data"]
            code = pos_data["代码"]
            rt_price = live_prices.get(code, pos_data["现价"])
            risk_alerts = risk_cache.get(code, [])

            # Always show the process-state card (first alert), then show important alerts.
            process_card = risk_alerts[:1]
            important = [a for a in risk_alerts[1:] if a["level"] in ("danger", "warning", "success")]
            show_alerts = process_card + important

            if show_alerts:
                _has_alerts = True
                with st.expander(
                    f"{pos_data['代码']} {pos_data['名称']}　"
                    f"现价 {rt_price:.2f}　盈亏 {pos_data.get('盈亏%', 0):+.2f}%　"
                    f"({len(show_alerts)} 条建议)",
                    expanded=bool(important) or bool(process_card),
                ):
                    for alert in show_alerts:
                        icon = _level_icons.get(alert["level"], "⚪")
                        st.markdown(
                            f"{icon} **[{alert['action']}]** {alert['title']}\n\n"
                            f"> {alert['reason']}"
                        )

        if not _has_alerts:
            if filtered_positions:
                st.info("当前筛选持仓暂无异常信号")
            else:
                st.info("当前筛选条件下无持仓可展示")

        # ---- 组合风险监控面板 ----
        st.divider()
        st.markdown("#### 📊 组合风险监控")
        st.caption("VaR / CVaR / 回撤 / 集中度实时评估")
        try:
            from risk_monitor import PortfolioRiskMonitor
            _daily_map = {}
            for pos in state.positions:
                _code = pos.get("code", "")
                try:
                    _ddf = get_daily_data(_code, force_refresh=False)
                    if _ddf is not None and not _ddf.empty:
                        _daily_map[_code] = _ddf
                except Exception:
                    pass
            _peak = st.session_state.get("_peak_equity", summary["total_equity"])
            _peak = max(_peak, summary["total_equity"])
            st.session_state["_peak_equity"] = _peak

            _rm = PortfolioRiskMonitor()
            _risk_report = _rm.assess(
                state.positions, live_prices, _daily_map,
                cash=state.cash, peak_equity=_peak,
            )
            rc1, rc2 = st.columns([2, 1])
            with rc1:
                st.dataframe(PortfolioRiskMonitor.summarize(_risk_report), width="stretch", hide_index=True)
            with rc2:
                _risk_icons = {"danger": "🔴", "warning": "🟡", "success": "🟢", "info": "🔵"}
                for _ra in _risk_report.alerts:
                    _icon = _risk_icons.get(_ra["level"], "⚪")
                    st.markdown(f"{_icon} **{_ra['title']}**")
                    st.caption(f"{_ra['reason']}")

            with st.expander("个股风险明细", expanded=False):
                if _risk_report.position_risks:
                    st.dataframe(pd.DataFrame(_risk_report.position_risks), width="stretch", hide_index=True)
        except Exception as _risk_exc:
            st.caption(f"组合风险监控加载失败：{_risk_exc}")
    else:
        st.info("模拟仓为空。请在「买入」页签中添加持仓。")

# ---- P&L Analysis Tab ----
with tab_pnl:
    if summary["positions"]:
        st.markdown("#### 实时多周期盈亏分析")
        st.caption("数据来源：东方财富实时行情 | 红色=盈利/上涨 绿色=亏损/下跌")

        # Compute multi-period P&L with real-time prices
        pnl_rows = []
        all_period_data = {}
        for pos in summary["positions"]:
            code = pos["代码"]
            realtime = live_prices.get(code, 0)
            entry = pos["买入价"]
            retried = False
            used_fallback = False
            pdata = get_multi_period_pnl(
                code, realtime, entry,
                force_refresh=force_daily_refresh
            )
            # 若当前项无可用周期数据，单独触发一次强制拉取重算（仅对失败项执行）。
            if not pdata:
                retried = True
                pdata = get_multi_period_pnl(code, realtime, entry, force_refresh=True)
            if not pdata:
                used_fallback = True
                # 强兜底：即使历史数据缺失，也回填基础实时/当日数据，避免表格出现全空。
                rt_fallback = realtime if realtime and realtime > 0 else float(pos.get("现价", entry))
                pos_pnl_fallback = (rt_fallback - entry) / entry * 100 if entry > 0 else 0
                today_fallback = float(pos.get("当日%", 0.0))
                pdata = {
                    "实时价": round(rt_fallback, 2),
                    "持仓盈亏%": round(pos_pnl_fallback, 2),
                    "当日": round(today_fallback, 2),
                    "7日": None,
                    "30日": None,
                    "一季度": None,
                    "半年": None,
                    "一年": None,
                    "预测20日": None,
                    "趋势": "缓存不足",
                }
            all_period_data[code] = pdata

            rt_price = pdata.get("实时价", realtime if realtime > 0 else float(pos.get("现价", entry)))
            pos_pnl = pdata.get("持仓盈亏%", 0)
            day_fallback_pct = float(pos.get("当日%", 0.0))
            today_val = pdata.get("当日")
            if today_val is None:
                today_val = day_fallback_pct

            row = {
                "代码": code,
                "名称": pos["名称"],
                "买入价": entry,
                "实时价": rt_price,
                "持仓盈亏%": f"{pos_pnl:+.2f}%",
            }
            for k in ["7日", "30日", "一季度", "半年", "一年"]:
                v = pdata.get(k)
                row[k] = f"{v:+.2f}%" if v is not None else "-"
            row["当日"] = f"{today_val:+.2f}%"
            row["预测20日"] = f"{pdata['预测20日']:+.2f}%" if pdata.get("预测20日") is not None else "-"
            row["趋势"] = pdata.get("趋势", "-")
            if used_fallback:
                reasons = []
                if not realtime or realtime <= 0:
                    reasons.append("实时行情缺失")
                try:
                    dchk = get_daily_data(code, force_refresh=False)
                    if dchk is None or dchk.empty:
                        reasons.append("日线缓存缺失")
                    elif len(dchk) < 22:
                        reasons.append("日线样本不足")
                except Exception:
                    reasons.append("日线读取失败")
                row["缺失原因"] = "；".join(reasons) if reasons else "接口失败已回退"
            elif retried:
                row["缺失原因"] = "首次拉取失败，重试成功"
            else:
                row["缺失原因"] = "-"
            pnl_rows.append(row)

        pnl_df = pd.DataFrame(pnl_rows)

        def _color_pnl_str(val):
            if isinstance(val, str) and val not in ("-", ""):
                try:
                    v = float(val.replace("%", "").replace("+", ""))
                    if v > 0:
                        return "color: #ef5350; font-weight: bold"
                    elif v < 0:
                        return "color: #26a69a; font-weight: bold"
                except (ValueError, TypeError):
                    pass
            return ""

        def _color_trend(val):
            if val == "看涨":
                return "color: #ef5350; font-weight: bold"
            elif val == "看跌":
                return "color: #26a69a; font-weight: bold"
            return "color: #FF9800"

        pct_cols = ["持仓盈亏%", "当日", "7日", "30日", "一季度", "半年", "一年", "预测20日"]
        styled = pnl_df.style.map(_color_pnl_str, subset=pct_cols)
        styled = styled.map(_color_trend, subset=["趋势"])
        st.dataframe(styled, width="stretch", hide_index=True,
                     height=min(len(pnl_df) * 38 + 40, 500))

        # ---- Per-stock detail + actual vs predicted ----
        st.divider()
        st.markdown("#### 个股详情 — 实际盈亏 vs 预测")
        sel_options = [f"{r['代码']} {r['名称']}" for r in pnl_rows]
        sel = st.selectbox("选择持仓", sel_options, key="pnl_detail_sel")
        sel_code = sel.split()[0]
        sel_name = sel.split()[1] if len(sel.split()) > 1 else sel_code
        pdata = all_period_data.get(sel_code, {})
        sel_row = next((r for r in pnl_rows if r["代码"] == sel_code), {})

        pc1, pc2 = st.columns([3, 1])
        with pc1:
            fig = plot_multi_period_bar(pdata, sel_name)
            st.plotly_chart(fig, width="stretch")

        with pc2:
            rt = pdata.get("实时价", 0)
            pos_pnl_val = pdata.get("持仓盈亏%", 0)
            today_chg = pdata.get("当日")
            pred_val = pdata.get("预测20日")
            trend = pdata.get("趋势", "-")
            momentum = pdata.get("动量", "-")

            st.metric("实时价", f"¥{rt:.2f}")
            delta_color = "normal" if pos_pnl_val >= 0 else "inverse"
            st.metric("持仓盈亏", f"{pos_pnl_val:+.2f}%", delta_color=delta_color)

            if today_chg is not None:
                delta_color_t = "normal" if today_chg >= 0 else "inverse"
                st.metric("今日涨跌", f"{today_chg:+.2f}%", delta_color=delta_color_t)

            st.divider()
            st.markdown("##### 趋势预测")
            if trend == "看涨":
                st.success(f"📈 **{trend}**")
            elif trend == "看跌":
                st.error(f"📉 **{trend}**")
            else:
                st.warning(f"📊 **{trend}**")

            if pred_val is not None:
                st.metric("预测20日", f"{pred_val:+.2f}%")

                # Actual vs Predicted comparison
                if today_chg is not None:
                    st.divider()
                    st.markdown("##### 实际 vs 预测")
                    if pred_val > 0 and today_chg < 0:
                        st.error(f"⚠️ 预测看涨 {pred_val:+.1f}%，实际今日 {today_chg:+.1f}%，背离!")
                    elif pred_val < 0 and today_chg > 0:
                        st.success(f"预测看跌 {pred_val:+.1f}%，实际今日 {today_chg:+.1f}%，超预期")
                    elif pred_val > 0 and today_chg > 0:
                        st.success(f"预测 {pred_val:+.1f}% / 实际 {today_chg:+.1f}%，方向一致 ✓")
                    else:
                        st.warning(f"预测 {pred_val:+.1f}% / 实际 {today_chg:+.1f}%，方向一致 ✓")

            st.markdown(f"**动量**: {momentum}")
            st.caption("预测基于60日线性回归 + MA动量，仅供参考")
    else:
        st.info("模拟仓为空，建仓后可查看盈亏分析。")

# ---- Buy Tab ----
with tab_buy:
    st.markdown("#### 买入股票")

    bc1, bc2 = st.columns(2)
    with bc1:
        buy_code = st.text_input("股票代码", placeholder="例如: 603881", key="buy_code")
        buy_price = st.number_input("买入价格", min_value=0.01, value=10.0, step=0.01, key="buy_price")
        buy_stop_pct = st.slider("止损比例 (%)", 5, 15, 8, key="buy_stop") / 100

    with bc2:
        buy_name = names_map.get(buy_code, "")
        if buy_name:
            st.markdown(f"**{buy_name}**")
        suggested = calc_position_size(state, buy_price, buy_stop_pct)
        buy_shares = st.number_input("买入股数", min_value=100, value=max(suggested, 100),
                                      step=100, key="buy_shares")

        cost_est = buy_price * buy_shares * 1.001
        stop_price = round(buy_price * (1 - buy_stop_pct), 2)
        risk = buy_price * buy_shares * buy_stop_pct
        st.markdown(f"预估费用: **¥{cost_est:,.0f}** | 止损价: **{stop_price}** | 风险: **¥{risk:,.0f}**")

    buy_notes = st.text_input("备注", placeholder="例如: VCP突破, 收缩4次", key="buy_notes")

    if st.button("确认买入", type="primary", key="confirm_buy"):
        if not buy_code:
            st.error("请输入股票代码")
        else:
            ok, msg = execute_buy(state, buy_code, buy_name or buy_code, buy_price,
                                   buy_shares, buy_stop_pct, notes=buy_notes)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ---- Sell Tab ----
with tab_sell:
    st.markdown("#### 卖出股票")

    if state.positions:
        pos_options = {f"{p['code']} {p.get('name', '')}": p for p in state.positions}
        selected = st.selectbox("选择持仓", list(pos_options.keys()), key="sell_select")
        pos = pos_options[selected]

        sc1, sc2 = st.columns(2)
        with sc1:
            sell_price = st.number_input("卖出价格", min_value=0.01,
                                          value=float(live_prices.get(pos["code"], pos["entry_price"])),
                                          step=0.01, key="sell_price")
        with sc2:
            sell_shares = st.number_input("卖出股数 (0=全部)", min_value=0,
                                           max_value=pos["shares"], value=0,
                                           step=100, key="sell_shares")

        sell_reason = st.selectbox("卖出原因", [
            "硬止损", "渐进止损", "部分止盈", "时间止损",
            "高潮顶", "Stage 3 退出", "主动卖出", "其他",
        ], key="sell_reason")

        pnl_est = (sell_price - pos["entry_price"]) * (sell_shares or pos["shares"])
        st.markdown(f"预估盈亏: **¥{pnl_est:+,.0f}**")

        if st.button("确认卖出", type="primary", key="confirm_sell"):
            ok, msg = execute_sell(state, pos["code"], sell_price,
                                    sell_reason, sell_shares)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("当前无持仓")

# ---- Trade History ----
with tab_history:
    if summary["closed_trades"]:
        trades_df = pd.DataFrame(summary["closed_trades"])
        wins = sum(1 for t in summary["closed_trades"] if t.get("pnl", 0) > 0)
        total_t = len(summary["closed_trades"])
        realized = sum(t.get("pnl", 0) for t in summary["closed_trades"])

        hc1, hc2, hc3 = st.columns(3)
        hc1.metric("总交易", f"{total_t} 笔")
        hc2.metric("胜率", f"{wins/total_t*100:.1f}%" if total_t else "0%")
        hc3.metric("已实现盈亏", f"¥{realized:+,.0f}")

        st.dataframe(trades_df, width="stretch", hide_index=True)
    else:
        st.info("暂无交易记录")
