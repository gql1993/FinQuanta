"""选股雷达 - SEPA 策略全市场扫描"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="选股雷达", page_icon="📡", layout="wide")

from services.stock_service import (
    run_screening, get_market_regime, get_sector_list, get_sector_stocks,
    get_sector_overview, refresh_sector_cache, get_strategy_catalog, get_strategy_params,
    load_strategy_param_templates, save_strategy_param_template, get_config, get_data_source_logs,
)
from ui.charts import plot_sector_treemap


def _screen_snapshot_path() -> str:
    return os.path.join(get_config().data.cache_dir, "screen_last_snapshot.json")


def _save_screen_snapshot(results: list[dict], scope: str,
                          per_strategy: dict, selected_ids: list[str]) -> None:
    payload = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "scope": scope,
        "per_strategy": per_strategy,
        "selected_ids": selected_ids,
    }
    try:
        with open(_screen_snapshot_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _load_screen_snapshot() -> dict:
    path = _screen_snapshot_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if isinstance(obj, dict) and isinstance(obj.get("results"), list):
                return obj
    except Exception:
        pass
    return {}


st.title("📡 选股雷达")
st.caption("基于趋势模板 + VCP 波动收缩 + RS 相对强度 综合评分排序")


def _cache_freshness() -> tuple[float | None, str]:
    cache_dir = get_config().data.cache_dir
    latest_ts = None
    latest_file = ""
    for fn in ["stock_list.csv", "financial.csv", "screen_last_snapshot.json"]:
        p = os.path.join(cache_dir, fn)
        if os.path.exists(p):
            ts = os.path.getmtime(p)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_file = fn
    try:
        daily_files = [f for f in os.listdir(cache_dir) if f.startswith("daily_") and f.endswith(".csv")]
        for fn in daily_files:
            p = os.path.join(cache_dir, fn)
            ts = os.path.getmtime(p)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
                latest_file = fn
    except Exception:
        pass
    if latest_ts is None:
        return None, "未检测到本地缓存文件"
    age_h = (datetime.now().timestamp() - latest_ts) / 3600.0
    dt_str = datetime.fromtimestamp(latest_ts).strftime("%Y-%m-%d %H:%M:%S")
    return age_h, f"最新缓存：{dt_str}（{latest_file}）"


_age_h, _fresh_msg = _cache_freshness()
if _age_h is None:
    st.error(f"⚠️ 数据新鲜度：{_fresh_msg}，当前可能无法获取最新扫描结果。")
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

# Market Status
try:
    regime = get_market_regime()
    if regime["market_ok"]:
        st.success(f"🟢 市场健康 (分布日: {regime['dist_count']})")
    else:
        st.warning(f"🔴 市场偏弱 (分布日: {regime['dist_count']})，建议谨慎")
except Exception:
    pass

# ---- Pre-load sector data from local cache (instant) ----
_sec_industry = get_sector_overview("行业板块")
_sec_concept = get_sector_overview("概念板块")

_hdr_col1, _hdr_col2 = st.columns([4, 1])
_hdr_col1.markdown("### 板块行情总览")
if _hdr_col2.button("🔄 刷新板块", key="refresh_sectors"):
    with st.spinner("从东方财富更新板块数据..."):
        refresh_sector_cache()
    st.rerun()
sec_tab3, sec_tab1, sec_tab2 = st.tabs(["⭐ 自定义板块", "行业板块", "概念板块"])


def _color_change(val):
    try:
        v = float(val)
        if v > 0:
            return "color: #ef5350; font-weight: bold"
        elif v < 0:
            return "color: #26a69a; font-weight: bold"
    except (ValueError, TypeError):
        pass
    return ""


def _render_sector_tab(sec_df, sec_type_label):
    if sec_df.empty:
        st.info(f"{sec_type_label}数据暂无")
        return

    fig_tree = plot_sector_treemap(sec_df)
    st.plotly_chart(fig_tree, width="stretch")

    with st.expander(f"📋 {sec_type_label}涨跌排行（点击展开）"):
        styled = sec_df.style.map(_color_change, subset=["涨跌幅"])
        if "领涨幅" in sec_df.columns:
            styled = styled.map(_color_change, subset=["领涨幅"])
        st.dataframe(styled, width="stretch", hide_index=True,
                     height=min(len(sec_df) * 35 + 40, 500))

    options = sec_df["板块"].tolist()
    sel_col1, sel_col2 = st.columns([3, 1])
    with sel_col1:
        picked = st.selectbox(
            f"选择{sec_type_label}扫描",
            ["（不限）"] + options,
            key=f"pick_{sec_type_label}",
        )
    with sel_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if picked != "（不限）":
            if st.button(f"🔍 扫描 {picked}", key=f"scan_{sec_type_label}",
                         width="stretch"):
                st.session_state["auto_sector"] = picked
                st.session_state["auto_sector_type"] = sec_type_label
                st.session_state["auto_run_screen"] = True
                st.rerun()


_THS_BOARDS_OVERVIEW = {
    "人工智能": {"ths_code": "885728", "keywords": ["人工智能"]},
    "芯片": {"ths_code": "885756", "keywords": ["芯片概念", "芯片"]},
    "量子科技": {"ths_code": "885823", "keywords": ["量子科技", "量子通信"]},
    "机器人": {"ths_code": "885750", "keywords": ["机器人概念", "机器人"]},
    "AI应用": {"ths_code": "886041", "keywords": ["AIGC概念", "ChatGPT概念", "AI应用"]},
    "算力": {"ths_code": "886025", "keywords": ["算力概念", "算力"]},
    "无人机": {"ths_code": "885706", "keywords": ["无人机"]},
    "军工": {"ths_code": "885660", "keywords": ["军工", "国防军工"]},
    "商业航天": {"ths_code": "885801", "keywords": ["航天概念", "卫星导航", "商业航天"]},
    "新能源汽车": {"ths_code": "885790", "keywords": ["新能源汽车"]},
    "储能": {"ths_code": "885918", "keywords": ["储能"]},
    "光伏": {"ths_code": "885773", "keywords": ["光伏概念", "光伏"]},
    "锂电池": {"ths_code": "885636", "keywords": ["锂电池"]},
    "半导体": {"ths_code": "885762", "keywords": ["半导体", "第三代半导体"]},
    "数据要素": {"ths_code": "886028", "keywords": ["数据要素", "数据确权"]},
    "大数据": {"ths_code": "885704", "keywords": ["大数据"]},
    "云计算": {"ths_code": "885758", "keywords": ["云计算"]},
    "物联网": {"ths_code": "885760", "keywords": ["物联网"]},
    "5G": {"ths_code": "885734", "keywords": ["5G"]},
    "自动驾驶": {"ths_code": "885806", "keywords": ["自动驾驶", "无人驾驶"]},
    "脑机接口": {"ths_code": "886042", "keywords": ["脑机接口"]},
    "低空经济": {"ths_code": "886057", "keywords": ["低空经济"]},
    "工业母机": {"ths_code": "885926", "keywords": ["工业母机"]},
    "光刻机": {"ths_code": "885832", "keywords": ["光刻机", "光刻胶"]},
    "存储芯片": {"ths_code": "885852", "keywords": ["存储芯片"]},
    "充电桩": {"ths_code": "885920", "keywords": ["充电桩"]},
    "风电": {"ths_code": "885798", "keywords": ["风电"]},
    "氢能源": {"ths_code": "885830", "keywords": ["氢能源"]},
    "创新药": {"ths_code": "885738", "keywords": ["创新药"]},
    "医疗器械": {"ths_code": "885770", "keywords": ["医疗器械"]},
    "CRO": {"ths_code": "885854", "keywords": ["CRO"]},
    "中药": {"ths_code": "885796", "keywords": ["中药"]},
}

_BUILTIN_GROUPS = {
    "先进生产力（AI/芯片/量子/机器人）": [
        "人工智能", "芯片", "半导体", "量子科技", "机器人",
        "AI应用", "算力", "无人机", "脑机接口",
    ],
    "军工航天": ["军工", "商业航天", "低空经济"],
    "新能源全链": ["新能源汽车", "储能", "光伏", "锂电池", "充电桩", "风电", "氢能源"],
    "数字经济": ["大数据", "云计算", "数据要素", "物联网", "5G"],
    "智能驾驶": ["自动驾驶", "新能源汽车"],
    "硬科技（光刻/存储/工母）": ["光刻机", "存储芯片", "工业母机"],
    "生物医药": ["创新药", "医疗器械", "CRO", "中药"],
}


def _load_custom_groups_global() -> dict[str, dict]:
    _path = os.path.join(get_config().data.cache_dir, "custom_sector_groups.json")
    if os.path.exists(_path):
        try:
            with open(_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
                return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    return {}


def _board_cache_path(board_name: str) -> str:
    return os.path.join(get_config().data.cache_dir, f"board_{board_name}.json")


def _load_builtin_board_data() -> dict[str, list[str]]:
    """加载内置成分股数据包（离线兜底）。"""
    path = os.path.join(get_config().data.cache_dir, "board_builtin.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
                return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    return {}


_BUILTIN_BOARD_DATA = _load_builtin_board_data()


def _get_board_stocks(board_name: str, force_refresh: bool = False) -> list[str]:
    """
    获取单个板块的成分股代码列表。
    优先级：用户缓存 → 在线接口 → 内置数据包。
    """
    cache_path = _board_cache_path(board_name)

    # 1) 用户缓存（72 小时有效）
    if not force_refresh and os.path.exists(cache_path):
        try:
            mtime = os.path.getmtime(cache_path)
            age_h = (datetime.now().timestamp() - mtime) / 3600.0
            if age_h < 72:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, list) and cached:
                    return cached
        except Exception:
            pass

    # 2) 在线接口
    info = _THS_BOARDS_OVERVIEW.get(board_name, {})
    kws = info.get("keywords", [board_name])
    codes = []
    for kw in kws:
        try:
            c = get_sector_stocks(kw, "概念板块")
            if c:
                codes.extend(c)
        except Exception:
            pass
    if not codes:
        for kw in kws:
            try:
                c = get_sector_stocks(kw, "行业板块")
                if c:
                    codes.extend(c)
            except Exception:
                pass

    unique = list(dict.fromkeys(codes))
    if unique:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(unique, f)
        except Exception:
            pass
        return unique

    # 3) 回退用户旧缓存（不限时间）
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, list) and cached:
                return cached
        except Exception:
            pass

    # 4) 内置数据包兜底
    builtin = _BUILTIN_BOARD_DATA.get(board_name, [])
    return builtin


with sec_tab3:
    _ct_hdr1, _ct_hdr2 = st.columns([4, 1])
    _ct_hdr1.markdown("#### ⭐ 自定义板块总览")
    _ct_hdr1.caption("参考同花顺/东方财富板块分类，点击板块查看成分股，点击扫描直接选股。")
    if _ct_hdr2.button("🔄 刷新全部成分股", key="refresh_custom_boards"):
        with st.spinner("并发刷新所有板块成分股缓存..."):
            from concurrent.futures import ThreadPoolExecutor, as_completed
            _board_list = list(_THS_BOARDS_OVERVIEW.keys())
            _refresh_ok = 0
            _refresh_fail = 0
            _progress = st.progress(0, text="刷新中...")
            with ThreadPoolExecutor(max_workers=6) as _pool:
                _futs = {_pool.submit(_get_board_stocks, bn, True): bn for bn in _board_list}
                _done = 0
                for fut in as_completed(_futs):
                    _done += 1
                    try:
                        result = fut.result()
                        if result:
                            _refresh_ok += 1
                        else:
                            _refresh_fail += 1
                    except Exception:
                        _refresh_fail += 1
                    _progress.progress(_done / len(_board_list), text=f"刷新中 {_done}/{len(_board_list)}...")
            _progress.empty()
        st.success(f"成分股缓存刷新完成！成功 {_refresh_ok} / 失败 {_refresh_fail}")
        st.rerun()

    _custom_user_groups = _load_custom_groups_global()
    _all_display_groups = dict(_BUILTIN_GROUPS)
    for k, v in _custom_user_groups.items():
        if isinstance(v, dict) and "boards" in v:
            _all_display_groups[k] = v["boards"]

    _group_names = list(_all_display_groups.keys())
    _board_names = list(_THS_BOARDS_OVERVIEW.keys())

    _view_mode = st.radio("查看方式", ["按板块组", "按单板块"], horizontal=True, key="custom_view_mode")

    if _view_mode == "按板块组":
        for gname, boards in _all_display_groups.items():
            with st.expander(f"📂 {gname}（{len(boards)} 个板块）", expanded=False):
                st.caption(f"包含：{', '.join(boards)}")
                gc1, gc2 = st.columns([1, 3])
                if gc1.button(f"🔍 扫描该组", key=f"cscan_grp_{gname}", width="stretch"):
                    merged = set()
                    for bn in boards:
                        merged.update(_get_board_stocks(bn))
                    if merged:
                        st.session_state["_custom_scan_codes"] = list(merged)
                        st.session_state["auto_run_screen"] = True
                        st.rerun()
                    else:
                        st.warning("未获取到成分股。")
                for bn in boards:
                    info = _THS_BOARDS_OVERVIEW.get(bn, {})
                    ths_code = info.get("ths_code", "-")
                    with st.expander(f"　{bn}（同花顺 {ths_code}）", expanded=False):
                        with st.spinner(f"加载 {bn} 成分股..."):
                            _stocks = _get_board_stocks(bn)
                        if _stocks:
                            st.caption(f"共 {len(_stocks)} 只成分股")
                            try:
                                from services.stock_service import get_stock_names as _gsn
                                _nm = _gsn()
                            except Exception:
                                _nm = {}
                            _rows = [{"代码": c, "名称": _nm.get(c, "")} for c in _stocks[:80]]
                            st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True,
                                         height=min(len(_rows) * 35 + 40, 400))
                            if st.button(f"🔍 扫描 {bn}", key=f"cscan_{bn}_{gname}", width="stretch"):
                                st.session_state["_custom_scan_codes"] = _stocks
                                st.session_state["auto_run_screen"] = True
                                st.rerun()
                        else:
                            st.info("暂未获取到成分股。")

    else:
        for bn, info in _THS_BOARDS_OVERVIEW.items():
            ths_code = info.get("ths_code", "-")
            with st.expander(f"📊 {bn}（同花顺 {ths_code}）", expanded=False):
                with st.spinner(f"加载 {bn} 成分股..."):
                    _stocks = _get_board_stocks(bn)
                if _stocks:
                    st.caption(f"共 {len(_stocks)} 只成分股")
                    try:
                        from services.stock_service import get_stock_names as _gsn2
                        _nm2 = _gsn2()
                    except Exception:
                        _nm2 = {}
                    _rows2 = [{"代码": c, "名称": _nm2.get(c, "")} for c in _stocks[:80]]
                    st.dataframe(pd.DataFrame(_rows2), width="stretch", hide_index=True,
                                 height=min(len(_rows2) * 35 + 40, 400))
                    if st.button(f"🔍 扫描 {bn}", key=f"cscan_single_{bn}", width="stretch"):
                        st.session_state["_custom_scan_codes"] = _stocks
                        st.session_state["auto_run_screen"] = True
                        st.rerun()
                else:
                    st.info("暂未获取到成分股。")

with sec_tab1:
    _render_sector_tab(_sec_industry, "行业板块")

with sec_tab2:
    _render_sector_tab(_sec_concept, "概念板块")

st.divider()

# Config
with st.sidebar:
    st.markdown("### 筛选参数")
    strategy_catalog = get_strategy_catalog()
    strategy_options = []
    for x in strategy_catalog:
        label = f"[{x.get('region', '-')}/{x.get('camp', '-')}] {x['name']}"
        strategy_options.append((label, x["id"]))
    strategy_labels = {label: sid for label, sid in strategy_options}
    strategy_name = st.selectbox(
        "策略体系",
        list(strategy_labels.keys()),
        index=0,
        help="按 国内/国外 与 游资/私募/机构/大师 分类展示，互相独立回测。",
    )
    strategy_mode = st.radio(
        "选择方式",
        ["单策略", "多策略并集"],
        horizontal=True,
        help="单策略：按一套规则筛选；多策略并集：任一策略命中即纳入候选。",
    )
    strategy_id = strategy_labels[strategy_name]
    if strategy_mode == "单策略":
        selected_strategy_labels = [strategy_name]
    else:
        all_labels = list(strategy_labels.keys())
        domestic_labels = [lb for lb, sid in strategy_labels.items() if "国内/" in lb]
        overseas_labels = [lb for lb, sid in strategy_labels.items() if "海外/" in lb]
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("全选全部", key="screen_union_all", width="stretch"):
            st.session_state["screen_union_strategies"] = all_labels
            st.rerun()
        if b2.button("全选国内", key="screen_union_domestic", width="stretch"):
            st.session_state["screen_union_strategies"] = domestic_labels
            st.rerun()
        if b3.button("全选海外", key="screen_union_overseas", width="stretch"):
            st.session_state["screen_union_strategies"] = overseas_labels
            st.rerun()
        if b4.button("清空", key="screen_union_clear", width="stretch"):
            st.session_state["screen_union_strategies"] = []
            st.rerun()

        selected_strategy_labels = st.multiselect(
            "并集策略",
            list(strategy_labels.keys()),
            default=[strategy_name],
            key="screen_union_strategies",
            help="可同时勾选多套策略，结果按并集输出。",
        )
        if not selected_strategy_labels:
            selected_strategy_labels = [strategy_name]
    selected_strategy_ids = [strategy_labels[x] for x in selected_strategy_labels]
    if strategy_mode == "单策略":
        st.caption(f"当前策略: {strategy_name}")
    else:
        st.caption(f"当前并集策略数: {len(selected_strategy_ids)}（支持选择 3 个及以上）")
    strategy_params = get_strategy_params(strategy_id)
    tpl_all = load_strategy_param_templates("screening")
    tpl_map = tpl_all.get(strategy_id, {})
    tpl_name = st.selectbox(
        "参数模板",
        ["(默认)"] + list(tpl_map.keys()),
        key=f"screen_tpl_{strategy_id}",
        help="可加载你保存的策略参数模板",
    )
    if tpl_name != "(默认)":
        strategy_params.update(tpl_map.get(tpl_name, {}))
    with st.expander("策略参数", expanded=False):
        if strategy_id == "sepa":
            strategy_params["rs_min"] = st.slider("SEPA 最低RS", 60, 95, int(strategy_params.get("rs_min", 70)), 1)
            strategy_params["pivot_distance_max_pct"] = st.slider(
                "SEPA 枢纽距离上限(%)", 3.0, 15.0,
                float(strategy_params.get("pivot_distance_max_pct", 8.0)), 0.5
            )
            strategy_params["volume_ratio_min"] = st.slider(
                "SEPA 最低量比", 0.5, 1.5,
                float(strategy_params.get("volume_ratio_min", 0.8)), 0.05
            )
        elif strategy_id == "canslim":
            strategy_params["rs_min"] = st.slider("CANSLIM 最低RS", 70, 95, int(strategy_params.get("rs_min", 80)), 1)
            strategy_params["volume_ratio_min"] = st.slider(
                "CANSLIM 最低放量倍数", 1.0, 2.0,
                float(strategy_params.get("volume_ratio_min", 1.2)), 0.05
            )
            strategy_params["near_high_52w_min_pct"] = st.slider(
                "距52周高点下限(%)", -25.0, -2.0,
                float(strategy_params.get("near_high_52w_min_pct", -12.0)), 1.0
            )
        elif strategy_id == "turtle":
            strategy_params["breakout_short"] = st.slider(
                "海龟短通道", 10, 40, int(strategy_params.get("breakout_short", 20)), 1
            )
            strategy_params["breakout_long"] = st.slider(
                "海龟长通道", 30, 100, int(strategy_params.get("breakout_long", 55)), 1
            )
            strategy_params["trend_ma_days"] = st.slider(
                "趋势均线天数", 20, 120, int(strategy_params.get("trend_ma_days", 50)), 5
            )
        elif strategy_id == "graham":
            strategy_params["pe_max"] = st.slider(
                "格雷厄姆 PE 上限", 8.0, 40.0, float(strategy_params.get("pe_max", 20.0)), 1.0
            )
            strategy_params["pb_max"] = st.slider(
                "格雷厄姆 PB 上限", 0.8, 6.0, float(strategy_params.get("pb_max", 2.5)), 0.1
            )
            strategy_params["trend_guard"] = st.checkbox(
                "启用趋势保护（仅上升趋势）", value=bool(strategy_params.get("trend_guard", True))
            )
        elif strategy_id == "livermore":
            strategy_params["breakout_days"] = st.slider(
                "利弗莫尔关键点窗口", 10, 60, int(strategy_params.get("breakout_days", 20)), 1
            )
            strategy_params["rs_min"] = st.slider(
                "利弗莫尔 最低RS", 50, 90, int(strategy_params.get("rs_min", 65)), 1
            )
            strategy_params["trend_ma_days"] = st.slider(
                "趋势均线天数", 20, 120, int(strategy_params.get("trend_ma_days", 50)), 5
            )
        elif strategy_id == "covell":
            strategy_params["breakout_days"] = st.slider(
                "卡沃尔突破窗口", 20, 120, int(strategy_params.get("breakout_days", 55)), 1
            )
            strategy_params["ma_days"] = st.slider(
                "卡沃尔主趋势均线", 80, 260, int(strategy_params.get("ma_days", 200)), 5
            )
            strategy_params["vol_filter_min"] = st.slider(
                "最低量能倍数", 0.5, 1.5, float(strategy_params.get("vol_filter_min", 0.7)), 0.05
            )
        elif strategy_id == "dow":
            strategy_params["ma_fast"] = st.slider(
                "道氏快均线", 20, 100, int(strategy_params.get("ma_fast", 50)), 5
            )
            strategy_params["ma_mid"] = st.slider(
                "道氏中均线", 80, 220, int(strategy_params.get("ma_mid", 150)), 5
            )
            strategy_params["ma_slow"] = st.slider(
                "道氏慢均线", 120, 320, int(strategy_params.get("ma_slow", 200)), 5
            )
            strategy_params["rs_min"] = st.slider(
                "道氏 最低RS", 45, 85, int(strategy_params.get("rs_min", 60)), 1
            )
        elif strategy_id == "lynch":
            strategy_params["pe_low"] = st.slider(
                "林奇 PE下限", 2.0, 20.0, float(strategy_params.get("pe_low", 8.0)), 1.0
            )
            strategy_params["pe_high"] = st.slider(
                "林奇 PE上限", 15.0, 60.0, float(strategy_params.get("pe_high", 35.0)), 1.0
            )
            strategy_params["rs_min"] = st.slider(
                "林奇 最低RS", 40, 90, int(strategy_params.get("rs_min", 60)), 1
            )
            strategy_params["trend_guard"] = st.checkbox(
                "启用趋势过滤", value=bool(strategy_params.get("trend_guard", True))
            )
        elif strategy_id == "buffett":
            strategy_params["pe_max"] = st.slider(
                "巴菲特 PE上限", 10.0, 60.0, float(strategy_params.get("pe_max", 35.0)), 1.0
            )
            strategy_params["pb_max"] = st.slider(
                "巴菲特 PB上限", 1.0, 10.0, float(strategy_params.get("pb_max", 6.0)), 0.1
            )
            strategy_params["trend_guard"] = st.checkbox(
                "启用价格趋势保护", value=bool(strategy_params.get("trend_guard", True))
            )
        elif strategy_id == "larry":
            strategy_params["breakout_days"] = st.slider(
                "拉里突破窗口", 5, 40, int(strategy_params.get("breakout_days", 20)), 1
            )
            strategy_params["volume_ratio_min"] = st.slider(
                "拉里 最低放量倍数", 1.0, 2.5, float(strategy_params.get("volume_ratio_min", 1.2)), 0.05
            )
            strategy_params["rs_min"] = st.slider(
                "拉里 最低RS", 35, 85, int(strategy_params.get("rs_min", 55)), 1
            )
        elif strategy_id == "cn_yz_yangjia":
            strategy_params["breakout_days"] = st.slider("养家突破窗口", 6, 30, int(strategy_params.get("breakout_days", 12)), 1)
            strategy_params["volume_ratio_min"] = st.slider("养家合力量比", 1.0, 2.5, float(strategy_params.get("volume_ratio_min", 1.25)), 0.05)
            strategy_params["pullback_max_pct"] = st.slider("分歧回撤上限(%)", 2.0, 12.0, float(strategy_params.get("pullback_max_pct", 6.0)), 0.5)
            strategy_params["rs_min"] = st.slider("养家最低RS", 45, 85, int(strategy_params.get("rs_min", 60)), 1)
            strategy_params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(strategy_params.get("allow_phase_start", True)))
            strategy_params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(strategy_params.get("allow_phase_ferment", True)))
            strategy_params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(strategy_params.get("allow_phase_climax", False)))
        elif strategy_id == "cn_yz_zhaolao":
            strategy_params["leader_near_high_pct"] = st.slider("龙头距新高下限(%)", -20.0, -2.0, float(strategy_params.get("leader_near_high_pct", -8.0)), 1.0)
            strategy_params["volume_ratio_min"] = st.slider("赵老哥放量倍数", 1.0, 2.8, float(strategy_params.get("volume_ratio_min", 1.35)), 0.05)
            strategy_params["rs_min"] = st.slider("赵老哥最低RS", 55, 95, int(strategy_params.get("rs_min", 75)), 1)
            strategy_params["breakout_days"] = st.slider("赵老哥突破窗口", 8, 40, int(strategy_params.get("breakout_days", 20)), 1)
            strategy_params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(strategy_params.get("allow_phase_start", True)))
            strategy_params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(strategy_params.get("allow_phase_ferment", True)))
            strategy_params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(strategy_params.get("allow_phase_climax", False)))
        elif strategy_id == "cn_yz_asking":
            strategy_params["breakout_days"] = st.slider("Asking突破窗口", 8, 40, int(strategy_params.get("breakout_days", 18)), 1)
            strategy_params["volume_ratio_min"] = st.slider("Asking放量倍数", 1.0, 2.5, float(strategy_params.get("volume_ratio_min", 1.15)), 0.05)
            strategy_params["rs_min"] = st.slider("Asking最低RS", 45, 90, int(strategy_params.get("rs_min", 65)), 1)
            strategy_params["exit_ma_days"] = st.slider("Asking截亏均线", 5, 20, int(strategy_params.get("exit_ma_days", 10)), 1)
            strategy_params["allow_phase_start"] = st.checkbox("允许启动期买入", value=bool(strategy_params.get("allow_phase_start", True)))
            strategy_params["allow_phase_ferment"] = st.checkbox("允许发酵期买入", value=bool(strategy_params.get("allow_phase_ferment", True)))
            strategy_params["allow_phase_climax"] = st.checkbox("允许高潮期买入", value=bool(strategy_params.get("allow_phase_climax", False)))
        elif strategy_id == "cn_pm_danbin":
            strategy_params["pe_max"] = st.slider("但斌 PE上限", 15.0, 80.0, float(strategy_params.get("pe_max", 45.0)), 1.0)
            strategy_params["pb_max"] = st.slider("但斌 PB上限", 1.0, 15.0, float(strategy_params.get("pb_max", 8.0)), 0.1)
            strategy_params["rs_min"] = st.slider("但斌最低RS", 35, 85, int(strategy_params.get("rs_min", 55)), 1)
            strategy_params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(strategy_params.get("heat_min", 50.0)), 1.0)
            strategy_params["valuation_min"] = st.slider("估值分位下限", 20.0, 90.0, float(strategy_params.get("valuation_min", 35.0)), 1.0)
            strategy_params["crowding_max"] = st.slider("拥挤度上限", 40.0, 95.0, float(strategy_params.get("crowding_max", 75.0)), 1.0)
            strategy_params["trend_guard"] = st.checkbox("启用长期趋势保护", value=bool(strategy_params.get("trend_guard", True)))
        elif strategy_id == "cn_pm_linyuan":
            strategy_params["pe_max"] = st.slider("林园 PE上限", 10.0, 70.0, float(strategy_params.get("pe_max", 35.0)), 1.0)
            strategy_params["pb_max"] = st.slider("林园 PB上限", 1.0, 12.0, float(strategy_params.get("pb_max", 7.0)), 0.1)
            strategy_params["rs_min"] = st.slider("林园最低RS", 35, 85, int(strategy_params.get("rs_min", 50)), 1)
            strategy_params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(strategy_params.get("heat_min", 45.0)), 1.0)
            strategy_params["valuation_min"] = st.slider("估值分位下限", 20.0, 90.0, float(strategy_params.get("valuation_min", 40.0)), 1.0)
            strategy_params["crowding_max"] = st.slider("拥挤度上限", 40.0, 95.0, float(strategy_params.get("crowding_max", 78.0)), 1.0)
            strategy_params["trend_guard"] = st.checkbox("启用趋势过滤", value=bool(strategy_params.get("trend_guard", True)))
        elif strategy_id == "cn_inst_qiuguolu":
            strategy_params["pe_max"] = st.slider("机构 PE上限", 10.0, 50.0, float(strategy_params.get("pe_max", 28.0)), 1.0)
            strategy_params["pb_max"] = st.slider("机构 PB上限", 1.0, 10.0, float(strategy_params.get("pb_max", 5.0)), 0.1)
            strategy_params["ma_days"] = st.slider("机构趋势均线", 60, 250, int(strategy_params.get("ma_days", 150)), 5)
            strategy_params["rs_min"] = st.slider("机构最低RS", 40, 90, int(strategy_params.get("rs_min", 55)), 1)
            strategy_params["heat_min"] = st.slider("赛道热度下限", 20.0, 90.0, float(strategy_params.get("heat_min", 42.0)), 1.0)
            strategy_params["valuation_min"] = st.slider("估值分位下限", 20.0, 95.0, float(strategy_params.get("valuation_min", 50.0)), 1.0)
            strategy_params["crowding_max"] = st.slider("拥挤度上限", 35.0, 90.0, float(strategy_params.get("crowding_max", 65.0)), 1.0)
            strategy_params["trend_guard"] = st.checkbox("启用趋势保护", value=bool(strategy_params.get("trend_guard", True)))
        else:
            st.caption("该策略当前使用默认参数。")
        save_name = st.text_input(
            "保存为模板名",
            value="",
            placeholder="例如：SEPA稳健版",
            key=f"screen_tpl_save_{strategy_id}",
        )
        if st.button("💾 保存当前参数模板", key=f"screen_tpl_btn_{strategy_id}", width="stretch"):
            if not save_name.strip():
                st.warning("请先输入模板名")
            else:
                ok = save_strategy_param_template(
                    strategy_id, save_name.strip(), strategy_params, context="screening"
                )
                if ok:
                    st.success(f"模板已保存：{save_name.strip()}")
                else:
                    st.error("模板保存失败")

    strategy_params_map = {}
    if strategy_mode == "单策略":
        strategy_params_map[strategy_id] = strategy_params
    else:
        for sid in selected_strategy_ids:
            strategy_params_map[sid] = get_strategy_params(sid)
    st.divider()

    # ---- Sector filter ----
    st.markdown("#### 板块筛选")
    sector_type = st.radio("板块类型", ["全市场", "行业板块", "概念板块", "自定义板块组"],
                           horizontal=True, key="sector_type")

    selected_sector = None
    _custom_sector_codes = None

    if sector_type == "自定义板块组":
        _custom_groups_path = os.path.join(get_config().data.cache_dir, "custom_sector_groups.json")

        def _load_custom_groups() -> dict[str, dict]:
            if os.path.exists(_custom_groups_path):
                try:
                    with open(_custom_groups_path, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                        return obj if isinstance(obj, dict) else {}
                except Exception:
                    pass
            return {}

        def _save_custom_groups(groups: dict[str, dict]) -> bool:
            try:
                os.makedirs(os.path.dirname(_custom_groups_path), exist_ok=True)
                with open(_custom_groups_path, "w", encoding="utf-8") as f:
                    json.dump(groups, f, ensure_ascii=False, indent=2)
                return True
            except Exception:
                return False

        _THS_BOARDS = {
            "人工智能": {"ths_code": "885728", "keywords": ["人工智能"]},
            "芯片": {"ths_code": "885756", "keywords": ["芯片概念"]},
            "量子科技": {"ths_code": "885823", "keywords": ["量子科技"]},
            "机器人": {"ths_code": "885750", "keywords": ["机器人概念"]},
            "AI应用": {"ths_code": "886041", "keywords": ["AIGC概念", "ChatGPT概念"]},
            "算力": {"ths_code": "886025", "keywords": ["算力概念"]},
            "无人机": {"ths_code": "885706", "keywords": ["无人机"]},
            "军工": {"ths_code": "885660", "keywords": ["军工"]},
            "商业航天": {"ths_code": "885801", "keywords": ["航天概念", "卫星导航"]},
            "新能源": {"ths_code": "885790", "keywords": ["新能源汽车"]},
            "储能": {"ths_code": "885918", "keywords": ["储能"]},
            "光伏": {"ths_code": "885773", "keywords": ["光伏概念"]},
            "锂电池": {"ths_code": "885636", "keywords": ["锂电池"]},
        }

        _builtin_presets = {
            "先进生产力（AI/芯片/量子/机器人）": ["人工智能", "芯片", "量子科技", "机器人", "AI应用", "算力", "无人机"],
            "军工航天": ["军工", "商业航天"],
            "新能源全链": ["新能源", "储能", "光伏", "锂电池"],
        }

        custom_groups = _load_custom_groups()
        all_presets = dict(_builtin_presets)
        for k, v in custom_groups.items():
            if isinstance(v, dict) and "boards" in v:
                all_presets[k] = v["boards"]

        sg_mode = st.radio("选择方式", ["预设板块组", "单个板块", "手动输入代码"], horizontal=True, key="csg_mode")

        if sg_mode == "预设板块组":
            selected_group = st.selectbox(
                "选择板块组", [""] + list(all_presets.keys()),
                key="custom_sector_group_select",
            )
            if selected_group and selected_group in all_presets:
                board_names = all_presets[selected_group]
                st.caption(f"包含：{', '.join(board_names)}")
                with st.spinner("获取成分股..."):
                    matched_codes = set()
                    for bn in board_names:
                        info = _THS_BOARDS.get(bn, {})
                        kws = info.get("keywords", [bn])
                        for kw in kws:
                            try:
                                codes = get_sector_stocks(kw, "概念板块")
                                if codes:
                                    matched_codes.update(codes)
                            except Exception:
                                pass
                if matched_codes:
                    _custom_sector_codes = list(matched_codes)
                    st.info(f"板块组 [{selected_group}] 共 {len(_custom_sector_codes)} 只成分股")
                else:
                    st.warning("未匹配到成分股，将按全市场扫描。")

        elif sg_mode == "单个板块":
            board_pick = st.selectbox(
                "选择同花顺板块", [""] + list(_THS_BOARDS.keys()),
                key="csg_single_board",
            )
            if board_pick and board_pick in _THS_BOARDS:
                info = _THS_BOARDS[board_pick]
                st.caption(f"同花顺代码：{info['ths_code']}")
                with st.spinner(f"获取 {board_pick} 成分股..."):
                    matched_codes = set()
                    for kw in info.get("keywords", [board_pick]):
                        try:
                            codes = get_sector_stocks(kw, "概念板块")
                            if codes:
                                matched_codes.update(codes)
                        except Exception:
                            pass
                if matched_codes:
                    _custom_sector_codes = list(matched_codes)
                    st.info(f"[{board_pick}] 共 {len(_custom_sector_codes)} 只成分股")
                else:
                    st.warning("未获取到成分股，将按全市场扫描。")

        elif sg_mode == "手动输入代码":
            _manual_codes = st.text_area(
                "输入股票代码（每行一个或逗号分隔）",
                placeholder="603881\n002975\n688001",
                height=120,
                key="csg_manual_codes",
            )
            if _manual_codes.strip():
                import re
                raw = re.split(r"[,\s\n;，；]+", _manual_codes.strip())
                valid = [c.strip() for c in raw if c.strip().isdigit() and len(c.strip()) == 6]
                if valid:
                    _custom_sector_codes = valid
                    st.info(f"手动输入 {len(valid)} 只股票代码")
                else:
                    st.warning("未检测到有效的 6 位股票代码。")

        with st.expander("管理自定义板块组", expanded=False):
            st.caption("从上面的板块中组合，保存为你自己的板块组。")
            _new_name = st.text_input("板块组名称", placeholder="例如：我的科技组", key="csg_new_name")
            _new_boards = st.multiselect(
                "选择包含的板块",
                options=list(_THS_BOARDS.keys()),
                key="csg_new_boards",
            )
            csg_c1, csg_c2 = st.columns(2)
            if csg_c1.button("💾 保存板块组", key="csg_save", width="stretch"):
                _name = _new_name.strip()
                if _name and _new_boards:
                    custom_groups[_name] = {"boards": _new_boards}
                    if _save_custom_groups(custom_groups):
                        st.success(f"已保存板块组：{_name}（{len(_new_boards)} 个板块）")
                        st.rerun()
                    else:
                        st.error("保存失败。")
                else:
                    st.warning("请填写组名并选择至少一个板块。")

            _del_options = sorted(custom_groups.keys())
            if _del_options:
                _del_target = st.selectbox("删除自定义板块组", [""] + _del_options, key="csg_del_target")
                if csg_c2.button("🗑️ 删除", key="csg_del", width="stretch"):
                    if _del_target and _del_target in custom_groups:
                        custom_groups.pop(_del_target)
                        _save_custom_groups(custom_groups)
                        st.success(f"已删除：{_del_target}")
                        st.rerun()

    elif sector_type != "全市场":
        with st.spinner("加载板块列表..."):
            sector_data = get_sector_list()
        sector_names = sector_data.get(sector_type, [])
        if sector_names:
            selected_sector = st.selectbox(
                f"选择{sector_type}", [""] + sector_names,
                key="sector_select",
                help="选择后将仅扫描该板块内的股票",
            )
            if selected_sector:
                st.caption(f"已选: {selected_sector}")
        else:
            st.warning("板块列表加载失败")

    # Auto-select from treemap click
    if st.session_state.get("auto_sector"):
        selected_sector = st.session_state.pop("auto_sector")
        sector_type = st.session_state.pop("auto_sector_type", "行业板块")

    st.divider()
    sample_size = st.slider("扫描股票数", 100, 800, 300, 50)
    min_rs = st.slider("最低 RS 评级", 50, 95, 70, 5)
    show_vcp_only = st.checkbox("仅显示有 VCP 形态", value=False)
    top_n = st.slider("显示前 N 名", 5, 30, 10, 5)
    force_latest = st.checkbox("每次扫描强制刷新最新数据（更慢）", value=True)

# Run Screening
auto_run = bool(st.session_state.pop("auto_run_screen", False))
btn_col1, btn_col2 = st.columns(2)
manual_run = btn_col1.button("🔍 开始扫描", type="primary", width="stretch")
offline_run = btn_col2.button("🗂️ 仅用本地缓存扫描（离线模式）", width="stretch")
if manual_run or auto_run or offline_run:
    run_offline = bool(offline_run)
    progress = st.progress(0, text="准备中...")

    def update_progress(pct, text):
        progress.progress(pct, text=text)

    # Resolve sector filter
    sector_codes = st.session_state.pop("_custom_scan_codes", None) or _custom_sector_codes or None
    if not sector_codes and selected_sector:
        if run_offline:
            st.info("离线模式下暂不支持实时拉取板块成分股，本次按全市场缓存扫描。")
        else:
            with st.spinner(f"获取 {selected_sector} 成分股..."):
                sector_codes = get_sector_stocks(selected_sector, sector_type)
            if not sector_codes:
                st.warning(f"未能获取 {selected_sector} 的成分股列表")
                st.stop()
            st.info(f"板块 [{selected_sector}] 共 {len(sector_codes)} 只成分股")

    per_strategy_results = {}
    candidates = []
    screen_exc = None
    fallback_state = {"used": False}

    def _run_one_strategy(sid: str, cb):
        try:
            return run_screening(
                sample_size,
                progress_callback=cb,
                sector_codes=sector_codes,
                strategy_id=sid,
                strategy_params=strategy_params_map.get(sid, {}),
                offline_only=run_offline,
                force_refresh=(force_latest and not run_offline),
            )
        except Exception:
            # 在线模式失败时自动回退到离线缓存，尽量保证有结果可看。
            if run_offline:
                raise
            part = run_screening(
                sample_size,
                progress_callback=cb,
                sector_codes=sector_codes,
                strategy_id=sid,
                strategy_params=strategy_params_map.get(sid, {}),
                offline_only=True,
                force_refresh=False,
            )
            fallback_state["used"] = True
            return part

    with st.spinner("离线扫描中..." if run_offline else "扫描中..."):
        try:
            if len(selected_strategy_ids) == 1:
                sid = selected_strategy_ids[0]
                candidates = _run_one_strategy(sid, update_progress)
                per_strategy_results = {sid: candidates}
            else:
                merged = {}
                total_s = len(selected_strategy_ids)
                for i, sid in enumerate(selected_strategy_ids):
                    def _cb(pct, text, idx=i):
                        # map each strategy run's progress [0,1] to overall [0,1]
                        update_progress((idx + pct) / total_s, f"{text}（{idx+1}/{total_s}）")

                    part = _run_one_strategy(sid, _cb)
                    per_strategy_results[sid] = part
                    for row in part:
                        code = row["代码"]
                        hit = row.get("策略", sid)
                        if code not in merged:
                            item = dict(row)
                            item["_hits"] = [hit]
                            merged[code] = item
                        else:
                            m = merged[code]
                            m["_hits"].append(hit)
                            if float(row.get("评分", 0)) > float(m.get("评分", 0)):
                                keep_hits = list(m["_hits"])
                                m.update(row)
                                m["_hits"] = keep_hits

                for item in merged.values():
                    seen = set()
                    hits = []
                    for h in item.get("_hits", []):
                        if h not in seen:
                            seen.add(h)
                            hits.append(h)
                    item["命中数"] = len(hits)
                    item["命中策略"] = " / ".join(hits)
                    item["策略"] = "并集"
                    item.pop("_hits", None)
                    candidates.append(item)
                candidates.sort(key=lambda x: (x.get("命中数", 1), x.get("评分", 0)), reverse=True)
        except Exception as e:
            # 代理/网络异常时避免整页 traceback，保留页面可用性。
            screen_exc = e

    progress.empty()
    if screen_exc is None and fallback_state["used"]:
        st.warning("实时数据接口暂不可用，已自动回退为离线缓存扫描结果。")

    if screen_exc is not None:
        if run_offline:
            st.warning(f"离线扫描失败（{type(screen_exc).__name__}），请检查本地缓存数据完整性。")
        else:
            st.warning(
                f"扫描请求失败（{type(screen_exc).__name__}），可能是网络/代理异常。"
                "已跳过本次扫描，可稍后重试。"
            )
        if "screen_results" in st.session_state and st.session_state["screen_results"]:
            st.session_state["screen_is_snapshot"] = True
            st.info("已保留上次扫描结果供继续查看。")
        else:
            snap = _load_screen_snapshot()
            if snap:
                st.session_state["screen_results"] = snap.get("results", [])
                st.session_state["screen_scope"] = snap.get("scope", "离线快照")
                st.session_state["screen_per_strategy"] = snap.get("per_strategy", {})
                st.session_state["screen_selected_ids"] = snap.get("selected_ids", [])
                st.session_state["screen_is_snapshot"] = True
                st.session_state["screen_snapshot_saved_at"] = snap.get("saved_at", "")
                st.info("已自动加载最近一次成功扫描的离线快照结果。")
            else:
                st.stop()

    if screen_exc is None and not candidates:
        st.warning("当前无股票通过筛选条件，可能处于弱势市场")
        st.stop()

    if screen_exc is None:
        # Filter
        filtered = [c for c in candidates if c["RS"] >= min_rs]
        if show_vcp_only:
            filtered = [c for c in filtered if c["VCP"] == "✓"]
        filtered = filtered[:top_n]

        scope = f"板块 [{selected_sector}]" if selected_sector else "全市场"
        if len(selected_strategy_ids) > 1:
            scope += f" / {len(selected_strategy_ids)}策略并集"
        if run_offline:
            scope += " / 离线模式"
        elif fallback_state["used"]:
            scope += " / 在线失败-离线回退"
        st.session_state["screen_results"] = filtered
        st.session_state["screen_scope"] = scope
        st.session_state["screen_per_strategy"] = per_strategy_results
        st.session_state["screen_selected_ids"] = selected_strategy_ids
        st.session_state["screen_is_snapshot"] = False
        st.session_state["screen_snapshot_saved_at"] = ""
        _save_screen_snapshot(filtered, scope, per_strategy_results, selected_strategy_ids)
        st.success(f"扫描完成 ({scope})! 找到 {len(candidates)} 只候选，筛选后 {len(filtered)} 只")

# Display Results
if "screen_results" in st.session_state and st.session_state["screen_results"]:
    results = st.session_state["screen_results"]
    scope_text = st.session_state.get("screen_scope", "全市场")
    per_strategy_results = st.session_state.get("screen_per_strategy", {})
    is_snapshot = bool(st.session_state.get("screen_is_snapshot", False))
    snapshot_time = st.session_state.get("screen_snapshot_saved_at", "")
    st.caption(f"当前推荐范围：{scope_text}")
    if is_snapshot:
        if snapshot_time:
            st.info(f"当前展示为离线快照结果（保存时间：{snapshot_time}）。")
        else:
            st.info("当前展示为离线快照结果。")

    if per_strategy_results and len(per_strategy_results) >= 1:
        with st.expander("📊 策略选股结果对比", expanded=len(per_strategy_results) > 1):
            catalog = {x["id"]: x["name"] for x in get_strategy_catalog()}
            cmp_rows = []
            for sid, rows in per_strategy_results.items():
                if not rows:
                    cmp_rows.append({
                        "策略": catalog.get(sid, sid),
                        "候选数": 0,
                        "突破数": 0,
                        "均分": 0.0,
                        "平均RS": 0.0,
                    })
                    continue
                cmp_rows.append({
                    "策略": catalog.get(sid, sid),
                    "候选数": len(rows),
                    "突破数": sum(1 for r in rows if r.get("突破") == "突破!"),
                    "均分": round(sum(float(r.get("评分", 0)) for r in rows) / len(rows), 1),
                    "平均RS": round(sum(float(r.get("RS", 0)) for r in rows) / len(rows), 1),
                })
            st.dataframe(pd.DataFrame(cmp_rows), width="stretch", hide_index=True)

            if len(per_strategy_results) > 1:
                all_sets = [set(r["代码"] for r in rows) for rows in per_strategy_results.values() if rows]
                if all_sets:
                    inter = set.intersection(*all_sets) if len(all_sets) > 1 else set()
                    uni = set.union(*all_sets)
                    jc1, jc2, jc3 = st.columns(3)
                    jc1.metric("并集股票数", len(uni))
                    jc2.metric("交集股票数", len(inter))
                    jc3.metric("交集占并集", f"{(len(inter)/len(uni)*100):.1f}%" if uni else "0%")

    # ---- 信号推送 ----
    _breakout_list = [r for r in results if r.get("突破") == "突破!"]
    if _breakout_list:
        _push_col1, _push_col2 = st.columns([1, 3])
        with _push_col1:
            if st.button("📤 推送突破信号", key="push_breakout_signal", width="stretch"):
                try:
                    from signal_push import push_screening_results
                    _strategy_label = scope_text
                    _push_result = push_screening_results(_breakout_list, strategy_name=_strategy_label)
                    if _push_result:
                        ok_ch = [ch for ch, ok in _push_result.items() if ok]
                        fail_ch = [ch for ch, ok in _push_result.items() if not ok]
                        if ok_ch:
                            st.success(f"推送成功：{', '.join(ok_ch)}")
                        if fail_ch:
                            st.warning(f"推送失败：{', '.join(fail_ch)}")
                    else:
                        st.info("未配置推送渠道。请设置环境变量 PUSH_SERVERCHAN_KEY / PUSH_WECOM_WEBHOOK / PUSH_EMAIL_TO。")
                except Exception as _pe:
                    st.warning(f"推送异常：{_pe}")
        with _push_col2:
            st.caption(f"当前有 {len(_breakout_list)} 只突破信号可推送（支持微信/企业微信/邮件）")

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    breakouts = sum(1 for r in results if r["突破"] == "突破!")
    vcp_count = sum(1 for r in results if r["VCP"] == "✓")
    avg_rs = sum(r["RS"] for r in results) / len(results)
    c1.metric("候选数", len(results))
    c2.metric("已突破", breakouts)
    c3.metric("有VCP形态", vcp_count)
    c4.metric("平均RS", f"{avg_rs:.0f}")

    st.divider()

    # Interactive table
    display_cols = ["代码", "名称", "命中数", "命中策略", "策略", "策略标签", "策略细分", "板块", "价格", "RS", "评分", "VCP", "收缩",
                    "枢纽", "距枢纽%", "突破", "紧密", "量比", "离高点%"]
    df = pd.DataFrame(results)
    display_cols = [c for c in display_cols if c in df.columns]
    df = df[display_cols]

    st.dataframe(
        df,
        width="stretch",
        height=min(len(df) * 38 + 40, 800),
        column_config={
            "评分": st.column_config.ProgressColumn("评分", min_value=0, max_value=120, format="%.1f"),
            "RS": st.column_config.NumberColumn("RS", format="%d"),
            "距枢纽%": st.column_config.NumberColumn("距枢纽%", format="%.1f%%"),
            "离高点%": st.column_config.NumberColumn("离高点%", format="%.1f%%"),
        },
    )

    # Quick-nav: select a stock from the results to view details
    sel_col1, sel_col2 = st.columns([3, 1])
    with sel_col1:
        options = [f"{r['代码']} {r['名称']}" for r in results]
        selected = st.selectbox("选择股票查看详情", options, key="screen_detail_select")
    with sel_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📉 查看详情", key="screen_goto_detail", width="stretch"):
            sel_code = selected.split()[0]
            st.session_state["detail_code"] = sel_code
            st.switch_page("pages/4_个股分析.py")

    # Categorized view
    st.divider()
    tab1, tab2, tab3 = st.tabs(["🔥 突破型", "⏳ 待突破", "📦 基底构建"])

    def _stock_link_row(r, suffix, extra_info):
        """Render a stock row with a clickable button to navigate to detail page."""
        lc, rc = st.columns([4, 1])
        lc.markdown(f"**{r['代码']} {r['名称']}** — {extra_info}")
        if rc.button("查看详情", key=f"go_{r['代码']}_{suffix}", width="stretch"):
            st.session_state["detail_code"] = r["代码"]
            st.switch_page("pages/4_个股分析.py")

    def _sector_tag(r):
        s = r.get("板块", "-")
        return f"[{s}] " if s and s != "-" else ""

    with tab1:
        bo = [r for r in results if r["突破"] == "突破!"]
        if bo:
            for r in bo:
                _stock_link_row(r, "bo", f"{_sector_tag(r)}RS {r['RS']}，评分 {r['评分']}，枢纽 {r['枢纽']}，放量突破确认")
        else:
            st.info("当前无突破型候选")

    with tab2:
        near = [r for r in results if r["突破"] == "~"]
        if near:
            for r in near:
                _stock_link_row(r, "near", f"{_sector_tag(r)}RS {r['RS']}，距枢纽 {r['距枢纽%']}%，关注放量突破")
        else:
            st.info("当前无待突破候选")

    with tab3:
        building = [r for r in results if r["VCP"] == "✓" and r["突破"] not in ("突破!", "~")]
        if building:
            for r in building[:10]:
                _stock_link_row(r, "base", f"{_sector_tag(r)}RS {r['RS']}，收缩 {r['收缩']} 次，量比 {r['量比']}，持续跟踪")
        else:
            st.info("当前无基底构建候选")
else:
    st.info("点击上方「开始扫描」按钮运行选股")
