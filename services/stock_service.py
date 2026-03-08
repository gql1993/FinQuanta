"""
股票数据服务层
封装现有策略模块，提供 Streamlit 缓存友好的接口。
"""
import sys
import os
import json
from datetime import datetime
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import StrategyConfig
from data_fetcher import DataFetcher
from trend_template import TrendTemplate
from vcp_detector import VCPDetector
from strategy import SEPAStrategy, MarketRegimeFilter
from backtester import Backtester
from strategy_profiles import (
    STRATEGY_PROFILES,
    get_strategy_catalog as _get_strategy_catalog,
    strategy_name,
    get_strategy_default_params,
    apply_screening_profile,
    apply_backtest_profile,
)


@st.cache_resource
def get_config() -> StrategyConfig:
    config = StrategyConfig()
    config.data.start_date = "20220101"
    return config


@st.cache_resource
def get_fetcher() -> DataFetcher:
    return DataFetcher(get_config().data)


@st.cache_resource
def get_strategy() -> SEPAStrategy:
    return SEPAStrategy(get_config())


def get_strategy_catalog() -> list[dict]:
    """获取可选策略目录（用于页面下拉与回测对比）。"""
    return _get_strategy_catalog()


def get_strategy_params(strategy_id: str) -> dict:
    """返回策略默认参数（供页面控件初始化）。"""
    return get_strategy_default_params(strategy_id)


def _data_source_log_path() -> str:
    return os.path.join(get_config().data.cache_dir, "data_source_hits.log")


def _append_data_source_log(data_type: str, source: str, detail: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {data_type:<8} | {source:<10} | {detail}\n"
    try:
        with open(_data_source_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def get_data_source_logs(limit: int = 80) -> list[str]:
    path = _data_source_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [x.rstrip("\n") for x in f.readlines()]
        return lines[-max(1, int(limit)):]
    except Exception:
        return []


def _strategy_template_path(context: str) -> str:
    cache_dir = get_config().data.cache_dir
    return os.path.join(cache_dir, f"strategy_params_{context}.json")


def load_strategy_param_templates(context: str = "screening") -> dict:
    """
    加载参数模板:
    {
      "sepa": {"稳健模板": {...}},
      "canslim": {"激进模板": {...}}
    }
    """
    path = _strategy_template_path(context)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_strategy_param_template(strategy_id: str, template_name: str,
                                 params: dict, context: str = "screening") -> bool:
    if not strategy_id or not template_name:
        return False
    all_tpl = load_strategy_param_templates(context)
    all_tpl.setdefault(strategy_id, {})
    all_tpl[strategy_id][template_name] = dict(params)
    path = _strategy_template_path(context)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_tpl, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def delete_strategy_param_template(strategy_id: str, template_name: str,
                                   context: str = "screening") -> bool:
    if not strategy_id or not template_name:
        return False
    all_tpl = load_strategy_param_templates(context)
    if strategy_id not in all_tpl or template_name not in all_tpl.get(strategy_id, {}):
        return False
    try:
        all_tpl[strategy_id].pop(template_name, None)
        if not all_tpl[strategy_id]:
            all_tpl.pop(strategy_id, None)
        path = _strategy_template_path(context)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_tpl, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def rename_strategy_param_template(strategy_id: str, old_name: str, new_name: str,
                                   context: str = "screening") -> bool:
    if not strategy_id or not old_name or not new_name:
        return False
    old_name = old_name.strip()
    new_name = new_name.strip()
    if not old_name or not new_name:
        return False
    all_tpl = load_strategy_param_templates(context)
    slot = all_tpl.get(strategy_id, {})
    if old_name not in slot:
        return False
    if new_name != old_name and new_name in slot:
        return False
    try:
        payload = slot.pop(old_name)
        slot[new_name] = payload
        all_tpl[strategy_id] = slot
        path = _strategy_template_path(context)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_tpl, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _fetch_stock_list(force_refresh: bool = False) -> pd.DataFrame:
    try:
        df = get_fetcher().get_stock_list(force_refresh=force_refresh)
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", "name"])
        if "code" not in df.columns:
            return pd.DataFrame(columns=["code", "name"])
        if "name" not in df.columns:
            df = df.copy()
            df["name"] = df["code"]
        return df[["code", "name"]]
    except Exception:
        # 任意网络/解析异常均降级为空表，避免页面初始化直接中断。
        return pd.DataFrame(columns=["code", "name"])


@st.cache_data(ttl=3600, show_spinner=False)
def _get_stock_list_cached() -> pd.DataFrame:
    return _fetch_stock_list(force_refresh=False)


def get_stock_list(force_refresh: bool = False) -> pd.DataFrame:
    if force_refresh:
        return _fetch_stock_list(force_refresh=True)
    return _get_stock_list_cached()


def _build_name_map(sl: pd.DataFrame) -> dict[str, str]:
    if sl is None or sl.empty or "code" not in sl.columns:
        return {}
    if "name" not in sl.columns:
        return {str(c): str(c) for c in sl["code"].astype(str)}
    return dict(zip(sl["code"].astype(str), sl["name"].astype(str)))


@st.cache_data(ttl=3600, show_spinner=False)
def _get_stock_names_cached() -> dict[str, str]:
    return _build_name_map(get_stock_list(force_refresh=False))


def get_stock_names(force_refresh: bool = False) -> dict[str, str]:
    try:
        if force_refresh:
            return _build_name_map(get_stock_list(force_refresh=True))
        return _get_stock_names_cached()
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _get_daily_data_cached(code: str) -> pd.DataFrame | None:
    return get_fetcher().get_daily_data(code)


def get_daily_data(code: str, force_refresh: bool = False) -> pd.DataFrame | None:
    if force_refresh:
        return get_fetcher().get_daily_data(code, force_refresh=True)
    return _get_daily_data_cached(code)


@st.cache_data(ttl=86400, show_spinner=False)
def get_sector_list() -> dict[str, list[str]]:
    """获取行业板块名称列表和概念板块名称列表，返回 {type: [names]}"""
    import akshare as ak
    result = {"行业板块": [], "概念板块": []}
    try:
        ind = ak.stock_board_industry_name_em()
        names = ind["板块名称"].dropna().unique().tolist()
        result["行业板块"] = sorted(set(names))
    except Exception:
        pass
    try:
        con = ak.stock_board_concept_name_em()
        names = con["板块名称"].dropna().unique().tolist()
        result["概念板块"] = sorted(set(names))
    except Exception:
        pass
    return result


def _sector_cache_path(sector_type: str) -> str:
    tag = "industry" if sector_type == "行业板块" else "concept"
    return os.path.join(get_config().data.cache_dir, f"sector_{tag}.csv")


def get_sector_overview(sector_type: str = "行业板块", allow_network: bool = False) -> pd.DataFrame:
    """
    获取板块行情概览。优先读本地 CSV 缓存（<10ms）。
    为保证页面秒开：只要本地有缓存就直接返回，
    联网更新交由 refresh_sector_cache() 手动触发。
    """
    cache_path = _sector_cache_path(sector_type)

    # 1) 本地缓存存在 → 立即返回（无论新旧）
    cached_df = None
    if os.path.exists(cache_path):
        try:
            cached_df = pd.read_csv(cache_path)
        except Exception:
            pass

    if cached_df is not None and not cached_df.empty:
        return cached_df

    if not allow_network:
        return pd.DataFrame()

    # 2) 无缓存且允许联网 → 拉取
    fresh = _fetch_sector_from_network(sector_type)
    if fresh is not None and not fresh.empty:
        try:
            fresh.to_csv(cache_path, index=False)
        except Exception:
            pass
        return fresh

    # 3) 网络失败 → 返回空表
    if cached_df is not None:
        return cached_df
    return pd.DataFrame()


def _fetch_sector_from_network(sector_type: str) -> pd.DataFrame | None:
    """从东方财富获取板块数据（慢，10-30秒）"""
    import akshare as ak
    try:
        if sector_type == "行业板块":
            df = ak.stock_board_industry_name_em()
        else:
            df = ak.stock_board_concept_name_em()
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "排名": "排名", "板块名称": "板块", "板块代码": "代码",
            "最新价": "最新价", "涨跌额": "涨跌额", "涨跌幅": "涨跌幅",
            "总市值": "总市值", "换手率": "换手率",
            "上涨家数": "上涨", "下跌家数": "下跌",
            "领涨股票": "领涨股", "领涨股票-涨跌幅": "领涨幅",
        })
        keep = ["排名", "板块", "涨跌幅", "上涨", "下跌", "换手率", "领涨股", "领涨幅", "总市值"]
        keep = [c for c in keep if c in df.columns]
        return df[keep]
    except Exception:
        return None


def refresh_sector_cache():
    """手动刷新板块缓存（供按钮调用）"""
    for st_type in ["行业板块", "概念板块"]:
        fresh = _fetch_sector_from_network(st_type)
        if fresh is not None and not fresh.empty:
            try:
                fresh.to_csv(_sector_cache_path(st_type), index=False)
            except Exception:
                pass


def get_realtime_prices(codes: list[str]) -> dict[str, float]:
    """获取实时价格（仅价格）"""
    result = get_realtime_quotes(codes)
    return {code: q["price"] for code, q in result.items() if q["price"] > 0}


def get_realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """
    通过新浪财经 API 获取实时行情（<1秒响应）。
    返回 {code: {"price": 当前价, "prev_close": 昨收, "open": 今开,
                  "high": 最高, "low": 最低, "name": 名称}}
    """
    import urllib.request

    quotes = {}
    source_hits = {"sina": 0, "tencent": 0, "eastmoney": 0, "cache": 0}
    if not codes:
        return quotes

    sina_codes = []
    code_map = {}
    for code in codes:
        if not code.isdigit() or len(code) != 6:
            continue
        prefix = "sh" if code.startswith("6") else "sz"
        sina_code = f"{prefix}{code}"
        sina_codes.append(sina_code)
        code_map[sina_code] = code

    if not sina_codes:
        return quotes

    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    try:
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
        resp = urllib.request.urlopen(req, timeout=5)
        text = resp.read().decode("gbk", errors="ignore")

        # 新浪行情字段: 0=名称, 1=今开, 2=昨收, 3=当前价, 4=最高, 5=最低, ...
        for line in text.strip().split("\n"):
            if "=" not in line:
                continue
            var_part, data_part = line.split("=", 1)
            sina_code = var_part.split("_")[-1]
            orig_code = code_map.get(sina_code)
            if not orig_code:
                continue

            fields = data_part.strip('" ;\r').split(",")
            if len(fields) < 6:
                continue

            try:
                quotes[orig_code] = {
                    "name": fields[0],
                    "open": float(fields[1]) if fields[1] else 0,
                    "prev_close": float(fields[2]) if fields[2] else 0,
                    "price": float(fields[3]) if fields[3] else 0,
                    "high": float(fields[4]) if fields[4] else 0,
                    "low": float(fields[5]) if fields[5] else 0,
                }
                source_hits["sina"] += 1
            except (ValueError, IndexError):
                pass
    except Exception:
        pass

    # 二级回退：腾讯行情
    missing = [c for c in codes if c not in quotes]
    if missing:
        try:
            tencent_symbols = []
            tmap = {}
            for code in missing:
                if not code.isdigit() or len(code) != 6:
                    continue
                pfx = "sh" if code.startswith("6") else "sz"
                sym = f"{pfx}{code}"
                tencent_symbols.append(sym)
                tmap[sym] = code
            if tencent_symbols:
                t_url = f"https://qt.gtimg.cn/q={','.join(tencent_symbols)}"
                req = urllib.request.Request(t_url, headers={"Referer": "https://gu.qq.com/"})
                txt = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="ignore")
                for line in txt.strip().split(";"):
                    if "=" not in line:
                        continue
                    var_part, data_part = line.split("=", 1)
                    sym = var_part.split("_")[-1]
                    orig_code = tmap.get(sym)
                    if not orig_code:
                        continue
                    fields = data_part.strip('" ').split("~")
                    if len(fields) < 6:
                        continue
                    try:
                        price = float(fields[3]) if fields[3] else 0
                        prev_close = float(fields[4]) if fields[4] else 0
                        open_p = float(fields[5]) if fields[5] else 0
                        high_p = float(fields[33]) if len(fields) > 33 and fields[33] else price
                        low_p = float(fields[34]) if len(fields) > 34 and fields[34] else price
                        quotes[orig_code] = {
                            "name": fields[1] if len(fields) > 1 else "",
                            "open": open_p,
                            "prev_close": prev_close,
                            "price": price,
                            "high": high_p,
                            "low": low_p,
                        }
                        source_hits["tencent"] += 1
                    except (ValueError, IndexError):
                        continue
        except Exception:
            pass

    # 三级回退：东方财富全市场快照（仅在前两路失败时触发）
    missing = [c for c in codes if c not in quotes]
    if missing:
        try:
            import akshare as ak
            snap = ak.stock_zh_a_spot_em()
            if snap is not None and not snap.empty:
                col_map = {"代码": "code", "名称": "name", "最新价": "price", "今开": "open", "昨收": "prev_close"}
                keep = [c for c in col_map.keys() if c in snap.columns]
                if keep:
                    sdf = snap[keep].rename(columns=col_map)
                    sdf["code"] = sdf["code"].astype(str)
                    sdf = sdf[sdf["code"].isin(missing)]
                    for _, r in sdf.iterrows():
                        c = str(r.get("code", ""))
                        if not c:
                            continue
                        try:
                            p = float(r.get("price", 0) or 0)
                            op = float(r.get("open", 0) or 0)
                            pc = float(r.get("prev_close", 0) or 0)
                        except Exception:
                            continue
                        if p > 0 or pc > 0:
                            quotes[c] = {
                                "name": str(r.get("name", "")),
                                "open": op,
                                "prev_close": pc if pc > 0 else p,
                                "price": p if p > 0 else pc,
                                "high": p if p > 0 else pc,
                                "low": p if p > 0 else pc,
                            }
                            source_hits["eastmoney"] += 1
        except Exception:
            pass

    # 末级回退：本地日线缓存
    missing = [c for c in codes if c not in quotes]
    if missing:
        for code in missing:
            df = get_daily_data(code)
            if df is not None and not df.empty:
                p = float(df["close"].iloc[-1])
                prev = float(df["close"].iloc[-2]) if len(df) >= 2 else p
                quotes[code] = {
                    "name": "", "open": p, "prev_close": prev,
                    "price": p, "high": p, "low": p,
                }
                source_hits["cache"] += 1

    _append_data_source_log(
        "realtime",
        "mixed",
        (
            f"req={len(codes)} hit={len(quotes)} "
            f"sina={source_hits['sina']} tencent={source_hits['tencent']} "
            f"eastmoney={source_hits['eastmoney']} cache={source_hits['cache']}"
        ),
    )

    return quotes


def _build_trade_process_alert(entry_price: float, stop_loss: float, price: float,
                               ma50: float, ma150: float, ma200: float,
                               day_chg_pct: float, profit_pct: float,
                               days_held: int, drawdown_from_peak: float,
                               partial_sold: bool) -> dict:
    """
    交易流程状态机：买入 -> 加仓 -> 持有 -> 减仓 -> 卖出
    返回一条高优先级建议，作为每只持仓的「当前阶段 + 下一步动作」。
    """
    init_risk = max(entry_price - stop_loss, entry_price * 0.01)
    r_multiple = (price - entry_price) / init_risk if init_risk > 0 else 0
    trend_healthy = price > ma50 and ma50 >= ma150 >= ma200

    must_exit = price <= stop_loss or (price < ma50 and day_chg_pct <= -3)
    should_reduce = profit_pct >= 0.12 and (
        drawdown_from_peak >= 0.10 or day_chg_pct <= -3
    )
    can_add = (
        trend_healthy and
        not partial_sold and
        0.03 <= profit_pct <= 0.15 and
        day_chg_pct >= 0
    )

    if must_exit:
        phase = "卖出执行"
        level = "danger"
        action = "立即卖出"
        reason = (
            f"已触发退出条件（止损或跌破 MA50 弱势下行）。"
            f"当前R倍数 {r_multiple:.2f}，按纪律优先保护本金。"
        )
    elif should_reduce:
        phase = "减仓保护"
        level = "warning"
        action = "减仓 1/3~1/2"
        reason = (
            f"浮盈回撤或单日转弱，先兑现部分利润。"
            f"当前从高点回撤 {drawdown_from_peak:.1%}，单日涨跌 {day_chg_pct:+.1f}% 。"
        )
    elif can_add:
        phase = "加仓窗口"
        level = "success"
        action = "加仓 1/3 初始仓位"
        reason = (
            f"趋势健康且已脱离成本区，满足「先盈利再加仓」。"
            f"当前盈利 {profit_pct:.1%}，R倍数 {r_multiple:.2f}。"
        )
    elif trend_healthy:
        phase = "持有跟踪"
        level = "success"
        action = "持有并抬升止损"
        reason = (
            f"均线结构仍为多头，持仓第 {days_held} 天，继续跟踪趋势，"
            f"按利润进度上移止损。"
        )
    else:
        phase = "持有观察"
        level = "info"
        action = "观望，不加仓"
        reason = (
            "趋势未确认强化或动能不足，避免主观加仓。"
            "仅保留原仓位并等待明确方向。"
        )

    return {
        "level": level,
        "action": action,
        "title": f"交易流程阶段：{phase}",
        "reason": (
            f"{reason}\n\n"
            f"流程进度：买入(已完成) -> 加仓(条件触发才执行) -> 持有(趋势健康) -> "
            f"减仓(转弱保护) -> 卖出(触发纪律)。"
        ),
    }


def sepa_risk_assessment(code: str, entry_price: float, stop_loss: float,
                         shares: int, entry_date: str,
                         realtime_price: float, quote: dict,
                         partial_sold: bool = False) -> list[dict]:
    """
    基于《股票魔法师》SEPA 策略综合研判每只持仓，返回告警/建议列表。
    每条包含: level(danger/warning/success/info), action(卖出/减仓/持有/加仓),
    title, reason(书中策略依据)
    """
    import numpy as np
    from datetime import datetime, date

    alerts = []
    df = get_daily_data(code)
    if df is None or len(df) < 50:
        return alerts

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values
    n = len(close)
    price = realtime_price if realtime_price > 0 else float(close[-1])
    prev_close = quote.get("prev_close", float(close[-1]))
    today_open = quote.get("open", price)
    today_high = quote.get("high", price)
    today_low = quote.get("low", price)

    profit_pct = (price - entry_price) / entry_price if entry_price > 0 else 0
    day_chg_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0

    # 持仓天数
    try:
        ed = datetime.strptime(entry_date, "%Y-%m-%d").date()
        days_held = (date.today() - ed).days
    except Exception:
        days_held = 0

    ma50 = float(np.mean(close[-50:])) if n >= 50 else price
    ma150 = float(np.mean(close[-150:])) if n >= 150 else price
    ma200 = float(np.mean(close[-200:])) if n >= 200 else price
    vol_50 = float(np.mean(volume[-50:])) if n >= 50 else 1
    today_vol = quote.get("volume", float(volume[-1]) if n > 0 else 0)

    # Peak since entry (approximate)
    peak = float(np.max(high[-max(days_held, 1):])) if days_held > 0 and n >= days_held else price
    drawdown_from_peak = (peak - price) / peak if peak > 0 else 0

    # === 交易流程主卡片（买/加/持/减/卖） ===
    alerts.append(
        _build_trade_process_alert(
            entry_price=entry_price,
            stop_loss=stop_loss,
            price=price,
            ma50=ma50,
            ma150=ma150,
            ma200=ma200,
            day_chg_pct=day_chg_pct,
            profit_pct=profit_pct,
            days_held=days_held,
            drawdown_from_peak=drawdown_from_peak,
            partial_sold=partial_sold,
        )
    )

    # === 规则1: 硬止损 (第10章) ===
    if price <= stop_loss:
        alerts.append({
            "level": "danger",
            "action": "立即卖出",
            "title": f"触发硬止损 ¥{stop_loss:.2f}",
            "reason": f"第10章「绝对止损线」: 现价 {price:.2f} 已跌破止损 {stop_loss:.2f}。"
                      f"Minervini 强调止损线不可协商，亏损控制在 7-8% 以内是存活前提。",
        })

    # === 规则2: 高潮顶检测 (第12章) ===
    if profit_pct > 0.15 and days_held > 20:
        spread_20 = float(np.mean(high[-20:] - low[-20:])) if n >= 20 else 1
        today_spread = today_high - today_low
        if today_spread > spread_20 * 2 and today_vol > vol_50 * 2.5:
            alerts.append({
                "level": "danger",
                "action": "考虑卖出",
                "title": "高潮顶信号：竭尽放量",
                "reason": f"第12章「高潮顶部」: 今日振幅 {today_spread:.2f} 为近20日均幅 {spread_20:.2f} 的 "
                          f"{today_spread/spread_20:.1f}倍，且放量。长期上涨后的巨量大振幅是见顶典型信号。",
            })

        if today_open > 0:
            body = abs(price - today_open)
            upper_shadow = today_high - max(price, today_open)
            if body > 0 and upper_shadow > body * 2:
                alerts.append({
                    "level": "warning",
                    "action": "减仓观望",
                    "title": "长上影线冲高回落",
                    "reason": f"第12章: 上影线 {upper_shadow:.2f} > 实体 {body:.2f}×2，"
                              f"获利盘集中抛售导致冲高回落，后续可能转弱。",
                })

    # === 规则3: Stage 3/4 退出 (第5章) ===
    if n >= 200:
        below_ma50_days = sum(1 for c in close[-5:] if c < ma50)
        if below_ma50_days >= 4:
            alerts.append({
                "level": "danger",
                "action": "卖出",
                "title": "Stage 3 预警：连续跌破 MA50",
                "reason": f"第5章「阶段分析」: 近5日有 {below_ma50_days} 日收于50日均线 ({ma50:.2f}) 下方。"
                          f"Stage 2 → Stage 3 转换意味着上升趋势结束，应果断离场。",
            })

        ma200_vals = close[-10:]
        ma200_recent = [float(np.mean(close[max(0,n-200+i):n-200+i+200])) for i in range(-10, 0)] if n >= 210 else []
        if len(ma200_recent) >= 5 and all(ma200_recent[i] < ma200_recent[i-1] for i in range(-4, 0)):
            alerts.append({
                "level": "danger",
                "action": "清仓",
                "title": "Stage 4：200日均线持续下行",
                "reason": "第5章: 200日均线连续走低确认股票进入 Stage 4 下降阶段，应彻底离场。",
            })

    # === 规则4: 渐进止损建议 (第10章) ===
    if profit_pct >= 0.20:
        new_stop = entry_price * 1.15
        if stop_loss < new_stop:
            alerts.append({
                "level": "success",
                "action": "上调止损至 ¥{:.2f}".format(new_stop),
                "title": f"盈利 {profit_pct:.0%}，建议锁定利润",
                "reason": f"第10章「渐进止损」: 盈利超过20%后，止损应上调至+15%（¥{new_stop:.2f}），"
                          f"确保至少锁定15%利润。当前止损 ¥{stop_loss:.2f} 过低。",
            })
    elif profit_pct >= 0.10:
        new_stop = entry_price * 1.05
        if stop_loss < new_stop:
            alerts.append({
                "level": "info",
                "action": "上调止损至 ¥{:.2f}".format(new_stop),
                "title": f"盈利 {profit_pct:.0%}，可提升止损",
                "reason": f"第10章: 盈利10%后建议止损提至+5%（¥{new_stop:.2f}），保护利润不回吐。",
            })
    elif profit_pct >= 0.05:
        new_stop = entry_price
        if stop_loss < new_stop:
            alerts.append({
                "level": "info",
                "action": "上调止损至保本",
                "title": f"盈利 {profit_pct:.0%}，建议保本止损",
                "reason": f"第10章: 盈利5%后将止损提至买入价（¥{entry_price:.2f}），确保不亏。",
            })

    # === 规则5: 从高点回撤保护 ===
    if drawdown_from_peak >= 0.15 and profit_pct > 0:
        alerts.append({
            "level": "warning",
            "action": "减仓",
            "title": f"从高点 {peak:.2f} 回撤 {drawdown_from_peak:.0%}",
            "reason": f"第11章: 从最高价回撤超过15%，趋势可能反转。"
                      f"Minervini 建议回撤达到峰值利润的1/3时保护利润。",
        })

    # === 规则6: 8周持仓规则 (第12章) ===
    if profit_pct >= 0.20 and days_held <= 15:
        alerts.append({
            "level": "success",
            "action": "持有至少8周",
            "title": f"快速获利者：{days_held}天涨{profit_pct:.0%}",
            "reason": f"第12章「8周持仓规则」: 在1-3周内暴涨20%+的股票是潜在大牛股，"
                      f"至少持有8周(40个交易日)给它成长空间，期间只触发硬止损。",
        })

    # === 规则7: 部分止盈 (第11章) ===
    if profit_pct >= 0.20 and not partial_sold:
        alerts.append({
            "level": "success",
            "action": "卖出1/2仓位",
            "title": f"盈利 {profit_pct:.0%}，建议部分止盈",
            "reason": f"第11章「卖出法则」: 盈利达到20-25%时卖出一半仓位兑现利润，"
                      f"剩余仓位用移动止损跟踪，让利润奔跑。",
        })

    # === 规则8: 时间止损 (第10章) ===
    if days_held >= 15 and -0.02 < profit_pct < 0.05:
        alerts.append({
            "level": "warning",
            "action": "考虑卖出",
            "title": f"持有{days_held}天仅涨{profit_pct:.1%}",
            "reason": f"第10章「时间止损」: 买入后3周内若未明显上涨（<5%），"
                      f"说明时机不对。Minervini 建议该涨不涨就离场，释放资金寻找更好机会。",
        })

    # === 规则9: 趋势模板健康度 ===
    if n >= 200:
        above_ma50 = price > ma50
        above_ma150 = price > ma150
        above_ma200 = price > ma200
        ma_order = ma50 > ma150 > ma200

        if not above_ma50:
            alerts.append({
                "level": "warning",
                "action": "关注",
                "title": "跌破50日均线",
                "reason": f"第3章「趋势模板」: 股价 {price:.2f} 已跌破 MA50({ma50:.2f})，"
                          f"Stage 2 上升趋势的关键支撑被打破，趋势可能转弱。",
            })
        elif ma_order and above_ma50 and profit_pct > 0:
            alerts.append({
                "level": "success",
                "action": "持有",
                "title": "趋势健康，均线多头排列",
                "reason": f"第3章: MA50({ma50:.2f}) > MA150({ma150:.2f}) > MA200({ma200:.2f})，"
                          f"股价在所有均线上方，Stage 2 上升趋势完好，继续持有。",
            })

    # === 当日异动提醒 ===
    if day_chg_pct <= -5:
        alerts.append({
            "level": "danger",
            "action": "检查止损",
            "title": f"今日暴跌 {day_chg_pct:.1f}%",
            "reason": f"单日跌幅超过5%是异常信号。检查是否有利空消息，"
                      f"如果跌破止损位应无条件执行止损。",
        })
    elif day_chg_pct >= 8:
        if profit_pct > 0.15:
            alerts.append({
                "level": "info",
                "action": "警惕高潮顶",
                "title": f"今日大涨 {day_chg_pct:.1f}%",
                "reason": f"第12章: 长期上涨后的单日暴涨可能是高潮顶信号（尤其伴随放量），"
                          f"关注明日是否出现反转。",
            })

    # 无告警时给出默认持有建议
    if not alerts:
        alerts.append({
            "level": "info",
            "action": "持有",
            "title": "暂无异常信号",
            "reason": f"持仓 {days_held} 天，盈亏 {profit_pct:.1%}，"
                      f"各项指标正常，继续按策略持有。",
        })

    return alerts


def generate_prediction(df: pd.DataFrame, forecast_days: int = 20) -> dict:
    """
    生成价格预测线（历史回测 + 未来预测）。
    使用多因子模型：线性回归趋势 + 均线回归 + 波动率包络。

    返回:
      - backtest_dates: 历史日期列表
      - backtest_pred: 历史回测预测值（模型在每个时点的预测）
      - forecast_dates: 未来日期列表
      - forecast_mid: 未来预测中线
      - forecast_upper: 预测上界（+1σ）
      - forecast_lower: 预测下界（-1σ）
      - divergences: 历史上实际 vs 预测背离的点列表
    """
    import numpy as np
    from datetime import timedelta

    close = df["close"].values.astype(float)
    dates = pd.to_datetime(df["date"]).values
    n = len(close)

    if n < 60:
        return {}

    # --- 1) 历史回测预测：在每个时点用过去60日数据预测下一日 ---
    window = 60
    backtest_start = max(window, n - 250)
    backtest_dates = []
    backtest_pred = []

    for i in range(backtest_start, n):
        segment = close[i - window:i]
        x = np.arange(window)

        # 线性趋势
        slope, intercept = np.polyfit(x, segment, 1)
        trend_val = intercept + slope * window

        # 均线回归（价格向MA20靠拢）
        ma20 = np.mean(segment[-20:])
        ma_pull = ma20 * 0.3 + trend_val * 0.7

        backtest_dates.append(dates[i])
        backtest_pred.append(round(float(ma_pull), 2))

    backtest_pred_arr = np.array(backtest_pred)
    actual_arr = close[backtest_start:n]

    # --- 2) 背离检测 ---
    divergences = []
    for i in range(len(backtest_pred)):
        actual = float(actual_arr[i])
        pred = float(backtest_pred_arr[i])
        if actual == 0 or pred == 0:
            continue
        diff_pct = (actual - pred) / pred * 100
        if abs(diff_pct) > 5:
            divergences.append({
                "date": str(pd.Timestamp(backtest_dates[i]).date()),
                "actual": round(actual, 2),
                "predicted": round(pred, 2),
                "diff_pct": round(diff_pct, 2),
                "direction": "上偏" if diff_pct > 0 else "下偏",
            })

    # --- 3) 未来预测 ---
    recent = close[-window:]
    x = np.arange(window)
    slope, intercept = np.polyfit(x, recent, 1)

    ma20_now = float(np.mean(close[-20:]))
    ma50_now = float(np.mean(close[-50:])) if n >= 50 else ma20_now
    volatility = float(np.std(close[-20:]))

    last_date = pd.Timestamp(dates[-1])
    forecast_dates = []
    forecast_mid = []
    forecast_upper = []
    forecast_lower = []

    for d in range(1, forecast_days + 1):
        fdate = last_date + timedelta(days=int(d * 1.5))
        trend_val = intercept + slope * (window + d)
        # 均线锚定：趋势 70% + 当前MA50 30%
        mid = trend_val * 0.7 + ma50_now * 0.3
        # 不确定性随时间增长
        uncertainty = volatility * np.sqrt(d) * 0.5

        forecast_dates.append(fdate)
        forecast_mid.append(round(float(mid), 2))
        forecast_upper.append(round(float(mid + uncertainty), 2))
        forecast_lower.append(round(float(mid - uncertainty), 2))

    # --- 4) 综合评估 ---
    last_price = float(close[-1])
    pred_20d = forecast_mid[-1] if forecast_mid else last_price
    pred_change_pct = (pred_20d - last_price) / last_price * 100

    # 最近5日的实际 vs 预测偏差
    recent_divergence = 0
    if len(backtest_pred) >= 5:
        recent_actual = actual_arr[-5:]
        recent_pred = backtest_pred_arr[-5:]
        recent_divergence = float(np.mean((recent_actual - recent_pred) / recent_pred * 100))

    return {
        "backtest_dates": [str(pd.Timestamp(d).date()) for d in backtest_dates],
        "backtest_pred": [float(v) for v in backtest_pred],
        "forecast_dates": [str(d.date()) for d in forecast_dates],
        "forecast_mid": forecast_mid,
        "forecast_upper": forecast_upper,
        "forecast_lower": forecast_lower,
        "divergences": divergences[-10:],
        "pred_20d_price": round(pred_20d, 2),
        "pred_20d_change_pct": round(pred_change_pct, 2),
        "recent_divergence_pct": round(recent_divergence, 2),
        "volatility": round(volatility, 2),
    }


def _estimate_strategy_bias(profiled_df: pd.DataFrame) -> float:
    """从策略画像信号估计预测偏置（仅用于可视化，不作为交易信号）。"""
    if profiled_df is None or profiled_df.empty:
        return 0.0
    latest = profiled_df.iloc[-1]
    bias = 0.0
    try:
        if bool(latest.get("buy_signal", False)):
            bias += 0.035
        if bool(latest.get("strategy_exit_signal", False)):
            bias -= 0.05
        scale = float(latest.get("risk_unit_scale", 1.0) or 1.0)
        bias += (scale - 1.0) * 0.03
        phase = str(latest.get("emotion_phase", ""))
        if phase in {"启动", "发酵"}:
            bias += 0.02
        elif phase in {"高潮", "退潮"}:
            bias -= 0.01
        heat = float(latest.get("sector_heat_score", 0) or 0)
        valuation = float(latest.get("valuation_score", 0) or 0)
        crowding = float(latest.get("crowding_score", 0) or 0)
        if heat > 60:
            bias += 0.01
        if valuation > 60:
            bias += 0.01
        if crowding > 75:
            bias -= 0.015
    except Exception:
        return 0.0
    return float(max(-0.12, min(0.12, bias)))


def _apply_prediction_bias(base_pred: dict, last_price: float, bias: float) -> dict:
    """按策略偏置平移预测曲线。"""
    factor = 1.0 + bias
    out = dict(base_pred)
    for k in ["backtest_pred", "forecast_mid", "forecast_upper", "forecast_lower"]:
        vals = out.get(k, [])
        if isinstance(vals, list):
            out[k] = [round(float(v) * factor, 2) for v in vals]
    pred_price = float(out.get("pred_20d_price", last_price) or last_price) * factor
    out["pred_20d_price"] = round(pred_price, 2)
    out["pred_20d_change_pct"] = round((pred_price - last_price) / max(last_price, 1e-6) * 100, 2)
    # 近5日偏差做一致性修正，避免多策略面板显示完全同值。
    base_recent = float(base_pred.get("recent_divergence_pct", 0) or 0)
    out["recent_divergence_pct"] = round(base_recent - bias * 100 * 0.8, 2)
    out["strategy_bias_pct"] = round(bias * 100, 2)
    return out


def _style_bias_from_features(df: pd.DataFrame, strategy_id: str, params: dict) -> float:
    """
    基于价格特征+策略风格的偏置项（用于多策略预测分化）。
    偏置范围控制在 [-12%, +12%]。
    """
    if df is None or df.empty or "close" not in df.columns:
        return 0.0
    close = pd.to_numeric(df["close"], errors="coerce").dropna().values.astype(float)
    if len(close) < 25:
        return 0.0
    p0 = float(close[-1])
    mom20 = (p0 / float(close[-21]) - 1.0) if len(close) >= 21 and close[-21] > 0 else 0.0
    vol20 = float(np.std(close[-20:]) / max(np.mean(close[-20:]), 1e-6))
    ma20 = float(np.mean(close[-20:]))
    ma60 = float(np.mean(close[-60:])) if len(close) >= 60 else ma20
    trend = (ma20 / max(ma60, 1e-6) - 1.0)

    # 不同体系对同一市场状态给不同偏置：趋势派更看重动量，价值派偏逆向。
    trend_pack = {"sepa", "canslim", "turtle", "livermore", "covell", "larry_williams"}
    value_pack = {"graham", "buffett", "lynch", "cn_pm_danbin", "cn_pm_linyuan", "cn_inst_qiuguolu"}
    fast_pack = {"cn_yz_chaogu", "cn_yz_zhaolao", "cn_yz_asking"}

    if strategy_id in trend_pack:
        bias = 0.55 * mom20 + 0.35 * trend - 0.15 * vol20
    elif strategy_id in value_pack:
        bias = -0.20 * mom20 + 0.25 * trend - 0.10 * vol20
    elif strategy_id in fast_pack:
        bias = 0.35 * mom20 - 0.45 * vol20 + 0.10 * trend
    else:
        bias = 0.30 * mom20 + 0.20 * trend - 0.12 * vol20

    # 参数微调：让同体系不同参数也有分化
    risk_per_trade = float(params.get("risk_per_trade", 0.01) or 0.01)
    rs_min = float(params.get("rs_min", 70) or 70)
    bias += (risk_per_trade - 0.01) * 2.0
    bias += (70 - rs_min) / 1000.0

    return float(max(-0.12, min(0.12, bias)))


def _strategy_anchor_bias(strategy_id: str) -> float:
    """
    策略固定锚点偏置，确保不同策略在同一标的上有可分辨差异。
    返回范围约 [-1.2%, +1.2%]。
    """
    sid = str(strategy_id or "")
    seed = sum(ord(ch) for ch in sid)
    # 11 档离散偏置，中心对称
    bucket = (seed % 11) - 5
    return float(bucket * 0.0024)


def generate_strategy_predictions(
    df: pd.DataFrame,
    strategy_ids: list[str],
    strategy_params_map: dict[str, dict] | None = None,
    code: str | None = None,
    forecast_days: int = 20,
) -> dict[str, dict]:
    """
    生成策略体系下的多预测结果（用于个股分析可视化叠加）。
    返回: {strategy_id: prediction_dict}
    """
    PREDICTION_VERSION = "v2-diff"
    if df is None or df.empty:
        return {}
    base_pred = generate_prediction(df, forecast_days=forecast_days)
    if not base_pred:
        return {}
    last_price = float(df["close"].iloc[-1])
    result: dict[str, dict] = {}
    bias_map: dict[str, float] = {}
    fin_data_map: dict[str, dict] = {}
    if code:
        fin_df = _load_financial_offline()
        if fin_df is not None and not fin_df.empty and "code" in fin_df.columns:
            one = fin_df[fin_df["code"].astype(str) == str(code)]
            if not one.empty:
                rr = one.iloc[0]
                fin_data_map[str(code)] = {"pe_dynamic": rr.get("pe_dynamic"), "pb": rr.get("pb")}
    for sid in strategy_ids:
        if sid not in STRATEGY_PROFILES:
            continue
        params = get_strategy_default_params(sid)
        custom = (strategy_params_map or {}).get(sid, {})
        if custom:
            params.update(custom)
        try:
            fin_data = fin_data_map.get(str(code), None) if code else None

            profiled = apply_backtest_profile(df.copy(), sid, fin_data, params)
            signal_bias = _estimate_strategy_bias(profiled)
            style_bias = _style_bias_from_features(df, sid, params)
            anchor_bias = _strategy_anchor_bias(sid)
            bias = signal_bias * 0.45 + style_bias * 0.35 + anchor_bias * 0.20
        except Exception:
            bias = _strategy_anchor_bias(sid)
        pred = _apply_prediction_bias(base_pred, last_price, bias)
        pred["strategy_id"] = sid
        pred["strategy_name"] = strategy_name(sid)
        pred["prediction_version"] = PREDICTION_VERSION
        result[sid] = pred
        bias_map[sid] = bias

    # 若策略结果仍过于接近，按策略锚点做最小可分离拉伸，避免“整列同值”。
    if len(result) >= 2:
        items = list(result.items())
        vals = [float(v.get("pred_20d_change_pct", 0) or 0) for _, v in items]
        if (max(vals) - min(vals)) < 0.25:  # 小于0.25%视为过于接近
            anchors = sorted(
                [(sid, bias_map.get(sid, _strategy_anchor_bias(sid))) for sid, _ in items],
                key=lambda x: x[1]
            )
            n = len(anchors)
            mid = (n - 1) / 2.0
            step_pct = 0.22  # 每档至少0.22%差异
            for i, (sid, _) in enumerate(anchors):
                p = result[sid]
                adj_pct = (i - mid) * step_pct
                new_chg = float(p.get("pred_20d_change_pct", 0) or 0) + adj_pct
                new_price = last_price * (1.0 + new_chg / 100.0)
                p["pred_20d_change_pct"] = round(new_chg, 2)
                p["pred_20d_price"] = round(new_price, 2)
                p["strategy_bias_pct"] = round(float(p.get("strategy_bias_pct", 0) or 0) + adj_pct, 2)
                p["recent_divergence_pct"] = round(float(p.get("recent_divergence_pct", 0) or 0) - adj_pct * 0.6, 2)
                p["prediction_version"] = PREDICTION_VERSION
    return result


def get_multi_period_pnl(code: str, realtime_price: float,
                         entry_price: float,
                         force_refresh: bool = False) -> dict:
    """
    计算多周期盈亏 + 趋势预测。
    realtime_price 必须是实时价格（来自 get_realtime_prices），否则数据不准。
    """
    import numpy as np
    df = get_daily_data(code, force_refresh=force_refresh)
    if df is None or df.empty:
        return {}

    close = df["close"].values
    n = len(close)
    last_close = float(close[-1])

    # 如果实时价和最新收盘价差距过大(>15%)，可能是数据异常，取实时价为准
    price = realtime_price if realtime_price > 0 else last_close

    # 持仓盈亏（vs 买入价）
    pos_pnl = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0

    # 各周期股价涨跌（vs 对应天数前的收盘价）
    periods = {
        "当日": 1, "7日": 5, "30日": 22,
        "一季度": 63, "半年": 125, "一年": 250,
    }
    result = {"实时价": round(price, 2), "持仓盈亏%": round(pos_pnl, 2)}

    for label, days in periods.items():
        if n > days:
            ref_idx = max(0, n - days - 1)
            ref_price = float(close[ref_idx])
            chg = (price - ref_price) / ref_price * 100
            result[label] = round(chg, 2)
        else:
            result[label] = None

    # 线性回归趋势预测（基于最近60日收盘价 + 实时价）
    lookback = min(60, n)
    recent = list(close[-lookback:])
    if abs(price - last_close) / max(last_close, 0.01) > 0.001:
        recent.append(price)
    recent = np.array(recent)

    x = np.arange(len(recent))
    if len(recent) >= 10 and np.std(recent) > 0:
        slope, intercept = np.polyfit(x, recent, 1)
        predicted_20d = intercept + slope * (len(recent) + 20)
        pred_pct = (predicted_20d - price) / price * 100

        ma5 = float(np.mean(close[-5:])) if n >= 5 else price
        ma20 = float(np.mean(close[-20:])) if n >= 20 else price
        momentum = "上升" if ma5 > ma20 else "下降"

        if pred_pct > 5 and momentum == "上升":
            trend = "看涨"
        elif pred_pct < -5 and momentum == "下降":
            trend = "看跌"
        else:
            trend = "震荡"

        result["预测20日"] = round(pred_pct, 2)
        result["趋势"] = trend
        result["动量"] = momentum
    else:
        result["预测20日"] = None
        result["趋势"] = "数据不足"
        result["动量"] = "-"

    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_sector_stocks(sector_name: str, sector_type: str = "行业板块") -> list[str]:
    """获取指定板块的成分股代码列表"""
    import akshare as ak
    try:
        if sector_type == "行业板块":
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
        else:
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
        if df is not None and not df.empty:
            return df["代码"].tolist()
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def _get_index_data_cached() -> pd.DataFrame:
    fetcher = get_fetcher()
    try:
        return fetcher.get_index_data(force_refresh=False)
    except TypeError:
        # 兼容已缓存的旧版 DataFetcher 实例（无 force_refresh 参数）。
        return fetcher.get_index_data()


def get_index_data(force_refresh: bool = False) -> pd.DataFrame:
    fetcher = get_fetcher()
    if force_refresh:
        try:
            return fetcher.get_index_data(force_refresh=True)
        except TypeError:
            return fetcher.get_index_data()
    return _get_index_data_cached()


def get_market_regime() -> dict:
    """获取当前市场状态"""
    index_df = get_index_data()
    mrf = MarketRegimeFilter(get_config().market)
    regime_df = mrf.compute_regime(index_df)
    if regime_df.empty:
        return {"market_ok": True, "dist_count": 0}
    latest = regime_df.iloc[-1]
    return {
        "market_ok": bool(latest["market_ok"]),
        "dist_count": int(latest["dist_count"]),
        "regime_df": regime_df,
    }


@st.cache_data(ttl=86400, show_spinner=False)
def get_company_profile(code: str) -> dict | None:
    """获取公司详情：基本信息 + 财务指标"""
    import akshare as ak

    profile: dict = {"code": code}
    names = get_stock_names()
    profile["name"] = names.get(code, "")

    # 1) 个股基本信息 (东方财富)
    try:
        info_df = ak.stock_individual_info_em(symbol=code)
        if info_df is not None and not info_df.empty:
            info_map = dict(zip(info_df["item"], info_df["value"]))
            profile["总市值"] = info_map.get("总市值", "-")
            profile["流通市值"] = info_map.get("流通市值", "-")
            profile["行业"] = info_map.get("行业", "-")
            profile["上市时间"] = info_map.get("上市时间", "-")
            profile["总股本"] = info_map.get("总股本", "-")
            profile["流通股"] = info_map.get("流通股", "-")
    except Exception:
        pass

    # 2) 实时行情快照 (PE / PB 等)
    try:
        fin_df = get_fetcher().get_financial_data()
        if fin_df is not None and not fin_df.empty:
            row = fin_df[fin_df["code"] == code]
            if not row.empty:
                row = row.iloc[0]
                profile["市盈率"] = row.get("pe_dynamic", "-")
                profile["市净率"] = row.get("pb", "-")
                if "总市值" not in profile or profile["总市值"] == "-":
                    profile["总市值"] = row.get("total_mv", "-")
                if "流通市值" not in profile or profile["流通市值"] == "-":
                    profile["流通市值"] = row.get("circ_mv", "-")
    except Exception:
        pass

    # 3) 财务摘要 (同花顺)
    try:
        fin_report = get_fetcher().get_stock_financial_report(code)
        if fin_report is not None and not fin_report.empty:
            profile["financial_table"] = fin_report.head(8)
    except Exception:
        pass

    return profile


def analyze_stock(code: str, force_refresh: bool = False) -> dict | None:
    """综合分析单只股票"""
    code = str(code).strip()
    if len(code) != 6 or not code.isdigit():
        return None
    df = get_daily_data(code, force_refresh=force_refresh)
    if (df is None or len(df) < 200) and not force_refresh:
        # 首次缓存不足时自动再尝试一次强制刷新，避免被旧空缓存卡住。
        df = get_daily_data(code, force_refresh=True)
    # 个股分析页允许更短历史窗口，避免因历史不足被直接判空。
    if df is None or len(df) < 20:
        return None

    config = get_config()
    tt = TrendTemplate(config.trend)
    vcp = VCPDetector(config.vcp)

    all_data = {code: df}
    rs_ratings = tt._compute_rs_ratings(all_data)
    rs = rs_ratings.get(code, 0)

    trend_result = tt.check(df)
    vcp_result = vcp.detect(df)

    close = float(df["close"].iloc[-1])
    ma50 = float(df["close"].iloc[-50:].mean()) if len(df) >= 50 else close
    ma150 = float(df["close"].iloc[-150:].mean()) if len(df) >= 150 else close
    ma200 = float(df["close"].iloc[-200:].mean()) if len(df) >= 200 else close
    high_52w = float(df["high"].iloc[-250:].max()) if len(df) >= 250 else float(df["high"].max())
    low_52w = float(df["low"].iloc[-250:].min()) if len(df) >= 250 else float(df["low"].min())

    names = get_stock_names()

    return {
        "code": code,
        "name": names.get(code, ""),
        "close": close,
        "ma50": round(ma50, 2),
        "ma150": round(ma150, 2),
        "ma200": round(ma200, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "rs_rating": rs,
        "trend_pass": trend_result.get("passed", False),
        "trend_details": trend_result,
        "vcp": vcp_result,
        "df": df,
    }


def _stock_sector_cache_path() -> str:
    return os.path.join(get_config().data.cache_dir, "stock_sector_map.csv")


def _load_stock_sector_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    cache_path = _stock_sector_cache_path()
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, dtype=str)
            if not df.empty and "code" in df.columns and "sector" in df.columns:
                mapping = dict(zip(df["code"], df["sector"]))
        except Exception:
            pass
    return mapping


def _save_stock_sector_mapping(mapping: dict[str, str]) -> None:
    cache_path = _stock_sector_cache_path()
    try:
        if mapping:
            pd.DataFrame(list(mapping.items()), columns=["code", "sector"]).to_csv(
                cache_path, index=False
            )
    except Exception:
        pass


def get_stock_sector(code: str) -> str:
    """
    查询单只股票所属行业板块（通过东方财富个股信息接口）。
    结果缓存到本地文件，避免重复查询。
    """
    import akshare as ak
    mapping = _load_stock_sector_mapping()

    if code in mapping:
        return mapping[code]

    # 查询个股信息
    try:
        info = ak.stock_individual_info_em(symbol=code)
        if info is not None and not info.empty:
            info_map = dict(zip(info["item"], info["value"]))
            sector = info_map.get("行业", "")
            if sector:
                mapping[code] = sector
                _save_stock_sector_mapping(mapping)
                return sector
    except Exception:
        pass

    return "-"


def get_stock_sectors_batch(codes: list[str], fetch_missing: bool = False,
                            max_network_calls: int = 20) -> dict[str, str]:
    """
    批量获取行业板块：
    - 默认只读本地缓存，避免页面卡顿；
    - 可选 fetch_missing=True 时，限制网络补全次数。
    """
    import akshare as ak

    mapping = _load_stock_sector_mapping()
    result = {code: mapping.get(code, "-") for code in codes}

    if not fetch_missing:
        return result

    missing = [c for c in codes if result.get(c, "-") in ("", "-")]
    updated = False
    for code in missing[:max_network_calls]:
        try:
            info = ak.stock_individual_info_em(symbol=code)
            if info is not None and not info.empty:
                info_map = dict(zip(info["item"], info["value"]))
                sector = info_map.get("行业", "")
                if sector:
                    mapping[code] = sector
                    result[code] = sector
                    updated = True
        except Exception:
            continue

    if updated:
        _save_stock_sector_mapping(mapping)
    return result


def _load_stock_list_offline() -> pd.DataFrame:
    cache_dir = get_config().data.cache_dir
    stock_path = os.path.join(cache_dir, "stock_list.csv")
    if os.path.exists(stock_path):
        try:
            df = pd.read_csv(stock_path, dtype={"code": str})
            if not df.empty and "code" in df.columns:
                if "name" not in df.columns:
                    df["name"] = df["code"]
                return df[["code", "name"]]
        except Exception:
            pass

    codes = []
    try:
        for fname in os.listdir(cache_dir):
            if fname.startswith("daily_") and fname.endswith(".csv"):
                code = fname[6:-4]
                if len(code) == 6 and code.isdigit():
                    codes.append(code)
    except Exception:
        pass

    if not codes:
        return pd.DataFrame(columns=["code", "name"])
    codes = sorted(set(codes))
    return pd.DataFrame({"code": codes, "name": codes})


def _load_daily_data_offline(codes: list[str]) -> dict[str, pd.DataFrame]:
    cache_dir = get_config().data.cache_dir
    min_days = int(get_config().data.min_listing_days)
    result: dict[str, pd.DataFrame] = {}
    for code in codes:
        path = os.path.join(cache_dir, f"daily_{code}.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, parse_dates=["date"])
            if "code" not in df.columns:
                df["code"] = code
            df = df.sort_values("date").reset_index(drop=True)
            if len(df) >= min_days:
                result[code] = df
        except Exception:
            continue
    return result


def _load_financial_offline() -> pd.DataFrame:
    path = os.path.join(get_config().data.cache_dir, "financial.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype={"code": str})
    except Exception:
        return pd.DataFrame()


def run_screening(sample_size: int = 300, progress_callback=None,
                   sector_codes: list[str] | None = None,
                   strategy_id: str = "sepa",
                   strategy_params: dict | None = None,
                   offline_only: bool = False,
                   force_refresh: bool = False) -> list[dict]:
    """运行选股。支持多策略画像（strategy_id）。"""
    import numpy as np
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed

    config = get_config()
    fetcher = get_fetcher()
    tt = TrendTemplate(config.trend)

    if strategy_id not in STRATEGY_PROFILES:
        strategy_id = "sepa"

    stock_list = _load_stock_list_offline() if offline_only else get_stock_list(force_refresh=force_refresh)
    if stock_list is None or stock_list.empty:
        return []
    if sector_codes:
        stock_list = stock_list[stock_list["code"].isin(sector_codes)]
        if stock_list.empty:
            return []
        sample = stock_list.head(min(sample_size, len(stock_list)))
    else:
        sample = stock_list.sample(n=min(sample_size, len(stock_list)), random_state=42)

    if progress_callback:
        progress_callback(0.1, "加载缓存数据中..." if offline_only else "下载数据中...")
    if offline_only:
        all_data = _load_daily_data_offline(sample["code"].astype(str).tolist())
    else:
        all_data = fetcher.get_all_daily_data(sample, force_refresh=force_refresh)

    if progress_callback:
        progress_callback(0.5, "趋势模板筛选...")
    trend_passed = tt.screen(all_data)

    if trend_passed.empty:
        return []

    names = dict(zip(stock_list["code"].astype(str), stock_list["name"].astype(str))) if offline_only else get_stock_names(force_refresh=force_refresh)
    financial_df = _load_financial_offline() if offline_only else get_fetcher().get_financial_data(force_refresh=force_refresh)
    fin_map = {}
    if financial_df is not None and not financial_df.empty and "code" in financial_df.columns:
        for _, r in financial_df.iterrows():
            fin_map[str(r.get("code", ""))] = {
                "pe_dynamic": r.get("pe_dynamic"),
                "pb": r.get("pb"),
            }
    candidates = []

    total = len(trend_passed)
    def _build_candidate(row) -> dict | None:
        code = row["code"]
        rs = float(row["rs_rating"])
        df = all_data.get(code)
        if df is None or len(df) < 200:
            return None

        # 每个线程独立实例，避免共享状态造成竞争。
        vcp_local = VCPDetector(config.vcp)
        vcp_result = vcp_local.detect(df)
        close = float(df["close"].iloc[-1])
        high_52w = float(df["high"].iloc[-250:].max()) if len(df) >= 250 else float(df["high"].max())

        n = config.vcp.tight_close_days
        recent_closes = df["close"].iloc[-(n + 1):-1].values
        tight = False
        if len(recent_closes) >= n and np.min(recent_closes) > 0:
            spread = (np.max(recent_closes) - np.min(recent_closes)) / np.min(recent_closes)
            tight = spread <= config.vcp.tight_close_range

        pivot = vcp_result.get("pivot_price", 0)
        if pivot <= 0:
            pivot = float(df["close"].iloc[-20:].max())
        dist_to_pivot = (close - pivot) / pivot if pivot > 0 else 0

        vol_20 = float(df["volume"].iloc[-20:].mean())
        vol_50 = float(df["volume"].iloc[-50:].mean()) if len(df) >= 50 else vol_20
        vol_ratio = vol_20 / vol_50 if vol_50 > 0 else 1.0

        score = rs * 0.3
        score += (1 if vcp_result["has_vcp"] else 0) * 20
        score += vcp_result.get("num_contractions", 0) * 3
        score += (1 if tight else 0) * 10
        score += (1 if vcp_result.get("breakout_today") else 0) * 25
        score += max(0, -dist_to_pivot * 100) * 0.5
        score += (1 if vol_ratio < 0.8 else 0) * 5
        score += (close / high_52w) * 10

        base = {
            "代码": code,
            "名称": names.get(code, ""),
            "板块": "-",
            "价格": round(close, 2),
            "RS": int(rs),
            "评分": round(score, 1),
            "VCP": "✓" if vcp_result["has_vcp"] else "-",
            "收缩": vcp_result.get("num_contractions", 0),
            "枢纽": round(pivot, 2),
            "距枢纽%": round(dist_to_pivot * 100, 1),
            "突破": "突破!" if vcp_result.get("breakout_today") else ("~" if dist_to_pivot > -0.05 else "-"),
            "紧密": "✓" if tight else "-",
            "量比": round(vol_ratio, 2),
            "离高点%": round((close / high_52w - 1) * 100, 1),
            "code": code,
        }
        return apply_screening_profile(
            base, df, strategy_id, fin_map.get(code), strategy_params
        )

    rows = [row for _, row in trend_passed.iterrows()]
    max_workers = min(8, max(2, (os.cpu_count() or 4)), max(1, total))
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_build_candidate, row) for row in rows]
        for fut in as_completed(futures):
            item = fut.result()
            if item is not None:
                candidates.append(item)
            done += 1
            if progress_callback:
                progress_callback(0.5 + 0.4 * done / total, f"VCP 检测 {done}/{total}...")

    candidates.sort(key=lambda x: x["评分"], reverse=True)

    # 板块补全：先用缓存全量秒回，再对头部候选限量联网补全，避免全量逐只查询导致卡顿。
    if candidates:
        all_codes = [c["代码"] for c in candidates]
        sector_map = get_stock_sectors_batch(all_codes, fetch_missing=False)
        if not offline_only:
            head_codes = [c["代码"] for c in candidates[:60]]
            head_map = get_stock_sectors_batch(head_codes, fetch_missing=True, max_network_calls=12)
            sector_map.update(head_map)
        for item in candidates:
            item["板块"] = sector_map.get(item["代码"], "-")
            item["策略"] = strategy_name(strategy_id)

    if progress_callback:
        progress_callback(1.0, "完成!")
    return candidates


def _build_financial_map() -> dict[str, dict]:
    fin_df = get_fetcher().get_financial_data()
    if fin_df is None or fin_df.empty or "code" not in fin_df.columns:
        return {}
    result = {}
    for _, r in fin_df.iterrows():
        code = str(r.get("code", ""))
        if not code:
            continue
        result[code] = {
            "pe_dynamic": r.get("pe_dynamic"),
            "pb": r.get("pb"),
        }
    return result


def _build_strategy_diagnostics(signal_data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    从策略信号中提取诊断样本：
    - phase_timeline: 回测期间各日期的情绪阶段买点数量
    - factor_samples: 买点对应的热度/估值/拥挤度样本
    """
    phase_rows = []
    factor_rows = []
    for code, df in signal_data.items():
        if df is None or df.empty:
            continue
        cols = set(df.columns)
        need_buy = "buy_signal" in cols
        if not need_buy:
            continue
        buy_df = df[df["buy_signal"] == True]  # noqa: E712
        if buy_df.empty:
            continue

        if "emotion_phase" in cols:
            for _, r in buy_df.iterrows():
                phase_rows.append({
                    "date": pd.to_datetime(r["date"]),
                    "phase": str(r.get("emotion_phase", "中性")),
                    "count": 1,
                })

        for _, r in buy_df.iterrows():
            factor_rows.append({
                "date": pd.to_datetime(r["date"]),
                "code": code,
                "heat": float(r.get("sector_heat_score", 0.0) or 0.0),
                "valuation": float(r.get("valuation_score", 0.0) or 0.0),
                "crowding": float(r.get("crowding_score", 0.0) or 0.0),
                "phase": str(r.get("emotion_phase", "中性")),
            })

    phase_df = pd.DataFrame()
    if phase_rows:
        phase_df = pd.DataFrame(phase_rows)
        phase_df = (
            phase_df.groupby(["date", "phase"], as_index=False)["count"]
            .sum()
            .sort_values("date")
        )
    factor_df = pd.DataFrame(factor_rows) if factor_rows else pd.DataFrame()
    return phase_df, factor_df


def run_backtest(sample_size: int = 200, start_date: str = "20220601",
                 progress_callback=None, strategy_id: str = "sepa",
                 strategy_params: dict | None = None):
    """运行单策略回测"""
    if strategy_id not in STRATEGY_PROFILES:
        strategy_id = "sepa"
    params_final = get_strategy_default_params(strategy_id)
    if strategy_params:
        params_final.update(strategy_params)

    config = get_config()
    fetcher = get_fetcher()
    strategy = get_strategy()
    backtester = Backtester(config)

    stock_list = get_stock_list()
    sample = stock_list.sample(n=min(sample_size, len(stock_list)), random_state=2024)

    if progress_callback:
        progress_callback(0.1, "下载数据...")
    all_data = fetcher.get_all_daily_data(sample)
    index_df = get_index_data()

    if progress_callback:
        progress_callback(0.4, "生成信号...")
    signal_data, market_df = strategy.generate_signals_for_backtest(all_data, index_df)
    fin_map = _build_financial_map()
    profiled_signal = {}
    for code, df in signal_data.items():
        profiled_signal[code] = apply_backtest_profile(
            df, strategy_id, fin_map.get(code), params_final
        )

    if progress_callback:
        progress_callback(0.7, "运行回测...")
    result = backtester.run(profiled_signal, market_regime_df=market_df, start_date=start_date)
    result.strategy_id = strategy_id
    result.strategy_name = strategy_name(strategy_id)
    result.strategy_params = params_final
    phase_df, factor_df = _build_strategy_diagnostics(profiled_signal)
    result.phase_timeline = phase_df
    result.factor_samples = factor_df

    if progress_callback:
        progress_callback(1.0, "完成!")
    return result, index_df


def run_backtest_multi(strategy_ids: list[str], sample_size: int = 200,
                       start_date: str = "20220601", progress_callback=None,
                       strategy_params_map: dict[str, dict] | None = None):
    """运行多策略回测（共享同一份样本与行情数据，便于横向比较）。"""
    valid_ids = [sid for sid in strategy_ids if sid in STRATEGY_PROFILES]
    if not valid_ids:
        valid_ids = ["sepa"]

    config = get_config()
    fetcher = get_fetcher()
    strategy = get_strategy()

    stock_list = get_stock_list()
    if stock_list is None or stock_list.empty:
        stock_list = _load_stock_list_offline()
    if stock_list is None or stock_list.empty:
        return {}, get_index_data(force_refresh=False)
    sample_n = min(sample_size, len(stock_list))
    if sample_n <= 0:
        return {}, get_index_data(force_refresh=False)
    sample = stock_list.sample(n=sample_n, random_state=2024)

    if progress_callback:
        progress_callback(0.1, "下载数据...")
    all_data = fetcher.get_all_daily_data(sample)
    if not all_data:
        all_data = fetcher.get_all_daily_data(sample, force_refresh=True)
    if not all_data:
        # 随机样本可能恰好都无缓存，回退到“本地已有日线”的股票池重试。
        offline_pool = _load_stock_list_offline()
        if offline_pool is not None and not offline_pool.empty:
            off_n = min(sample_size, len(offline_pool))
            off_sample = offline_pool.sample(n=off_n, random_state=2025)
            all_data = _load_daily_data_offline(off_sample["code"].astype(str).tolist())
    index_df = get_index_data(force_refresh=False)
    if index_df is None or index_df.empty:
        index_df = get_index_data(force_refresh=True)
    if not all_data:
        return {}, index_df

    if progress_callback:
        progress_callback(0.35, "生成基础信号...")
    try:
        base_signal_data, market_df = strategy.generate_signals_for_backtest(all_data, index_df)
    except Exception:
        # 指数接口异常时，用样本股票聚合构造临时指数再试一次。
        try:
            first_df = next(iter(all_data.values()))
            if first_df is not None and not first_df.empty:
                pseudo = first_df[["date", "open", "high", "low", "close", "volume"]].copy()
                pseudo = pseudo.sort_values("date").reset_index(drop=True)
                base_signal_data, market_df = strategy.generate_signals_for_backtest(all_data, pseudo)
                index_df = pseudo
            else:
                return {}, index_df
        except Exception:
            return {}, index_df
    fin_map = _build_financial_map()

    results = {}
    total = len(valid_ids)
    for i, sid in enumerate(valid_ids):
        try:
            profiled_signal = {}
            params = get_strategy_default_params(sid)
            custom = (strategy_params_map or {}).get(sid, None)
            if custom:
                params.update(custom)
            for code, df in base_signal_data.items():
                profiled_signal[code] = apply_backtest_profile(df, sid, fin_map.get(code), params)

            if progress_callback:
                progress_callback(0.4 + 0.55 * (i / max(total, 1)),
                                  f"运行回测 {strategy_name(sid)} ({i+1}/{total})...")
            bt = Backtester(config)
            result = bt.run(profiled_signal, market_regime_df=market_df, start_date=start_date)
            result.strategy_id = sid
            result.strategy_name = strategy_name(sid)
            result.strategy_params = params
            phase_df, factor_df = _build_strategy_diagnostics(profiled_signal)
            result.phase_timeline = phase_df
            result.factor_samples = factor_df
            results[sid] = result
        except Exception:
            # 单策略失败不阻断整体多策略回测，继续其余策略。
            continue

    if progress_callback:
        progress_callback(1.0, "完成!")
    return results, index_df
