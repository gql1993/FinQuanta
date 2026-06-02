"""回测分析 - 历史数据回测 + 可视化报告"""
import streamlit as st
import sys, os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="回测分析", page_icon="📊", layout="wide")

from services.stock_service import (
    run_backtest, run_backtest_multi, get_strategy_catalog, get_strategy_params,
    load_strategy_param_templates, save_strategy_param_template,
)
from ui.charts import (
    plot_equity_curve, plot_drawdown, plot_monthly_heatmap,
    plot_exit_reasons, plot_pnl_distribution, plot_strategy_correlation,
)
from monte_carlo import MonteCarloSimulator
from walkforward import WalkForward

st.title("📊 回测分析")
st.caption("基于统一历史样本验证多策略表现")


def _build_reason_diagnostics(trades):
    """按买入/卖出逻辑汇总统计：触发次数、胜率、平均盈亏%、累计盈亏。"""
    rows = []
    for t in trades:
        rows.append({
            "strategy": getattr(t, "strategy_id", ""),
            "entry_reason": str(getattr(t, "entry_reason", "")) or "未记录",
            "exit_reason": str(getattr(t, "exit_reason", "")) or "未记录",
            "pnl": float(getattr(t, "pnl", 0.0)),
            "pnl_pct": float(getattr(t, "pnl_pct", 0.0)),
            "win": 1 if float(getattr(t, "pnl", 0.0)) > 0 else 0,
        })
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(rows)

    entry_diag = (
        df.groupby("entry_reason", dropna=False)
        .agg(
            触发次数=("entry_reason", "count"),
            胜率=("win", "mean"),
            平均盈亏百分比=("pnl_pct", "mean"),
            累计盈亏=("pnl", "sum"),
            平均单笔盈亏=("pnl", "mean"),
        )
        .reset_index()
        .rename(columns={"entry_reason": "买入逻辑"})
        .sort_values(["触发次数", "累计盈亏"], ascending=[False, False])
    )

    exit_diag = (
        df.groupby("exit_reason", dropna=False)
        .agg(
            触发次数=("exit_reason", "count"),
            胜率=("win", "mean"),
            平均盈亏百分比=("pnl_pct", "mean"),
            累计盈亏=("pnl", "sum"),
            平均单笔盈亏=("pnl", "mean"),
        )
        .reset_index()
        .rename(columns={"exit_reason": "卖出逻辑"})
        .sort_values(["触发次数", "累计盈亏"], ascending=[False, False])
    )

    return entry_diag, exit_diag


def _format_diag_df(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["胜率"] = out["胜率"].map(lambda x: f"{x:.1%}")
    out["平均盈亏百分比"] = out["平均盈亏百分比"].map(lambda x: f"{x:+.2%}")
    out["累计盈亏"] = out["累计盈亏"].map(lambda x: f"¥{x:+,.0f}")
    out["平均单笔盈亏"] = out["平均单笔盈亏"].map(lambda x: f"¥{x:+,.0f}")
    cols = [key_col, "触发次数", "胜率", "平均盈亏百分比", "累计盈亏", "平均单笔盈亏"]
    return out[cols]


def _logic_top3(df: pd.DataFrame, key_col: str, positive: bool = True) -> list[dict]:
    if df.empty:
        return []
    ranked = df.sort_values("累计盈亏", ascending=not positive).head(3)
    items = []
    for _, r in ranked.iterrows():
        items.append({
            "name": str(r.get(key_col, "")),
            "count": int(r.get("触发次数", 0)),
            "pnl": float(r.get("累计盈亏", 0.0)),
            "win": float(r.get("胜率", 0.0)),
        })
    return items


def _render_top3_cards(entry_diag: pd.DataFrame, exit_diag: pd.DataFrame):
    """红绿摘要：Top3 有效逻辑 / Top3 低效逻辑。"""
    pool = []
    if not entry_diag.empty:
        tmp = entry_diag.copy()
        tmp["逻辑类型"] = "买入"
        tmp = tmp.rename(columns={"买入逻辑": "逻辑"})
        pool.append(tmp[["逻辑类型", "逻辑", "触发次数", "胜率", "累计盈亏"]])
    if not exit_diag.empty:
        tmp = exit_diag.copy()
        tmp["逻辑类型"] = "卖出"
        tmp = tmp.rename(columns={"卖出逻辑": "逻辑"})
        pool.append(tmp[["逻辑类型", "逻辑", "触发次数", "胜率", "累计盈亏"]])

    if not pool:
        st.info("暂无可用逻辑诊断摘要")
        return

    all_diag = pd.concat(pool, ignore_index=True)
    best = all_diag.sort_values("累计盈亏", ascending=False).head(3)
    worst = all_diag.sort_values("累计盈亏", ascending=True).head(3)

    c_good, c_bad = st.columns(2)
    with c_good:
        st.markdown("#### 🟢 Top3 有效逻辑")
        if best.empty:
            st.caption("暂无数据")
        else:
            for _, r in best.iterrows():
                st.markdown(
                    f"- `{r['逻辑类型']}` {r['逻辑']} ｜累计 **¥{float(r['累计盈亏']):+,.0f}** ｜"
                    f"触发 {int(r['触发次数'])} 次 ｜胜率 {float(r['胜率']):.1%}"
                )


def _practical_confidence(total_trades: int, win_rate: float) -> tuple[str, str]:
    """
    交易样本量+胜率的实践验证分级。
    返回: (等级, 说明)
    """
    if total_trades < 20:
        return "低", "样本较少，需继续观察"
    if total_trades < 60:
        if win_rate >= 0.55:
            return "中", "样本中等，策略具备可用性"
        return "中", "样本中等，但稳定性一般"
    if win_rate >= 0.58:
        return "高", "样本较充分，实践可靠性较高"
    if win_rate >= 0.5:
        return "中", "样本充分，但优势边际有限"
    return "低", "样本充分但胜率偏弱"


def _plot_emotion_timeline(phase_df: pd.DataFrame, title: str):
    if phase_df is None or phase_df.empty:
        st.info("暂无情绪阶段时间轴数据")
        return
    fig = go.Figure()
    ordered = ["冰点", "启动", "发酵", "高潮", "退潮", "中性"]
    colors = {
        "冰点": "#4FC3F7",
        "启动": "#81C784",
        "发酵": "#43A047",
        "高潮": "#EF5350",
        "退潮": "#FB8C00",
        "中性": "#BDBDBD",
    }
    for phase in ordered:
        sub = phase_df[phase_df["phase"] == phase]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"],
            y=sub["count"],
            mode="lines",
            stackgroup="one",
            name=phase,
            line=dict(width=0.8, color=colors.get(phase, "#BDBDBD")),
            hovertemplate=f"{phase}<br>%{{x|%Y-%m-%d}}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=30, r=20, t=45, b=25),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title="买点数量",
    )
    st.plotly_chart(fig, width="stretch")


def _plot_factor_diagnostics(factor_df: pd.DataFrame, title: str, thresholds: dict | None = None):
    if factor_df is None or factor_df.empty:
        st.info("暂无三因子诊断样本")
        return
    thresholds = thresholds or {}
    heat_min = thresholds.get("heat_min")
    valuation_min = thresholds.get("valuation_min")
    crowding_max = thresholds.get("crowding_max")

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.74, 0.26],
        subplot_titles=("热度 vs 估值（颜色=拥挤）", "拥挤度分布"),
        horizontal_spacing=0.06,
    )
    fig.add_trace(go.Scatter(
        x=factor_df["heat"],
        y=factor_df["valuation"],
        mode="markers",
        marker=dict(
            size=8,
            color=factor_df["crowding"],
            colorscale="RdYlGn_r",
            cmin=0,
            cmax=100,
            colorbar=dict(title="拥挤度"),
            opacity=0.72,
        ),
        text=factor_df["phase"] if "phase" in factor_df.columns else None,
        hovertemplate=(
            "热度: %{x:.1f}<br>"
            "估值分位: %{y:.1f}<br>"
            "拥挤度: %{marker.color:.1f}<br>"
            "情绪: %{text}<extra></extra>"
        ),
        showlegend=False,
    ), row=1, col=1)

    fig.add_trace(go.Histogram(
        x=factor_df["crowding"],
        nbinsx=20,
        marker_color="rgba(100,149,237,0.55)",
        showlegend=False,
        hovertemplate="拥挤度 %{x:.1f}<br>样本 %{y}<extra></extra>",
    ), row=1, col=2)

    if heat_min is not None:
        fig.add_vline(
            x=float(heat_min), line_dash="dash", line_color="#1E88E5",
            annotation_text=f"热度下限 {float(heat_min):.0f}",
            annotation_position="top left", row=1, col=1,
        )
    if valuation_min is not None:
        fig.add_hline(
            y=float(valuation_min), line_dash="dash", line_color="#43A047",
            annotation_text=f"估值下限 {float(valuation_min):.0f}",
            annotation_position="top left", row=1, col=1,
        )
    if crowding_max is not None:
        fig.add_vline(
            x=float(crowding_max), line_dash="dash", line_color="#E53935",
            annotation_text=f"拥挤上限 {float(crowding_max):.0f}",
            annotation_position="top right", row=1, col=2,
        )

    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=30, r=20, t=45, b=30),
    )
    fig.update_xaxes(title_text="赛道热度 (0-100)", row=1, col=1)
    fig.update_yaxes(title_text="估值分位 (0-100)", row=1, col=1)
    fig.update_xaxes(title_text="拥挤度 (0-100)", row=1, col=2)
    fig.update_yaxes(title_text="样本数", row=1, col=2)
    st.plotly_chart(fig, width="stretch")


def _auto_suggest_thresholds(factor_df: pd.DataFrame, params: dict | None = None) -> dict:
    """
    根据当前回测样本分布，给出三因子阈值建议。
    目标：避免参数过严导致样本过少，也避免过松导致噪音过高。
    """
    if factor_df is None or factor_df.empty:
        return {}

    p = dict(params or {})
    heat = pd.to_numeric(factor_df.get("heat", pd.Series(dtype=float)), errors="coerce").dropna()
    valuation = pd.to_numeric(factor_df.get("valuation", pd.Series(dtype=float)), errors="coerce").dropna()
    crowding = pd.to_numeric(factor_df.get("crowding", pd.Series(dtype=float)), errors="coerce").dropna()
    if heat.empty or valuation.empty or crowding.empty:
        return {}

    # 经验分位建议：热度/估值用35分位，拥挤用70分位（上限）。
    s_heat = float(heat.quantile(0.35))
    s_val = float(valuation.quantile(0.35))
    s_crowd = float(crowding.quantile(0.70))

    def _clamp(x, lo=0.0, hi=100.0):
        return max(lo, min(hi, x))

    suggested = {
        "heat_min": round(_clamp(s_heat), 1),
        "valuation_min": round(_clamp(s_val), 1),
        "crowding_max": round(_clamp(s_crowd), 1),
    }

    # 计算当前阈值通过率，辅助解释过严/过松。
    cur_heat = float(p.get("heat_min", suggested["heat_min"]))
    cur_val = float(p.get("valuation_min", suggested["valuation_min"]))
    cur_crowd = float(p.get("crowding_max", suggested["crowding_max"]))
    passed = (
        (heat >= cur_heat)
        & (valuation >= cur_val)
        & (crowding <= cur_crowd)
    )
    pass_rate = float(passed.mean()) if len(passed) > 0 else 0.0
    suggested["current_pass_rate"] = pass_rate
    return suggested


def _render_suggestion_block(strategy_key: str, strategy_id: str,
                             factor_df: pd.DataFrame, params: dict | None,
                             allow_apply: bool = False):
    if factor_df is None or factor_df.empty:
        return

    btn_key = f"auto_suggest_btn_{strategy_key}"
    cache_key = f"auto_suggest_data_{strategy_key}"
    if st.button("🤖 自动参数建议", key=btn_key, width="stretch"):
        st.session_state[cache_key] = _auto_suggest_thresholds(factor_df, params)

    sugg = st.session_state.get(cache_key)
    if not sugg:
        return

    c1, c2, c3 = st.columns(3)
    cur_h = float((params or {}).get("heat_min", sugg["heat_min"]))
    cur_v = float((params or {}).get("valuation_min", sugg["valuation_min"]))
    cur_c = float((params or {}).get("crowding_max", sugg["crowding_max"]))

    c1.metric("热度下限建议", f"{sugg['heat_min']:.1f}", f"当前 {cur_h:.1f}")
    c2.metric("估值下限建议", f"{sugg['valuation_min']:.1f}", f"当前 {cur_v:.1f}")
    c3.metric("拥挤上限建议", f"{sugg['crowding_max']:.1f}", f"当前 {cur_c:.1f}")

    pr = sugg.get("current_pass_rate", 0.0)
    if pr < 0.2:
        st.warning(f"当前三因子通过率约 {pr:.1%}，偏严，可能错过机会。")
    elif pr > 0.7:
        st.warning(f"当前三因子通过率约 {pr:.1%}，偏松，可能噪音偏多。")
    else:
        st.success(f"当前三因子通过率约 {pr:.1%}，参数松紧度大致适中。")

    if not allow_apply:
        return

    # 仅对当前已暴露三因子参数的策略支持“一键应用”。
    key_map = {
        "cn_pm_danbin": ("bt_danbin_heat", "bt_danbin_val", "bt_danbin_crowd"),
        "cn_pm_linyuan": ("bt_linyuan_heat", "bt_linyuan_val", "bt_linyuan_crowd"),
        "cn_inst_qiuguolu": ("bt_qiuguolu_heat", "bt_qiuguolu_val", "bt_qiuguolu_crowd"),
    }
    if strategy_id not in key_map:
        st.caption("该策略当前未暴露三因子阈值控件，无法一键应用。")
        return

    k_heat, k_val, k_crowd = key_map[strategy_id]
    b1, b2, b3 = st.columns(3)
    if b1.button("✅ 一键应用建议", key=f"auto_apply_btn_{strategy_key}", width="stretch"):
        st.session_state[k_heat] = float(sugg["heat_min"])
        st.session_state[k_val] = float(sugg["valuation_min"])
        st.session_state[k_crowd] = float(sugg["crowding_max"])
        st.success("已应用建议参数。")
        st.rerun()

    if b2.button("🚀 应用并重跑回测", key=f"auto_apply_rerun_btn_{strategy_key}", width="stretch"):
        st.session_state[k_heat] = float(sugg["heat_min"])
        st.session_state[k_val] = float(sugg["valuation_min"])
        st.session_state[k_crowd] = float(sugg["crowding_max"])
        st.session_state["_bt_auto_run"] = True
        st.session_state["_bt_auto_run_msg"] = "已应用建议参数并自动重跑回测。"
        st.rerun()

    if b3.button("💾 保存建议为模板", key=f"auto_save_tpl_btn_{strategy_key}", width="stretch"):
        suggest_params = dict(params or {})
        suggest_params["heat_min"] = float(sugg["heat_min"])
        suggest_params["valuation_min"] = float(sugg["valuation_min"])
        suggest_params["crowding_max"] = float(sugg["crowding_max"])
        tpl_name = f"自动建议-{datetime.now().strftime('%m%d-%H%M%S')}"
        ok = save_strategy_param_template(strategy_id, tpl_name, suggest_params, context="backtest")
        if ok:
            st.success(f"建议模板已保存：{tpl_name}")
        else:
            st.error("保存模板失败")
    with c_bad:
        st.markdown("#### 🔴 Top3 低效逻辑")
        if worst.empty:
            st.caption("暂无数据")
        else:
            for _, r in worst.iterrows():
                st.markdown(
                    f"- `{r['逻辑类型']}` {r['逻辑']} ｜累计 **¥{float(r['累计盈亏']):+,.0f}** ｜"
                    f"触发 {int(r['触发次数'])} 次 ｜胜率 {float(r['胜率']):.1%}"
                )

# Config
with st.sidebar:
    st.markdown("### 回测参数")
    sample_size = st.slider("股票样本数", 50, 500, 200, 50, key="bt_sample")
    start_date = st.date_input("起始日期", value=None, key="bt_start")
    start_str = start_date.strftime("%Y%m%d") if start_date else "20220601"

    st.markdown("### 策略模式")
    catalog = get_strategy_catalog()
    strategy_options = []
    for x in catalog:
        label = f"[{x.get('region', '-')}/{x.get('camp', '-')}] {x['name']}"
        strategy_options.append((label, x["id"]))
    label_to_id = {label: sid for label, sid in strategy_options}
    default_multi = [
        label for label, sid in strategy_options
        if sid in ("sepa", "canslim", "turtle", "graham")
    ]
    selected_names = st.multiselect(
        "选择策略（可多选对比）",
        list(label_to_id.keys()),
        default=default_multi[:2],
        key="bt_strategies",
    )
    selected_ids = [label_to_id[n] for n in selected_names] if selected_names else ["sepa"]
    st.caption("提示：多选时会在同一批股票与同一成本模型下对比。")
    strategy_params_map: dict[str, dict] = {}
    if len(selected_ids) == 1:
        sid = selected_ids[0]
        params = get_strategy_params(sid)
        tpl_all = load_strategy_param_templates("backtest")
        tpl_map = tpl_all.get(sid, {})
        tpl_name = st.selectbox(
            "回测参数模板",
            ["(默认)"] + list(tpl_map.keys()),
            key=f"bt_tpl_{sid}",
            help="加载已保存的回测参数模板",
        )
        if tpl_name != "(默认)":
            params.update(tpl_map.get(tpl_name, {}))
        with st.expander("策略参数", expanded=False):
            if sid == "sepa":
                params["rs_min"] = st.slider("SEPA 最低RS", 60, 95, int(params.get("rs_min", 70)), 1, key="bt_sepa_rs")
                params["pivot_distance_max_pct"] = st.slider(
                    "SEPA 枢纽距离上限(%)", 3.0, 15.0, float(params.get("pivot_distance_max_pct", 8.0)), 0.5,
                    key="bt_sepa_pivot"
                )
                params["volume_ratio_min"] = st.slider(
                    "SEPA 最低量比", 0.5, 1.5, float(params.get("volume_ratio_min", 0.8)), 0.05,
                    key="bt_sepa_vol"
                )
            elif sid == "canslim":
                params["rs_min"] = st.slider("CANSLIM 最低RS", 70, 95, int(params.get("rs_min", 80)), 1, key="bt_canslim_rs")
                params["volume_ratio_min"] = st.slider(
                    "CANSLIM 最低放量倍数", 1.0, 2.0, float(params.get("volume_ratio_min", 1.2)), 0.05,
                    key="bt_canslim_vol"
                )
                params["near_high_52w_min_pct"] = st.slider(
                    "距52周高点下限(%)", -25.0, -2.0, float(params.get("near_high_52w_min_pct", -12.0)), 1.0,
                    key="bt_canslim_high"
                )
            elif sid == "turtle":
                params["breakout_short"] = st.slider(
                    "海龟短通道", 10, 40, int(params.get("breakout_short", 20)), 1, key="bt_turtle_s"
                )
                params["breakout_long"] = st.slider(
                    "海龟长通道", 30, 100, int(params.get("breakout_long", 55)), 1, key="bt_turtle_l"
                )
                params["trend_ma_days"] = st.slider(
                    "趋势均线天数", 20, 120, int(params.get("trend_ma_days", 50)), 5, key="bt_turtle_ma"
                )
            elif sid == "graham":
                params["pe_max"] = st.slider(
                    "格雷厄姆 PE 上限", 8.0, 40.0, float(params.get("pe_max", 20.0)), 1.0, key="bt_graham_pe"
                )
                params["pb_max"] = st.slider(
                    "格雷厄姆 PB 上限", 0.8, 6.0, float(params.get("pb_max", 2.5)), 0.1, key="bt_graham_pb"
                )
                params["trend_guard"] = st.checkbox(
                    "启用趋势保护（仅上升趋势）", value=bool(params.get("trend_guard", True)), key="bt_graham_trend"
                )
            elif sid == "livermore":
                params["breakout_days"] = st.slider(
                    "利弗莫尔关键点窗口", 10, 60, int(params.get("breakout_days", 20)), 1, key="bt_livermore_break"
                )
                params["rs_min"] = st.slider(
                    "利弗莫尔 最低RS", 50, 90, int(params.get("rs_min", 65)), 1, key="bt_livermore_rs"
                )
                params["trend_ma_days"] = st.slider(
                    "趋势均线天数", 20, 120, int(params.get("trend_ma_days", 50)), 5, key="bt_livermore_ma"
                )
            elif sid == "covell":
                params["breakout_days"] = st.slider(
                    "卡沃尔突破窗口", 20, 120, int(params.get("breakout_days", 55)), 1, key="bt_covell_break"
                )
                params["ma_days"] = st.slider(
                    "卡沃尔主趋势均线", 80, 260, int(params.get("ma_days", 200)), 5, key="bt_covell_ma"
                )
                params["vol_filter_min"] = st.slider(
                    "最低量能倍数", 0.5, 1.5, float(params.get("vol_filter_min", 0.7)), 0.05, key="bt_covell_vol"
                )
            elif sid == "dow":
                params["ma_fast"] = st.slider(
                    "道氏快均线", 20, 100, int(params.get("ma_fast", 50)), 5, key="bt_dow_fast"
                )
                params["ma_mid"] = st.slider(
                    "道氏中均线", 80, 220, int(params.get("ma_mid", 150)), 5, key="bt_dow_mid"
                )
                params["ma_slow"] = st.slider(
                    "道氏慢均线", 120, 320, int(params.get("ma_slow", 200)), 5, key="bt_dow_slow"
                )
                params["rs_min"] = st.slider(
                    "道氏 最低RS", 45, 85, int(params.get("rs_min", 60)), 1, key="bt_dow_rs"
                )
            elif sid == "lynch":
                params["pe_low"] = st.slider(
                    "林奇 PE下限", 2.0, 20.0, float(params.get("pe_low", 8.0)), 1.0, key="bt_lynch_pe_low"
                )
                params["pe_high"] = st.slider(
                    "林奇 PE上限", 15.0, 60.0, float(params.get("pe_high", 35.0)), 1.0, key="bt_lynch_pe_high"
                )
                params["rs_min"] = st.slider(
                    "林奇 最低RS", 40, 90, int(params.get("rs_min", 60)), 1, key="bt_lynch_rs"
                )
                params["trend_guard"] = st.checkbox(
                    "启用趋势过滤", value=bool(params.get("trend_guard", True)), key="bt_lynch_trend"
                )
            elif sid == "buffett":
                params["pe_max"] = st.slider(
                    "巴菲特 PE上限", 10.0, 60.0, float(params.get("pe_max", 35.0)), 1.0, key="bt_buffett_pe"
                )
                params["pb_max"] = st.slider(
                    "巴菲特 PB上限", 1.0, 10.0, float(params.get("pb_max", 6.0)), 0.1, key="bt_buffett_pb"
                )
                params["trend_guard"] = st.checkbox(
                    "启用价格趋势保护", value=bool(params.get("trend_guard", True)), key="bt_buffett_trend"
                )
            elif sid == "larry":
                params["breakout_days"] = st.slider(
                    "拉里突破窗口", 5, 40, int(params.get("breakout_days", 20)), 1, key="bt_larry_break"
                )
                params["volume_ratio_min"] = st.slider(
                    "拉里 最低放量倍数", 1.0, 2.5, float(params.get("volume_ratio_min", 1.2)), 0.05, key="bt_larry_vol"
                )
                params["rs_min"] = st.slider(
                    "拉里 最低RS", 35, 85, int(params.get("rs_min", 55)), 1, key="bt_larry_rs"
                )
            elif sid == "cn_yz_yangjia":
                params["breakout_days"] = st.slider("养家突破窗口", 6, 30, int(params.get("breakout_days", 12)), 1, key="bt_yangjia_break")
                params["volume_ratio_min"] = st.slider("养家合力量比", 1.0, 2.5, float(params.get("volume_ratio_min", 1.25)), 0.05, key="bt_yangjia_vol")
                params["pullback_max_pct"] = st.slider("分歧回撤上限(%)", 2.0, 12.0, float(params.get("pullback_max_pct", 6.0)), 0.5, key="bt_yangjia_pull")
                params["rs_min"] = st.slider("养家最低RS", 45, 85, int(params.get("rs_min", 60)), 1, key="bt_yangjia_rs")
                params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(params.get("allow_phase_start", True)), key="bt_yangjia_phase_start")
                params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(params.get("allow_phase_ferment", True)), key="bt_yangjia_phase_ferment")
                params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(params.get("allow_phase_climax", False)), key="bt_yangjia_phase_climax")
            elif sid == "cn_yz_zhaolao":
                params["leader_near_high_pct"] = st.slider("龙头距新高下限(%)", -20.0, -2.0, float(params.get("leader_near_high_pct", -8.0)), 1.0, key="bt_zhaolao_high")
                params["volume_ratio_min"] = st.slider("赵老哥放量倍数", 1.0, 2.8, float(params.get("volume_ratio_min", 1.35)), 0.05, key="bt_zhaolao_vol")
                params["rs_min"] = st.slider("赵老哥最低RS", 55, 95, int(params.get("rs_min", 75)), 1, key="bt_zhaolao_rs")
                params["breakout_days"] = st.slider("赵老哥突破窗口", 8, 40, int(params.get("breakout_days", 20)), 1, key="bt_zhaolao_break")
                params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(params.get("allow_phase_start", True)), key="bt_zhaolao_phase_start")
                params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(params.get("allow_phase_ferment", True)), key="bt_zhaolao_phase_ferment")
                params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(params.get("allow_phase_climax", False)), key="bt_zhaolao_phase_climax")
            elif sid == "cn_yz_asking":
                params["breakout_days"] = st.slider("Asking突破窗口", 8, 40, int(params.get("breakout_days", 18)), 1, key="bt_asking_break")
                params["volume_ratio_min"] = st.slider("Asking放量倍数", 1.0, 2.5, float(params.get("volume_ratio_min", 1.15)), 0.05, key="bt_asking_vol")
                params["rs_min"] = st.slider("Asking最低RS", 45, 90, int(params.get("rs_min", 65)), 1, key="bt_asking_rs")
                params["exit_ma_days"] = st.slider("Asking截亏均线", 5, 20, int(params.get("exit_ma_days", 10)), 1, key="bt_asking_exit")
                params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(params.get("allow_phase_start", True)), key="bt_asking_phase_start")
                params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(params.get("allow_phase_ferment", True)), key="bt_asking_phase_ferment")
                params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(params.get("allow_phase_climax", False)), key="bt_asking_phase_climax")
            elif sid == "cn_pm_danbin":
                params["pe_max"] = st.slider("但斌 PE上限", 15.0, 80.0, float(params.get("pe_max", 45.0)), 1.0, key="bt_danbin_pe")
                params["pb_max"] = st.slider("但斌 PB上限", 1.0, 15.0, float(params.get("pb_max", 8.0)), 0.1, key="bt_danbin_pb")
                params["rs_min"] = st.slider("但斌最低RS", 35, 85, int(params.get("rs_min", 55)), 1, key="bt_danbin_rs")
                params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(params.get("heat_min", 50.0)), 1.0, key="bt_danbin_heat")
                params["valuation_min"] = st.slider("估值分位下限", 20.0, 90.0, float(params.get("valuation_min", 35.0)), 1.0, key="bt_danbin_val")
                params["crowding_max"] = st.slider("拥挤度上限", 40.0, 95.0, float(params.get("crowding_max", 75.0)), 1.0, key="bt_danbin_crowd")
                params["trend_guard"] = st.checkbox("启用长期趋势保护", value=bool(params.get("trend_guard", True)), key="bt_danbin_trend")
            elif sid == "cn_pm_linyuan":
                params["pe_max"] = st.slider("林园 PE上限", 10.0, 70.0, float(params.get("pe_max", 35.0)), 1.0, key="bt_linyuan_pe")
                params["pb_max"] = st.slider("林园 PB上限", 1.0, 12.0, float(params.get("pb_max", 7.0)), 0.1, key="bt_linyuan_pb")
                params["rs_min"] = st.slider("林园最低RS", 35, 85, int(params.get("rs_min", 50)), 1, key="bt_linyuan_rs")
                params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(params.get("heat_min", 45.0)), 1.0, key="bt_linyuan_heat")
                params["valuation_min"] = st.slider("估值分位下限", 20.0, 90.0, float(params.get("valuation_min", 40.0)), 1.0, key="bt_linyuan_val")
                params["crowding_max"] = st.slider("拥挤度上限", 40.0, 95.0, float(params.get("crowding_max", 78.0)), 1.0, key="bt_linyuan_crowd")
                params["trend_guard"] = st.checkbox("启用趋势过滤", value=bool(params.get("trend_guard", True)), key="bt_linyuan_trend")
            elif sid == "cn_inst_qiuguolu":
                params["pe_max"] = st.slider("机构 PE上限", 10.0, 50.0, float(params.get("pe_max", 28.0)), 1.0, key="bt_qiuguolu_pe")
                params["pb_max"] = st.slider("机构 PB上限", 1.0, 10.0, float(params.get("pb_max", 5.0)), 0.1, key="bt_qiuguolu_pb")
                params["ma_days"] = st.slider("机构趋势均线", 60, 250, int(params.get("ma_days", 150)), 5, key="bt_qiuguolu_ma")
                params["rs_min"] = st.slider("机构最低RS", 40, 90, int(params.get("rs_min", 55)), 1, key="bt_qiuguolu_rs")
                params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(params.get("heat_min", 42.0)), 1.0, key="bt_qiuguolu_heat")
                params["valuation_min"] = st.slider("估值分位下限", 20.0, 95.0, float(params.get("valuation_min", 50.0)), 1.0, key="bt_qiuguolu_val")
                params["crowding_max"] = st.slider("拥挤度上限", 35.0, 90.0, float(params.get("crowding_max", 65.0)), 1.0, key="bt_qiuguolu_crowd")
                params["trend_guard"] = st.checkbox("启用趋势保护", value=bool(params.get("trend_guard", True)), key="bt_qiuguolu_trend")
            else:
                st.caption("该策略当前使用默认参数。")
            save_name = st.text_input(
                "保存回测模板名",
                value="",
                placeholder="例如：海龟保守版",
                key=f"bt_tpl_save_{sid}",
            )
            if st.button("💾 保存回测参数模板", key=f"bt_tpl_btn_{sid}", width="stretch"):
                if not save_name.strip():
                    st.warning("请先输入模板名")
                else:
                    ok = save_strategy_param_template(
                        sid, save_name.strip(), params, context="backtest"
                    )
                    if ok:
                        st.success(f"模板已保存：{save_name.strip()}")
                    else:
                        st.error("模板保存失败")
        strategy_params_map[sid] = params

catalog_meta = {
    x["id"]: {
        "region": x.get("region", "-"),
        "camp": x.get("camp", "-"),
        "name": x.get("name", x["id"]),
    }
    for x in catalog
}

run_clicked = st.button("🚀 运行回测", type="primary", width="stretch")
auto_run = bool(st.session_state.pop("_bt_auto_run", False))
if run_clicked or auto_run:
    auto_msg = st.session_state.pop("_bt_auto_run_msg", "")
    if auto_msg:
        st.info(auto_msg)
    progress = st.progress(0, text="准备中...")

    def update_progress(pct, text):
        progress.progress(pct, text=text)

    with st.spinner("回测运行中（可能需要 1-2 分钟）..."):
        if len(selected_ids) == 1:
            result, index_df = run_backtest(
                sample_size, start_str, update_progress,
                strategy_id=selected_ids[0],
                strategy_params=strategy_params_map.get(selected_ids[0]),
            )
            st.session_state["bt_result"] = result
            st.session_state["bt_index"] = index_df
            st.session_state["bt_multi"] = False
        else:
            results, index_df = run_backtest_multi(
                selected_ids, sample_size, start_str, update_progress,
                strategy_params_map=strategy_params_map,
            )
            st.session_state["bt_results_multi"] = results
            st.session_state["bt_index"] = index_df
            st.session_state["bt_multi"] = True

    progress.empty()
    st.success("回测完成!")

# Display Results
if st.session_state.get("bt_multi"):
    results = st.session_state.get("bt_results_multi", {})
    index_df = st.session_state.get("bt_index")
    if not results:
        st.info("暂无多策略结果")
        st.stop()

    st.divider()
    st.markdown("### 多策略对比")
    rows = []
    for sid, r in results.items():
        level, note = _practical_confidence(r.total_trades, r.win_rate)
        rows.append({
            "策略": getattr(r, "strategy_name", sid),
            "总收益率": f"{r.total_return:.2%}",
            "年化收益": f"{r.annual_return:.2%}",
            "最大回撤": f"{r.max_drawdown:.2%}",
            "夏普": r.sharpe_ratio,
            "Sortino": getattr(r, "sortino_ratio", 0.0),
            "Calmar": getattr(r, "calmar_ratio", 0.0),
            "准确率(胜率)": f"{r.win_rate:.1%}",
            "交易次数": r.total_trades,
            "实践可信度": level,
            "验证说明": note,
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.markdown("#### 准确率对比（实践验证）")
    acc_df = pd.DataFrame(rows)
    if not acc_df.empty:
        acc_df["准确率值"] = acc_df["准确率(胜率)"].str.replace("%", "", regex=False).astype(float)
        fig_acc = go.Figure(data=[go.Bar(
            x=acc_df["策略"],
            y=acc_df["准确率值"],
            text=acc_df["准确率(胜率)"],
            textposition="outside",
            marker_color=["#43A047" if v >= 55 else "#FB8C00" if v >= 50 else "#E53935" for v in acc_df["准确率值"]],
        )])
        fig_acc.update_layout(
            template="plotly_white",
            margin=dict(l=30, r=20, t=35, b=30),
            yaxis_title="准确率 (%)",
            xaxis_title="策略",
        )
        st.plotly_chart(fig_acc, width="stretch")

    # Group summary: 国内/海外 and 游资/私募/机构/大师
    g_rows_region = []
    for region in sorted({catalog_meta.get(sid, {}).get("region", "-") for sid in results.keys()}):
        members = [results[sid] for sid in results if catalog_meta.get(sid, {}).get("region", "-") == region]
        if not members:
            continue
        g_rows_region.append({
            "分组": region,
            "策略数": len(members),
            "平均年化收益": f"{sum(r.annual_return for r in members)/len(members):.2%}",
            "平均最大回撤": f"{sum(r.max_drawdown for r in members)/len(members):.2%}",
            "平均夏普": round(sum(r.sharpe_ratio for r in members)/len(members), 2),
        })
    g_rows_camp = []
    for camp in sorted({catalog_meta.get(sid, {}).get("camp", "-") for sid in results.keys()}):
        members = [results[sid] for sid in results if catalog_meta.get(sid, {}).get("camp", "-") == camp]
        if not members:
            continue
        g_rows_camp.append({
            "分组": camp,
            "策略数": len(members),
            "平均年化收益": f"{sum(r.annual_return for r in members)/len(members):.2%}",
            "平均最大回撤": f"{sum(r.max_drawdown for r in members)/len(members):.2%}",
            "平均夏普": round(sum(r.sharpe_ratio for r in members)/len(members), 2),
        })

    gc1, gc2 = st.columns(2)
    with gc1:
        st.markdown("#### 国内 vs 海外")
        if g_rows_region:
            st.dataframe(pd.DataFrame(g_rows_region), width="stretch", hide_index=True)
    with gc2:
        st.markdown("#### 游资 / 私募 / 机构 / 大师")
        if g_rows_camp:
            st.dataframe(pd.DataFrame(g_rows_camp), width="stretch", hide_index=True)

    fig = go.Figure()
    for sid, r in results.items():
        if r.equity_curve is None or r.equity_curve.empty:
            continue
        nav = r.equity_curve["total_equity"] / r.initial_capital
        fig.add_trace(go.Scatter(
            x=r.equity_curve["date"],
            y=nav,
            mode="lines",
            name=getattr(r, "strategy_name", sid),
            line=dict(width=2),
        ))
    fig.update_layout(
        title="多策略净值曲线对比",
        template="plotly_white",
        margin=dict(l=40, r=20, t=55, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.markdown("### 策略相关性矩阵")
    st.caption("日收益率 Pearson 相关系数：低相关意味着策略互补性好，适合组合配置。")
    fig_corr = plot_strategy_correlation(results)
    st.plotly_chart(fig_corr, width="stretch")

    st.divider()
    st.markdown("### 策略内诊断")
    st.caption("按买入/卖出逻辑分解绩效，定位每套策略真正有效的触发条件。")
    for sid, r in results.items():
        trades = getattr(r, "trades", [])
        if not trades:
            continue
        entry_diag, exit_diag = _build_reason_diagnostics(trades)
        with st.expander(f"{getattr(r, 'strategy_name', sid)} 逻辑诊断", expanded=False):
            _render_top3_cards(entry_diag, exit_diag)
            st.markdown("**情绪阶段时间轴**")
            _plot_emotion_timeline(
                getattr(r, "phase_timeline", pd.DataFrame()),
                "回测期间情绪阶段分布（按买点）",
            )
            st.markdown("**三因子诊断图（热度/估值/拥挤）**")
            _plot_factor_diagnostics(
                getattr(r, "factor_samples", pd.DataFrame()),
                "买点三因子散点诊断",
                getattr(r, "strategy_params", {}),
            )
            _render_suggestion_block(
                f"multi_{sid}",
                sid,
                getattr(r, "factor_samples", pd.DataFrame()),
                getattr(r, "strategy_params", {}),
                allow_apply=False,
            )
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**买入逻辑贡献**")
                st.dataframe(
                    _format_diag_df(entry_diag, "买入逻辑"),
                    width="stretch",
                    hide_index=True,
                    height=min(len(entry_diag) * 35 + 40, 320),
                )
            with c2:
                st.markdown("**卖出逻辑贡献**")
                st.dataframe(
                    _format_diag_df(exit_diag, "卖出逻辑"),
                    width="stretch",
                    hide_index=True,
                    height=min(len(exit_diag) * 35 + 40, 320),
                )

elif "bt_result" in st.session_state:
    result = st.session_state["bt_result"]
    index_df = st.session_state.get("bt_index")

    # Key Metrics
    st.divider()
    st.markdown("### 核心指标")

    st.caption(f"当前策略：{getattr(result, 'strategy_name', 'SEPA / 股票魔法师')}")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("总收益率", f"{result.total_return:.2%}",
              f"年化 {result.annual_return:.2%}")
    m2.metric("最大回撤", f"{result.max_drawdown:.2%}")
    m3.metric("夏普比率", f"{result.sharpe_ratio:.2f}")
    m4.metric("胜率", f"{result.win_rate:.1%}")
    m5.metric("盈亏比", f"{result.profit_loss_ratio:.2f}")
    m6.metric("交易次数", f"{result.total_trades}",
              f"平均持仓 {result.avg_hold_days:.0f} 天")
    m7, m8, m9 = st.columns(3)
    m7.metric("Sortino", f"{getattr(result, 'sortino_ratio', 0.0):.2f}")
    m8.metric("Calmar", f"{getattr(result, 'calmar_ratio', 0.0):.2f}")
    m9.metric("换手率", f"{getattr(result, 'turnover_ratio', 0.0):.2f}x")
    level, note = _practical_confidence(result.total_trades, result.win_rate)
    pc1, pc2 = st.columns(2)
    pc1.metric("实践准确率(胜率)", f"{result.win_rate:.1%}")
    pc2.metric("实践可信度", level, note)

    st.divider()

    # Charts
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 资金曲线", "📉 回撤分析", "🗓️ 月度收益", "🎯 退出分析", "📊 盈亏分布",
    ])

    with tab1:
        if not result.equity_curve.empty:
            fig = plot_equity_curve(result.equity_curve, result.initial_capital, index_df)
            st.plotly_chart(fig, width="stretch")

    with tab2:
        if not result.equity_curve.empty:
            fig = plot_drawdown(result.equity_curve)
            st.plotly_chart(fig, width="stretch")

    with tab3:
        if not result.equity_curve.empty:
            fig = plot_monthly_heatmap(result.equity_curve)
            st.plotly_chart(fig, width="stretch")

    with tab4:
        if result.trades:
            fig = plot_exit_reasons(result.trades)
            st.plotly_chart(fig, width="stretch")

    with tab5:
        if result.trades:
            fig = plot_pnl_distribution(result.trades)
            st.plotly_chart(fig, width="stretch")

    # Detailed Metrics
    st.divider()
    st.markdown("### 详细统计")

    dc1, dc2 = st.columns(2)
    with dc1:
        st.markdown(f"""
        | 指标 | 值 |
        |------|-----|
        | 初始资金 | ¥{result.initial_capital:,.0f} |
        | 最终资金 | ¥{result.final_capital:,.0f} |
        | 总收益率 | {result.total_return:.2%} |
        | 年化收益 | {result.annual_return:.2%} |
        | 最大回撤 | {result.max_drawdown:.2%} |
        | 夏普比率 | {result.sharpe_ratio:.2f} |
        | Sortino | {getattr(result, 'sortino_ratio', 0.0):.2f} |
        | Calmar | {getattr(result, 'calmar_ratio', 0.0):.2f} |
        """)

    with dc2:
        st.markdown(f"""
        | 指标 | 值 |
        |------|-----|
        | 总交易 | {result.total_trades} 笔 |
        | 盈利 | {result.winning_trades} 笔 |
        | 亏损 | {result.losing_trades} 笔 |
        | 胜率 | {result.win_rate:.1%} |
        | 平均盈利 | {result.avg_win_pct:.2%} |
        | 平均亏损 | {result.avg_loss_pct:.2%} |
        | 换手率 | {getattr(result, 'turnover_ratio', 0.0):.2f}x |
        """)

    st.divider()
    st.markdown("### 策略内诊断")
    st.caption("同一策略内部，按触发逻辑分解绩效（哪些买点/卖点真正有效）。")
    entry_diag, exit_diag = _build_reason_diagnostics(result.trades)
    _render_top3_cards(entry_diag, exit_diag)
    st.markdown("**情绪阶段时间轴**")
    _plot_emotion_timeline(
        getattr(result, "phase_timeline", pd.DataFrame()),
        "回测期间情绪阶段分布（按买点）",
    )
    st.markdown("**三因子诊断图（热度/估值/拥挤）**")
    _plot_factor_diagnostics(
        getattr(result, "factor_samples", pd.DataFrame()),
        "买点三因子散点诊断",
        getattr(result, "strategy_params", {}),
    )
    _render_suggestion_block(
        "single",
        getattr(result, "strategy_id", ""),
        getattr(result, "factor_samples", pd.DataFrame()),
        getattr(result, "strategy_params", {}),
        allow_apply=True,
    )
    st.markdown("---")
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**买入逻辑贡献**")
        if entry_diag.empty:
            st.info("暂无买入逻辑诊断数据")
        else:
            st.dataframe(
                _format_diag_df(entry_diag, "买入逻辑"),
                width="stretch",
                hide_index=True,
                height=min(len(entry_diag) * 35 + 40, 360),
            )
    with d2:
        st.markdown("**卖出逻辑贡献**")
        if exit_diag.empty:
            st.info("暂无卖出逻辑诊断数据")
        else:
            st.dataframe(
                _format_diag_df(exit_diag, "卖出逻辑"),
                width="stretch",
                hide_index=True,
                height=min(len(exit_diag) * 35 + 40, 360),
            )

    # Trade Log
    if result.trades:
        with st.expander("查看全部交易记录"):
            import pandas as pd
            trade_data = []
            for t in result.trades:
                trade_data.append({
                    "策略": getattr(t, "strategy_id", ""),
                    "代码": t.code, "买入日": t.entry_date,
                    "买入价": t.entry_price, "卖出日": t.exit_date,
                    "卖出价": t.exit_price, "盈亏%": f"{t.pnl_pct:.1%}",
                    "天数": t.hold_days,
                    "买入逻辑": str(getattr(t, "entry_reason", ""))[:36],
                    "卖出逻辑": t.exit_reason[:36],
                })
            st.dataframe(pd.DataFrame(trade_data), width="stretch", hide_index=True)

    # ---- 蒙特卡洛鲁棒性检验 ----
    st.divider()
    st.markdown("### 🎲 蒙特卡洛鲁棒性检验")
    st.caption("对交易序列随机重排 1000 次，评估策略表现是否显著优于随机。")
    with st.expander("运行蒙特卡洛模拟", expanded=False):
        mc_n = st.slider("模拟次数", 200, 3000, 1000, 100, key="mc_sim_n")
        if st.button("🎲 运行蒙特卡洛", key="mc_run_btn"):
            with st.spinner("蒙特卡洛模拟中..."):
                mc = MonteCarloSimulator(n_simulations=mc_n, initial_capital=result.initial_capital)
                mc_result = mc.run(result)
            st.session_state["mc_result"] = mc_result
        mc_result = st.session_state.get("mc_result")
        if mc_result and mc_result.n_simulations > 0:
            mc1, mc2 = st.columns([2, 1])
            with mc1:
                st.dataframe(MonteCarloSimulator.summarize(mc_result), width="stretch", hide_index=True)
            with mc2:
                grade = mc_result.robustness_grade
                if grade == "优秀":
                    st.success(f"鲁棒性等级：**{grade}**")
                elif grade == "良好":
                    st.info(f"鲁棒性等级：**{grade}**")
                elif grade == "一般":
                    st.warning(f"鲁棒性等级：**{grade}**")
                else:
                    st.error(f"鲁棒性等级：**{grade}**")
                st.caption(mc_result.robustness_note)

    # ---- Walk-Forward 样本外验证 ----
    st.divider()
    st.markdown("### 📐 Walk-Forward 样本外验证")
    st.caption("滚动窗口回测：训练期优化，验证期检验，评估策略是否过拟合。")
    with st.expander("运行 Walk-Forward 分析", expanded=False):
        wf_train = st.slider("训练期(月)", 6, 24, 12, 3, key="wf_train_m")
        wf_test = st.slider("验证期(月)", 3, 12, 6, 3, key="wf_test_m")
        if st.button("📐 运行 Walk-Forward", key="wf_run_btn"):
            with st.spinner("Walk-Forward 分析中..."):
                from services.stock_service import get_strategy as _get_strategy, get_fetcher as _get_fetcher
                from services.stock_service import get_stock_list as _get_sl, get_index_data as _get_idx
                _sl = _get_sl()
                _sample = _sl.sample(n=min(sample_size, len(_sl)), random_state=2024)
                _all_data = _get_fetcher().get_all_daily_data(_sample)
                _idx = _get_idx()
                if _all_data:
                    _strategy = _get_strategy()
                    _sig, _mkt = _strategy.generate_signals_for_backtest(_all_data, _idx)
                    sid0 = selected_ids[0] if selected_ids else "sepa"
                    from strategy_profiles import apply_backtest_profile, get_strategy_default_params as _gdp
                    _params = _gdp(sid0)
                    _profiled = {c: apply_backtest_profile(d.copy(), sid0, None, _params) for c, d in _sig.items()}
                    wf = WalkForward(train_months=wf_train, test_months=wf_test)
                    wf_windows = wf.run(_profiled, market_regime_df=_mkt)
                    st.session_state["wf_windows"] = wf_windows
                else:
                    st.warning("无法获取样本数据，Walk-Forward 跳过。")
        wf_windows = st.session_state.get("wf_windows")
        if wf_windows:
            wf_df = WalkForward.summarize(wf_windows)
            st.dataframe(wf_df, width="stretch", hide_index=True)
            train_sharpes = [w.train_result.sharpe_ratio for w in wf_windows]
            test_sharpes = [w.test_result.sharpe_ratio for w in wf_windows]
            avg_decay = sum(t / max(tr, 0.01) for t, tr in zip(test_sharpes, train_sharpes)) / max(len(wf_windows), 1)
            if avg_decay >= 0.7:
                st.success(f"平均衰减率 {avg_decay:.0%} — 策略样本外表现稳健")
            elif avg_decay >= 0.4:
                st.warning(f"平均衰减率 {avg_decay:.0%} — 策略有一定过拟合风险")
            else:
                st.error(f"平均衰减率 {avg_decay:.0%} — 策略可能严重过拟合")

else:
    st.info("点击「运行回测」开始历史数据验证")

    st.markdown("""
    #### 回测说明
    - 支持 SEPA / CAN SLIM / 海龟 / 价值等多策略
    - 多策略对比时使用同一股票样本与同一成本模型
    - 回测包含 A 股特有规则：T+1、涨跌停、印花税
    - 风控规则：统一基础风控（便于横向比较）
    - 市场环境过滤：弱市自动减仓
    """)
