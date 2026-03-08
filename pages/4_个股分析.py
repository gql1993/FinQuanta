"""个股分析 - 交互式 K 线 + VCP 检测 + 趋势模板"""
import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="个股分析", page_icon="📉", layout="wide")

from services.stock_service import (
    get_stock_names, analyze_stock, get_company_profile, generate_prediction,
    generate_strategy_predictions, get_strategy_catalog, get_strategy_params, get_config
)
from ui.charts import plot_candlestick, plot_vcp_overlay, plot_rs_gauge
from ui.components import trend_check_item

st.title("📉 个股分析")


def _latest_cache_time_for_code(code: str) -> str:
    cache_dir = get_config().data.cache_dir
    path = os.path.join(cache_dir, f"daily_{code}.csv")
    if not os.path.exists(path):
        return ""
    try:
        ts = os.path.getmtime(path)
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""

# Resolve initial code: query param > session_state > default
_default_code = "603881"
qp = st.query_params.get("code", "")
if qp:
    _default_code = qp
elif st.session_state.get("detail_code"):
    _default_code = st.session_state["detail_code"]

if "analysis_code_input" not in st.session_state:
    st.session_state["analysis_code_input"] = _default_code

# Stock Input
col_input, col_quick = st.columns([2, 3])
with col_input:
    st.text_input("输入股票代码", key="analysis_code_input", placeholder="例如: 600519")
with col_quick:
    st.markdown("<br>", unsafe_allow_html=True)
    quick_codes = ["603881", "002975", "688001", "300604", "688498", "002150"]
    cols = st.columns(len(quick_codes))
    for i, qc in enumerate(quick_codes):
        if cols[i].button(qc, key=f"q_{qc}", width="stretch"):
            st.session_state["analysis_code_input"] = qc
            st.rerun()

code = str(st.session_state.get("analysis_code_input", "")).strip()

if not code:
    st.info("请输入股票代码开始分析")
    st.stop()

ctl1, ctl2 = st.columns([1, 3])
force_refresh_one = ctl1.button("🔄 强制刷新该股数据", width="stretch")
if force_refresh_one:
    st.session_state["analysis_force_once"] = True
prefer_latest = ctl2.checkbox("优先拉取最新数据", value=False, key="analysis_prefer_latest")
manual_force = bool(st.session_state.pop("analysis_force_once", False))

# 自动策略：先缓存秒开，再按节流周期尝试拉新。
with st.spinner(f"分析 {code} 中..."):
    result = analyze_stock(code, force_refresh=False)

_updated_from_latest = False
_auto_refresh_interval_sec = 300
_last_refresh_map = st.session_state.setdefault("analysis_last_refresh_ts", {})
_last_ts = float(_last_refresh_map.get(code, 0.0))
_need_auto_refresh = prefer_latest and (time.time() - _last_ts >= _auto_refresh_interval_sec)

if manual_force or _need_auto_refresh:
    with st.spinner("正在拉取最新数据..."):
        latest_result = analyze_stock(code, force_refresh=True)
    if latest_result is not None:
        result = latest_result
        _last_refresh_map[code] = time.time()
        _updated_from_latest = True

if result is None:
    st.error(f"无法获取 {code} 的数据（可能是接口波动或缓存不足）")
    latest_cache = _latest_cache_time_for_code(code)
    if latest_cache:
        st.caption(f"最近缓存日期：{latest_cache}")
    else:
        st.caption("最近缓存日期：无（本地未找到该股票日线缓存）")
    st.caption("可点击上方“强制刷新该股数据”重试。")
    st.stop()

if _updated_from_latest:
    st.success("已自动更新为最新可用数据。")
elif prefer_latest:
    st.caption("自动拉新策略已启用：先展示缓存，再周期性尝试更新最新数据。")

# Header
name = result["name"]
close = result["close"]
st.markdown(f"## {code} {name}　　现价 ¥{close:.2f}")

# Key metrics
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("MA50", f"{result['ma50']}", f"{'上方' if close > result['ma50'] else '下方'}")
m2.metric("MA150", f"{result['ma150']}", f"{'上方' if close > result['ma150'] else '下方'}")
m3.metric("MA200", f"{result['ma200']}", f"{'上方' if close > result['ma200'] else '下方'}")
m4.metric("52周高点", f"{result['high_52w']}", f"{(close/result['high_52w']-1)*100:+.1f}%")
m5.metric("52周低点", f"{result['low_52w']}", f"{(close/result['low_52w']-1)*100:+.1f}%")

st.divider()

# Tabs
tab_kline, tab_vcp, tab_trend, tab_profile = st.tabs(["K 线图", "VCP 形态", "趋势模板", "公司详情"])

with tab_kline:
    df = result["df"]
    kc1, kc2 = st.columns([3, 1])
    with kc1:
        period = st.select_slider("显示周期", options=[60, 120, 250, 500, "全部"],
                                   value=250, key="kline_period")
    with kc2:
        show_pred = st.checkbox("显示预测线", value=True, key="show_prediction")

    st.markdown("##### 策略预测叠加")
    catalog = get_strategy_catalog()
    sid_to_name = {x["id"]: x["name"] for x in catalog}
    sid_to_label = {
        x["id"]: f"[{x.get('region', '-')}/{x.get('camp', '-')}] {x['name']}"
        for x in catalog
    }
    all_sids = [x["id"] for x in catalog]
    domestic_sids = [x["id"] for x in catalog if "国内" in str(x.get("region", ""))]
    overseas_sids = [x["id"] for x in catalog if "海外" in str(x.get("region", ""))]
    pred_col1, pred_col2 = st.columns([3, 2])
    with pred_col1:
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("全选全部", key="kline_pred_all", width="stretch"):
            st.session_state["kline_pred_strategy_ids"] = all_sids
            st.rerun()
        if q2.button("全选国内", key="kline_pred_cn", width="stretch"):
            st.session_state["kline_pred_strategy_ids"] = domestic_sids
            st.rerun()
        if q3.button("全选海外", key="kline_pred_os", width="stretch"):
            st.session_state["kline_pred_strategy_ids"] = overseas_sids
            st.rerun()
        if q4.button("清空", key="kline_pred_clear", width="stretch"):
            st.session_state["kline_pred_strategy_ids"] = []
            st.rerun()

        selected_strategy_ids = st.multiselect(
            "选择要显示的策略预测",
            options=all_sids,
            default=["sepa", "canslim"],
            format_func=lambda x: sid_to_label.get(x, sid_to_name.get(x, x)),
            key="kline_pred_strategy_ids",
        )
        st.caption(f"当前已选 {len(selected_strategy_ids)} 个策略（中线模式下支持同时对比多策略）")
    with pred_col2:
        overlay_mode = st.radio(
            "显示方式",
            ["仅中线(清晰)", "中线+单策略区间"],
            horizontal=False,
            key="kline_pred_overlay_mode",
        )
    focus_strategy_id = None
    if overlay_mode == "中线+单策略区间" and selected_strategy_ids:
        focus_strategy_id = st.selectbox(
            "区间展示策略",
            selected_strategy_ids,
            format_func=lambda x: sid_to_name.get(x, x),
            key="kline_pred_focus_sid",
        )
    style_col1, style_col2 = st.columns(2)
    with style_col1:
        strategy_line_opacity = st.slider(
            "策略线透明度",
            min_value=0.2, max_value=1.0, value=0.85, step=0.05,
            key="kline_pred_line_opacity",
        )
    with style_col2:
        strategy_line_width = st.slider(
            "策略线粗细",
            min_value=1.0, max_value=4.0, value=2.2, step=0.2,
            key="kline_pred_line_width",
        )

    if period != "全部":
        df_show = df.iloc[-period:]
    else:
        df_show = df

    # Generate prediction
    pred_data = None
    strategy_pred_list = []
    if show_pred:
        with st.spinner("计算预测..."):
            pred_data = generate_prediction(df)
            if selected_strategy_ids:
                params_map = {sid: get_strategy_params(sid) for sid in selected_strategy_ids}
                pred_map = generate_strategy_predictions(
                    df, selected_strategy_ids, strategy_params_map=params_map, code=code, forecast_days=20
                )
                for sid in selected_strategy_ids:
                    p = pred_map.get(sid)
                    if not p:
                        continue
                    p["_show_band"] = (overlay_mode == "中线+单策略区间" and sid == focus_strategy_id)
                    p["_show_divergence"] = (sid == focus_strategy_id)
                    strategy_pred_list.append(p)

    fig = plot_candlestick(df_show, mas=[50, 150, 200],
                            title=f"{code} {name} K线图",
                            prediction=pred_data if show_pred else None,
                            predictions=strategy_pred_list if show_pred else None,
                            strategy_line_width=strategy_line_width,
                            strategy_line_opacity=strategy_line_opacity)
    st.plotly_chart(fig, width="stretch")

    # Prediction analysis panel
    if show_pred and pred_data:
        st.divider()
        st.markdown("#### 预测分析")

        ac1, ac2, ac3, ac4 = st.columns(4)
        pred_chg = pred_data.get("pred_20d_change_pct", 0)
        pred_price = pred_data.get("pred_20d_price", 0)
        recent_div = pred_data.get("recent_divergence_pct", 0)
        vol = pred_data.get("volatility", 0)

        color = "normal" if pred_chg >= 0 else "inverse"
        ac1.metric("20日预测价", f"¥{pred_price:.2f}", f"{pred_chg:+.2f}%", delta_color=color)
        ac2.metric("近5日偏差", f"{recent_div:+.2f}%",
                    "预测偏高" if recent_div < -2 else ("预测偏低" if recent_div > 2 else "基本一致"))
        ac3.metric("波动率", f"¥{vol:.2f}")
        ac4.metric("背离次数", f"{len(pred_data.get('divergences', []))} 次")

        # Divergence explanation
        divs = pred_data.get("divergences", [])
        if divs or abs(recent_div) > 2:
            st.markdown("##### 实际走势 vs 预测背离分析")

            if recent_div > 3:
                st.success(
                    f"📈 **实际走势强于预测** (偏差 +{recent_div:.1f}%)\n\n"
                    f"可能原因：突发利好、资金集中流入、板块联动效应。"
                    f"如果伴随放量突破，属于 SEPA 策略中的强势信号，可继续持有。"
                )
            elif recent_div < -3:
                st.error(
                    f"📉 **实际走势弱于预测** (偏差 {recent_div:.1f}%)\n\n"
                    f"可能原因：利空消息、主力出货、大盘拖累。"
                    f"按《股票魔法师》第10章，如果跌破止损线应无条件离场；"
                    f"如果趋势模板条件被打破（跌破MA50），应提高警惕。"
                )
            else:
                st.info(
                    f"📊 实际走势与预测基本一致 (偏差 {recent_div:+.1f}%)，模型跟踪良好。"
                )

            if divs:
                with st.expander(f"查看近期 {len(divs)} 个背离点详情"):
                    import pandas as pd
                    div_df = pd.DataFrame(divs)
                    div_df.columns = ["日期", "实际价", "预测价", "偏差%", "方向"]
                    st.dataframe(div_df, width="stretch", hide_index=True)
        else:
            st.info("预测线与实际走势吻合度良好，无显著背离。")

    if strategy_pred_list:
        st.divider()
        st.markdown("#### 多策略预测分析")
        rows = []
        for p in strategy_pred_list:
            rows.append({
                "策略": p.get("strategy_name", p.get("strategy_id", "")),
                "预测来源版本": p.get("prediction_version", "-"),
                "20日预测价": p.get("pred_20d_price", "-"),
                "20日预测涨跌%": f"{p.get('pred_20d_change_pct', 0):+.2f}%",
                "策略偏置%": f"{p.get('strategy_bias_pct', 0):+.2f}%",
                "近5日偏差%": f"{p.get('recent_divergence_pct', 0):+.2f}%",
            })
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

with tab_vcp:
    vcp = result["vcp"]
    c1, c2 = st.columns([2, 1])

    with c1:
        fig_vcp = plot_vcp_overlay(df, vcp, title=f"{code} {name} VCP 分析")
        st.plotly_chart(fig_vcp, width="stretch")

    with c2:
        st.markdown("#### VCP 检测结果")
        if vcp["has_vcp"]:
            st.success("✅ 发现 VCP 形态")
        else:
            st.warning("❌ 未发现 VCP 形态")

        st.markdown(f"- **收缩次数**: {vcp.get('num_contractions', 0)}")
        st.markdown(f"- **枢纽价格**: {vcp.get('pivot_price', 0):.2f}")
        st.markdown(f"- **波动率斜率**: {vcp.get('vol_slope', 0):.4f}")
        st.markdown(f"- **成交量萎缩**: {'是' if vcp.get('volume_contracting') else '否'}")

        if vcp.get("breakout_today"):
            st.success("🔥 **今日突破枢纽点！**")
        else:
            pivot = vcp.get("pivot_price", 0)
            if pivot > 0:
                dist = (close - pivot) / pivot * 100
                st.info(f"距枢纽: {dist:+.1f}%")

with tab_trend:
    t1, t2 = st.columns([1, 1])

    with t1:
        st.markdown("#### 趋势模板 8 大条件")
        td = result.get("trend_details", {})

        checks = [
            ("股价 > MA150 且 MA200", td.get("condition_1_above_ma150_200", False)),
            ("MA150 > MA200", td.get("condition_2_ma150_gt_ma200", False)),
            ("MA200 上升趋势", td.get("condition_3_ma200_rising", False)),
            ("MA50 > MA150 且 MA200", td.get("condition_4_ma50_gt_ma150_200", False)),
            ("股价 > MA50", td.get("condition_5_above_ma50", False)),
            ("股价 > 52周低点×125%", td.get("condition_6_above_52w_low_25pct", False)),
            ("股价距52周高点≤25%", td.get("condition_7_within_52w_high_25pct", False)),
            ("RS 评级 ≥ 70", td.get("condition_8_rs_rating", False)),
        ]
        for label, passed in checks:
            trend_check_item(label, passed)

        if result["trend_pass"]:
            st.success("✅ 通过趋势模板！处于 Stage 2 上升阶段")
        else:
            passed_count = sum(1 for _, p in checks if p)
            st.warning(f"通过 {passed_count}/8 个条件")

    with t2:
        st.markdown("#### RS 相对强度评级")
        fig_rs = plot_rs_gauge(result["rs_rating"])
        st.plotly_chart(fig_rs, width="stretch")

        if result["rs_rating"] >= 90:
            st.success("RS ≥ 90: 全市场领涨股")
        elif result["rs_rating"] >= 70:
            st.info("RS ≥ 70: 强势股")
        else:
            st.warning(f"RS = {result['rs_rating']:.0f}: 相对强度不足")

with tab_profile:
    with st.spinner("加载公司详情..."):
        profile = get_company_profile(code)

    if profile is None:
        st.warning("无法获取公司详情")
    else:
        st.markdown(f"#### {profile.get('name', code)} ({code})")

        def _fmt_market_cap(val):
            if val == "-" or val is None:
                return "-"
            try:
                v = float(val)
                if v >= 1e8:
                    return f"{v / 1e8:.2f} 亿"
                elif v >= 1e4:
                    return f"{v / 1e4:.2f} 万"
                return f"{v:.0f}"
            except (ValueError, TypeError):
                return str(val)

        pc1, pc2 = st.columns(2)

        with pc1:
            st.markdown("##### 基本信息")
            info_items = {
                "行业": profile.get("行业", "-"),
                "上市时间": profile.get("上市时间", "-"),
                "总市值": _fmt_market_cap(profile.get("总市值", "-")),
                "流通市值": _fmt_market_cap(profile.get("流通市值", "-")),
                "总股本": _fmt_market_cap(profile.get("总股本", "-")),
                "流通股": _fmt_market_cap(profile.get("流通股", "-")),
            }
            for k, v in info_items.items():
                st.markdown(f"- **{k}**: {v}")

        with pc2:
            st.markdown("##### 估值指标")
            pe = profile.get("市盈率", "-")
            pb = profile.get("市净率", "-")

            vm1, vm2 = st.columns(2)
            vm1.metric("市盈率 (PE)", f"{pe}" if pe != "-" else "-")
            vm2.metric("市净率 (PB)", f"{pb}" if pb != "-" else "-")

            if pe != "-" and pb != "-":
                try:
                    pe_f, pb_f = float(pe), float(pb)
                    if pe_f < 0:
                        st.warning("PE 为负 — 公司当前亏损")
                    elif pe_f < 20:
                        st.info(f"PE {pe_f:.1f} — 估值偏低")
                    elif pe_f < 50:
                        st.info(f"PE {pe_f:.1f} — 估值适中")
                    else:
                        st.warning(f"PE {pe_f:.1f} — 估值较高")
                except (ValueError, TypeError):
                    pass

        fin_table = profile.get("financial_table")
        if fin_table is not None and not fin_table.empty:
            st.divider()
            st.markdown("##### 近期财务摘要")
            st.dataframe(fin_table, width="stretch", hide_index=True)
