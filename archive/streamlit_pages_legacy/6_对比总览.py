"""对比总览 - 选股对比 + 回测对比 + 准确率验证联动页"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="对比总览", page_icon="🧭", layout="wide")

from services.stock_service import (
    get_strategy_catalog,
    get_strategy_params,
    run_screening,
    run_backtest_multi,
    load_strategy_param_templates,
    save_strategy_param_template,
    delete_strategy_param_template,
    rename_strategy_param_template,
)


def _pick_existing(preferred_ids: list[str], existing_ids: set[str]) -> list[str]:
    return [sid for sid in preferred_ids if sid in existing_ids]


def _build_strategy_templates(catalog_items: list[dict]) -> dict[str, list[str]]:
    ids_all = [x["id"] for x in catalog_items]
    id_set = set(ids_all)

    overseas = [x["id"] for x in catalog_items if "海外" in str(x.get("region", ""))]
    domestic = [x["id"] for x in catalog_items if "国内" in str(x.get("region", ""))]
    yz = [x["id"] for x in catalog_items if "游资" in str(x.get("camp", ""))]
    pm = [x["id"] for x in catalog_items if "私募" in str(x.get("camp", ""))]
    inst = [x["id"] for x in catalog_items if "机构" in str(x.get("camp", ""))]

    templates = {
        "默认对比组（SEPA/CANSLIM/海龟）": _pick_existing(["sepa", "canslim", "turtle"], id_set),
        "海外大师组": overseas,
        "国内游资组": yz,
        "国内私募组": pm,
        "国内机构组": inst,
        "国内全策略": domestic,
        "稳健组合（价值+成长）": _pick_existing(["graham", "buffett", "lynch", "canslim"], id_set),
        "趋势动量组合（突破/波段）": _pick_existing(
            ["sepa", "turtle", "livermore", "covell", "larry_williams"], id_set
        ),
        "全市场全策略": ids_all,
    }
    return {name: ids for name, ids in templates.items() if ids}


def _load_custom_group_templates(valid_ids: set[str]) -> dict[str, list[str]]:
    raw = load_strategy_param_templates(context="overview_groups")
    store = raw.get("__strategy_group__", {})
    if not isinstance(store, dict):
        return {}
    result = {}
    for name, payload in store.items():
        if not isinstance(name, str) or not isinstance(payload, dict):
            continue
        ids = payload.get("strategy_ids", [])
        if not isinstance(ids, list):
            continue
        cleaned = []
        seen = set()
        for sid in ids:
            if sid in valid_ids and sid not in seen:
                seen.add(sid)
                cleaned.append(sid)
        if cleaned:
            result[name] = cleaned
    return result


def _save_custom_group_template(name: str, strategy_ids: list[str]) -> bool:
    return save_strategy_param_template(
        strategy_id="__strategy_group__",
        template_name=name,
        params={"strategy_ids": list(strategy_ids)},
        context="overview_groups",
    )


def _delete_custom_group_template(name: str) -> bool:
    return delete_strategy_param_template(
        strategy_id="__strategy_group__",
        template_name=name,
        context="overview_groups",
    )


def _rename_custom_group_template(old_name: str, new_name: str) -> bool:
    return rename_strategy_param_template(
        strategy_id="__strategy_group__",
        old_name=old_name,
        new_name=new_name,
        context="overview_groups",
    )


def _practical_confidence(total_trades: int, win_rate: float) -> tuple[str, str]:
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


st.title("🧭 对比总览")
st.caption("把选股结果、回测表现、实践准确率放在同一页联动比较。")

catalog = get_strategy_catalog()
strategy_options = []
for x in catalog:
    label = f"[{x.get('region', '-')}/{x.get('camp', '-')}] {x['name']}"
    strategy_options.append((label, x["id"]))
label_to_id = {label: sid for label, sid in strategy_options}
id_to_name = {x["id"]: x["name"] for x in catalog}
id_to_label = {sid: label for label, sid in strategy_options}
builtin_template_map = _build_strategy_templates(catalog)
custom_template_map = _load_custom_group_templates(set(id_to_name.keys()))
template_map = dict(builtin_template_map)
for tpl_name, tpl_ids in custom_template_map.items():
    template_map[f"⭐ 我的：{tpl_name}"] = tpl_ids

with st.sidebar:
    st.markdown("### 对比参数")
    st.markdown("#### 策略组模板")
    template_names = list(template_map.keys())
    if template_names:
        selected_template = st.selectbox("模板", template_names, index=0)
        tcol1, tcol2 = st.columns(2)
        if tcol1.button("应用模板", width="stretch"):
            st.session_state["overview_selected_labels"] = [
                id_to_label[sid] for sid in template_map.get(selected_template, []) if sid in id_to_label
            ]
            st.session_state["overview_template_name"] = selected_template
            st.rerun()
        if tcol2.button("清空选择", width="stretch"):
            st.session_state["overview_selected_labels"] = []
            st.session_state["overview_template_name"] = "自定义"
            st.rerun()

    if "overview_selected_labels" not in st.session_state:
        st.session_state["overview_selected_labels"] = [
            lb for lb, sid in strategy_options if sid in ("sepa", "canslim", "turtle")
        ]
    if "overview_template_name" not in st.session_state:
        st.session_state["overview_template_name"] = "默认对比组（SEPA/CANSLIM/海龟）"

    selected_labels = st.multiselect(
        "策略集合",
        list(label_to_id.keys()),
        key="overview_selected_labels",
        help="可混合国内外策略做横向联动对比",
    )
    selected_ids_raw = [label_to_id[x] for x in selected_labels] if selected_labels else []
    selected_ids = selected_ids_raw if selected_ids_raw else ["sepa"]
    matched_template = "自定义"
    selected_set = set(selected_ids)
    for t_name, t_ids in template_map.items():
        if selected_set == set(t_ids):
            matched_template = t_name
            break
    st.session_state["overview_template_name"] = matched_template
    st.caption(f"当前模板：{matched_template} | 已选 {len(selected_ids)} 个策略")
    with st.expander("我的模板管理", expanded=False):
        save_name = st.text_input(
            "模板名称",
            placeholder="例如：我的稳健组合",
            key="overview_custom_template_name",
        )
        if st.button("保存为我的模板", width="stretch"):
            save_name = save_name.strip()
            if not save_name:
                st.warning("请先输入模板名称。")
            elif not selected_ids_raw:
                st.warning("请先在“策略集合”中至少选择 1 个策略。")
            elif _save_custom_group_template(save_name, selected_ids_raw):
                st.success(f"已保存模板：{save_name}")
                st.session_state["overview_template_name"] = f"⭐ 我的：{save_name}"
                st.rerun()
            else:
                st.error("模板保存失败，请稍后重试。")

        custom_names = sorted(custom_template_map.keys())
        col_rename, col_delete = st.columns(2)
        with col_rename:
            st.markdown("##### 重命名")
            rename_target = st.selectbox(
                "重命名我的模板",
                options=[""] + custom_names,
                key="overview_custom_template_rename_target",
            )
            rename_new = st.text_input(
                "新模板名称",
                placeholder="例如：我的进攻组合",
                key="overview_custom_template_rename_new",
            )
            if st.button("模板重命名", width="stretch"):
                rename_target = rename_target.strip() if isinstance(rename_target, str) else ""
                rename_new = rename_new.strip()
                if not rename_target:
                    st.warning("请先选择要重命名的模板。")
                elif not rename_new:
                    st.warning("请先输入新模板名称。")
                elif rename_new == rename_target:
                    st.info("新旧名称相同，无需重命名。")
                elif rename_new in custom_names:
                    st.warning("该模板名称已存在，请换一个名称。")
                elif _rename_custom_group_template(rename_target, rename_new):
                    st.success(f"重命名成功：{rename_target} → {rename_new}")
                    if st.session_state.get("overview_template_name") == f"⭐ 我的：{rename_target}":
                        st.session_state["overview_template_name"] = f"⭐ 我的：{rename_new}"
                    st.rerun()
                else:
                    st.error("模板重命名失败，请稍后重试。")
        with col_delete:
            st.markdown("##### 删除")
            del_target = st.selectbox(
                "删除我的模板",
                options=[""] + custom_names,
                key="overview_custom_template_delete_target",
            )
            if st.button("删除我的模板", width="stretch"):
                if not del_target:
                    st.warning("请先选择要删除的模板。")
                elif _delete_custom_group_template(del_target):
                    st.success(f"已删除模板：{del_target}")
                    if st.session_state.get("overview_template_name") == f"⭐ 我的：{del_target}":
                        st.session_state["overview_template_name"] = "自定义"
                    st.rerun()
                else:
                    st.error("模板删除失败，请稍后重试。")

    st.divider()
    st.markdown("#### 选股维度")
    screen_sample = st.slider("选股扫描样本", 100, 800, 300, 50)
    top_n = st.slider("并集展示前N", 10, 100, 30, 10)

    st.markdown("#### 回测维度")
    bt_sample = st.slider("回测样本数", 50, 500, 200, 50)
    start_date = st.date_input("回测起始日", value=pd.to_datetime("2022-06-01").date())
    start_str = start_date.strftime("%Y%m%d") if start_date else "20220601"

run_clicked = st.button("🔄 一键联动刷新", type="primary", width="stretch")

if run_clicked:
    bt_error_msg = ""
    with st.spinner("联动计算中（选股 + 回测）..."):
        screen_map = {}
        params_map = {}
        for sid in selected_ids:
            params_map[sid] = get_strategy_params(sid)
            screen_map[sid] = run_screening(
                sample_size=screen_sample,
                progress_callback=None,
                sector_codes=None,
                strategy_id=sid,
                strategy_params=params_map[sid],
            )

        merged = {}
        for sid, rows in screen_map.items():
            for row in rows:
                code = row["代码"]
                if code not in merged:
                    item = dict(row)
                    item["_hits"] = [id_to_name.get(sid, sid)]
                    merged[code] = item
                else:
                    merged[code]["_hits"].append(id_to_name.get(sid, sid))
                    if float(row.get("评分", 0)) > float(merged[code].get("评分", 0)):
                        keep_hits = list(merged[code]["_hits"])
                        merged[code].update(row)
                        merged[code]["_hits"] = keep_hits

        union_rows = []
        for item in merged.values():
            uniq = []
            seen = set()
            for h in item.get("_hits", []):
                if h not in seen:
                    seen.add(h)
                    uniq.append(h)
            item["命中数"] = len(uniq)
            item["命中策略"] = " / ".join(uniq)
            item.pop("_hits", None)
            union_rows.append(item)
        union_rows.sort(key=lambda x: (x.get("命中数", 1), x.get("评分", 0)), reverse=True)
        union_rows = union_rows[:top_n]

        prev_bt_results = st.session_state.get("overview_bt_results", {})
        try:
            bt_results, _ = run_backtest_multi(
                strategy_ids=selected_ids,
                sample_size=bt_sample,
                start_date=start_str,
                progress_callback=None,
                strategy_params_map=params_map,
            )
        except Exception as e:
            bt_results = prev_bt_results if isinstance(prev_bt_results, dict) else {}
            bt_error_msg = f"回测环节失败（{type(e).__name__}），已保留上一次可用回测结果。"

        st.session_state["overview_screen_map"] = screen_map
        st.session_state["overview_union_rows"] = union_rows
        st.session_state["overview_bt_results"] = bt_results
        st.session_state["overview_ids"] = selected_ids
    if bt_error_msg:
        st.warning(bt_error_msg)
    elif not st.session_state.get("overview_bt_results"):
        st.warning("回测本次未产出可用结果（可能受数据接口影响），请稍后重试。")
    else:
        st.success("联动刷新完成")

screen_map = st.session_state.get("overview_screen_map")
union_rows = st.session_state.get("overview_union_rows")
bt_results = st.session_state.get("overview_bt_results")

if screen_map or bt_results:
    st.markdown("### 1) 选股结果对比")
    rows = []
    for sid, items in (screen_map or {}).items():
        if not items:
            rows.append({"策略": id_to_name.get(sid, sid), "候选数": 0, "突破数": 0, "平均RS": 0, "平均评分": 0})
            continue
        rows.append({
            "策略": id_to_name.get(sid, sid),
            "候选数": len(items),
            "突破数": sum(1 for r in items if r.get("突破") == "突破!"),
            "平均RS": round(sum(float(r.get("RS", 0)) for r in items) / len(items), 1),
            "平均评分": round(sum(float(r.get("评分", 0)) for r in items) / len(items), 1),
        })
    screen_df = pd.DataFrame(rows)
    st.dataframe(screen_df, width="stretch", hide_index=True)

    if union_rows:
        st.markdown("#### 并集候选（Top）")
        union_df = pd.DataFrame(union_rows)
        cols = [c for c in ["代码", "名称", "命中数", "命中策略", "板块", "价格", "RS", "评分", "突破"] if c in union_df.columns]
        st.dataframe(union_df[cols], width="stretch", hide_index=True, height=min(len(union_df) * 36 + 40, 520))

    st.divider()
    st.markdown("### 2) 回测对比")
    if bt_results:
        bt_rows = []
        for sid, r in bt_results.items():
            level, note = _practical_confidence(r.total_trades, r.win_rate)
            bt_rows.append({
                "策略": getattr(r, "strategy_name", id_to_name.get(sid, sid)),
                "总收益率": f"{r.total_return:.2%}",
                "年化": f"{r.annual_return:.2%}",
                "回撤": f"{r.max_drawdown:.2%}",
                "夏普": r.sharpe_ratio,
                "准确率(胜率)": f"{r.win_rate:.1%}",
                "交易次数": r.total_trades,
                "实践可信度": level,
                "验证说明": note,
            })
        bt_df = pd.DataFrame(bt_rows)
        st.dataframe(bt_df, width="stretch", hide_index=True)

        st.markdown("### 3) 准确率验证")
        if not bt_df.empty:
            chart_df = bt_df.copy()
            chart_df["acc"] = chart_df["准确率(胜率)"].str.replace("%", "", regex=False).astype(float)
            fig = go.Figure(data=[go.Bar(
                x=chart_df["策略"],
                y=chart_df["acc"],
                text=chart_df["准确率(胜率)"],
                textposition="outside",
                marker_color=["#43A047" if v >= 55 else "#FB8C00" if v >= 50 else "#E53935" for v in chart_df["acc"]],
            )])
            fig.update_layout(
                template="plotly_white",
                margin=dict(l=30, r=20, t=25, b=30),
                yaxis_title="准确率 (%)",
            )
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("本次回测暂未产出结果，已保留选股联动结果。可重试刷新或减少回测样本数。")

    st.divider()
    st.markdown("### 联动观察结论")
    st.caption("建议优先关注：命中数高且回测准确率/回撤表现平衡的策略组合。")
else:
    st.info("点击上方「一键联动刷新」，生成选股对比 + 回测对比 + 准确率验证。")
