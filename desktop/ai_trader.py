"""
AI 决策引擎
调用 DeepSeek API 分析持仓+市场数据，输出买卖决策并自动执行。
"""
import os
import json
import logging
import urllib.request
import numpy as np
import re
from datetime import date, datetime

_log = logging.getLogger("ai_trader")

from core.ai.decision_engine import run_ai_decision as run_ai_decision_with_engine
from core.ai.context_builder import (
    build_ai_portfolio_context_text,
    build_candidates_context_text,
    build_decision_history_context_text,
    build_market_context_text,
)
from desktop.ai_portfolio import get_state, buy, sell, get_log
from desktop.data_access import RepoCompatConnection

_AI_GUARD_MODES = {"auto", "manual", "full_auto", "arena_hot_llm"}
_BUY_MIN_SCORE_BY_MARKET = {
    "strong_trend": 70,
    "rotation": 75,
    "neutral": 80,
    "risk_off": 10_000,
}
_MAX_DAILY_BUYS = 1
_MAX_DAILY_TRADES = 4
_MIN_HOLD_DAYS_FOR_AI_ROTATION_SELL = 5
_MIN_STOP_DISTANCE_PCT = 0.08
_WEAK_BOARD_5D_THRESHOLD = 0.0


def _get_api_config() -> dict:
    """从设置中读取 API 配置。"""
    cfg_path = os.path.join("data_cache", "push_config.json")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = "https://api.deepseek.com/v1"
    model = "deepseek-chat"
    provider = "DeepSeek"

    if not api_key and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            api_key = cfg.get("ai_api_key", "") or api_key
            base_url = cfg.get("ai_base_url", "") or base_url
            model = cfg.get("ai_model", "") or model
            provider = cfg.get("ai_provider", "") or provider
        except Exception:
            pass

    # 也检查 kv_store
    if not api_key:
        try:
            conn = RepoCompatConnection()
            cur = conn.execute("SELECT value FROM kv_store WHERE key='ai_config'")
            row = cur.fetchone()
            conn.close()
            if row:
                cfg = json.loads(row[0])
                api_key = cfg.get("api_key", "")
                base_url = cfg.get("base_url", base_url)
                model = cfg.get("model", model)
                provider = cfg.get("provider", provider)
        except Exception:
            pass

    return {"api_key": api_key, "base_url": base_url, "model": model, "provider": provider}


def save_ai_config(api_key: str, base_url: str = "", model: str = ""):
    """保存 AI API 配置。"""
    conn = RepoCompatConnection()
    cfg = {
        "api_key": api_key,
        "base_url": base_url or "https://api.deepseek.com/v1",
        "model": model or "deepseek-chat",
    }
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        ("ai_config", json.dumps(cfg), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _call_llm(prompt: str, system: str = "") -> str:
    """调用 DeepSeek/OpenAI 兼容 API。"""
    cfg = _get_api_config()
    if not cfg["api_key"]:
        return "ERROR: 未配置 API Key。请在设置页面配置 DeepSeek API Key。"

    url = f"{cfg['base_url']}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # 根据 prompt 长度动态调整超时：短 prompt 60s，长 prompt 120s
    prompt_len = sum(len(m["content"]) for m in messages)
    api_timeout = 120 if prompt_len > 3000 else 60

    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode("utf-8")

    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=payload, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
            })
            resp = urllib.request.urlopen(req, timeout=api_timeout)
            body = json.loads(resp.read().decode("utf-8", errors="ignore"))
            choices = body.get("choices") if isinstance(body, dict) else None
            if isinstance(choices, list) and choices:
                first = choices[0] if isinstance(choices[0], dict) else {}
                message = first.get("message") if isinstance(first, dict) else {}
                content = message.get("content") if isinstance(message, dict) else ""
                if isinstance(content, str) and content.strip():
                    return content
            err_msg = body.get("error") if isinstance(body, dict) else None
            raise ValueError(f"unexpected LLM response: {err_msg or body}")
        except Exception as e:
            last_err = e
            if attempt == 0 and "timed out" in str(e).lower():
                import time
                time.sleep(2)
                continue
            break
    return f"ERROR: API 调用失败: {last_err}"


def _build_market_context() -> str:
    """从统一上下文构建器获取当前市场上下文。"""
    return build_market_context_text()


def _build_portfolio_context(mode: str = "auto") -> str:
    """从统一上下文构建器获取当前 AI 持仓上下文。"""
    return build_ai_portfolio_context_text(mode)


def _compute_strategy_scores(code: str, closes, highs, lows, volumes) -> dict:
    """用本地策略引擎计算单只股票的多策略评分和信号。"""
    n = len(closes)
    if n < 50:
        return {"score": 0, "signals": [], "strategies": {}}

    price = float(closes[-1])
    ma50 = float(np.mean(closes[-50:]))
    ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
    ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

    results = {}

    # 趋势模板 (SEPA)
    sepa_score = 0
    sepa_signals = []
    if price > ma50:
        sepa_score += 15
    if n >= 200 and ma50 > ma150 > ma200:
        sepa_score += 20
        sepa_signals.append("多头排列")
    if n >= 200:
        ma200_prev = float(np.mean(closes[-222:-22])) if n >= 222 else ma200
        if ma200 > ma200_prev:
            sepa_score += 10
    h52 = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
    if h52 > 0 and price >= h52 * 0.75:
        sepa_score += 10
    results["SEPA趋势"] = {"score": sepa_score, "signals": sepa_signals, "view": "看多" if sepa_score >= 40 else "中性" if sepa_score >= 20 else "看空"}

    # VCP 形态
    vcp_score = 0
    vcp_signals = []
    if n >= 40:
        vol_early = float(np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6))
        vol_recent = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6))
        if vol_recent < vol_early * 0.8:
            vcp_score += 25
            vcp_signals.append("波动收缩")
    if n >= 20:
        high20 = float(np.max(closes[-21:-1]))
        if price >= high20:
            vcp_score += 30
            vcp_signals.append("突破20日高点")
        elif price >= high20 * 0.98:
            vcp_score += 15
            vcp_signals.append("接近突破")
    results["VCP形态"] = {"score": vcp_score, "signals": vcp_signals, "view": "突破" if vcp_score >= 40 else "收缩" if vcp_score >= 20 else "无形态"}

    # 价值评估 (格雷厄姆)
    value_score = 0
    value_signals = []
    if price < ma200 * 0.9:
        value_score += 30
        value_signals.append("低于MA200的90%")
    mom60 = (price / float(closes[-61]) - 1) if n >= 61 and closes[-61] > 0 else 0
    if mom60 < -0.15:
        value_score += 20
        value_signals.append(f"60日跌{mom60*100:.0f}%超跌")
    results["价值评估"] = {"score": value_score, "signals": value_signals, "view": "低估" if value_score >= 30 else "合理"}

    # 动量 (短线)
    mom_score = 0
    mom_signals = []
    mom5 = (price / float(closes[-6]) - 1) * 100 if n >= 6 and closes[-6] > 0 else 0
    mom20 = (price / float(closes[-21]) - 1) * 100 if n >= 21 and closes[-21] > 0 else 0
    if mom5 > 5:
        mom_score += 20
        mom_signals.append(f"5日涨{mom5:.1f}%")
    if mom20 > 10:
        mom_score += 20
        mom_signals.append(f"20日涨{mom20:.1f}%")
    results["动量"] = {"score": mom_score, "signals": mom_signals, "view": "强势" if mom_score >= 30 else "中性" if mom_score >= 10 else "弱势"}

    # 情绪博弈
    emo_score = 0
    emo_signals = []
    if n >= 20:
        vol_ma20 = float(np.mean(volumes[-20:])) if np.mean(volumes[-20:]) > 0 else 1
        vol_ratio = float(volumes[-1]) / vol_ma20
        if vol_ratio > 1.5 and mom5 > 3:
            emo_score += 25
            emo_signals.append(f"放量{vol_ratio:.1f}倍+短期强势")
        elif vol_ratio > 1.2:
            emo_score += 10
            emo_signals.append(f"量比{vol_ratio:.1f}")
        # 涨停检测
        if n >= 2 and closes[-2] > 0:
            day_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
            if day_pct >= 9.5:
                emo_score += 20
                emo_signals.append("涨停")
    results["情绪博弈"] = {"score": emo_score, "signals": emo_signals, "view": "高潮" if emo_score >= 30 else "活跃" if emo_score >= 10 else "平淡"}

    # 事件驱动
    event_score = 0
    event_signals = []
    if n >= 2:
        day_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
        vol_ma20 = float(np.mean(volumes[-20:])) if n >= 20 and np.mean(volumes[-20:]) > 0 else 1
        vol_ratio = float(volumes[-1]) / vol_ma20 if vol_ma20 > 0 else 1
        if abs(day_pct) > 5 and vol_ratio > 2:
            event_score += 30
            event_signals.append(f"异动{day_pct:+.1f}%+放量{vol_ratio:.1f}倍")
        elif abs(day_pct) > 3 and vol_ratio > 1.5:
            event_score += 15
            event_signals.append(f"小异动{day_pct:+.1f}%")
    results["事件驱动"] = {"score": event_score, "signals": event_signals, "view": "有事件" if event_score >= 15 else "无事件"}

    # 基金持仓跟踪
    fund_score = 0
    fund_signals = []
    try:
        conn_fund = RepoCompatConnection()
        cur_f = conn_fund.execute(
            "SELECT holding_funds, change_type FROM fund_holdings WHERE code=? "
            "ORDER BY updated_at DESC LIMIT 1", (code,)
        )
        row_f = cur_f.fetchone()
        conn_fund.close()
        if row_f:
            hf, ct = row_f
            if hf and int(hf) >= 100:
                fund_score += 15
                fund_signals.append(f"{hf}只基金持有")
            if hf and int(hf) >= 500:
                fund_score += 15
                fund_signals.append("超500只基金重仓")
            if ct == "增持":
                fund_score += 20
                fund_signals.append("基金增持")
            elif ct == "新进":
                fund_score += 25
                fund_signals.append("基金新进")
            elif ct == "减持":
                fund_score -= 10
                fund_signals.append("基金减持")
    except Exception:
        pass
    results["基金持仓"] = {"score": max(fund_score, 0), "signals": fund_signals, "view": "重仓" if fund_score >= 30 else "持有" if fund_score > 0 else "无持仓"}

    total_score = sum(r["score"] for r in results.values())
    all_signals = []
    for r in results.values():
        all_signals.extend(r["signals"])

    return {"score": total_score, "signals": all_signals, "strategies": results}


def _build_candidates_context(board: str = "人工智能", limit: int = 30) -> str:
    """从统一上下文构建器获取候选股上下文。"""
    return build_candidates_context_text(board=board, limit=limit)


def _build_decision_history_context() -> str:
    """从统一上下文构建器获取历史决策反馈。"""
    return build_decision_history_context_text()


def run_ai_decision(board: str = "人工智能", mode: str = "auto", extra_prompt: str = "") -> dict:
    """兼容入口：真实实现已迁移到 core.ai.decision_engine。"""
    return run_ai_decision_with_engine(
        llm_call=_call_llm,
        board=board,
        mode=mode,
        extra_prompt=extra_prompt,
    )


def _calc_atr_stop(code: str, entry_price: float, multiplier: float = 2.5) -> float:
    """基于 ATR（20日平均真实波幅）计算动态止损价。

    至少留出 _MIN_STOP_DISTANCE_PCT 的波动空间，避免 ATR 过小时止损贴脸。
    """
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT high, low, close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 21",
        (code,),
    )
    rows = cur.fetchall()
    conn.close()

    min_stop_price = entry_price * (1 - _MIN_STOP_DISTANCE_PCT)

    if len(rows) < 5:
        return round(min_stop_price, 2)

    rows = rows[::-1]
    tr_list = []
    for i in range(1, len(rows)):
        h, l, prev_c = rows[i][0], rows[i][1], rows[i - 1][2]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

    atr = float(np.mean(tr_list[-20:])) if len(tr_list) >= 20 else float(np.mean(tr_list))
    atr_stop = entry_price - multiplier * atr
    stop = min(atr_stop, min_stop_price)
    return round(max(stop, entry_price * 0.85), 2)


def update_trailing_stops(mode: str = "full_auto") -> list[str]:
    """
    更新持仓的跟踪止损：如果现价创新高，上移止损线。
    止损线 = max(原止损, 最高价 - 2×ATR)
    """
    from desktop.ai_portfolio import get_state
    state = get_state(mode)
    if not state["positions"]:
        return []

    conn = RepoCompatConnection()
    updates = []

    for p in state["positions"]:
        code = p["code"]
        old_stop = p.get("stop_loss", 0)

        cur = conn.execute(
            "SELECT high, low, close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 21",
            (code,),
        )
        rows = cur.fetchall()
        if len(rows) < 5:
            continue

        rows_r = rows[::-1]
        highest = max(r[0] for r in rows_r)

        tr_list = []
        for i in range(1, len(rows_r)):
            h, l, prev_c = rows_r[i][0], rows_r[i][1], rows_r[i - 1][2]
            tr_list.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        atr = float(np.mean(tr_list[-20:])) if len(tr_list) >= 20 else float(np.mean(tr_list))

        new_stop = round(highest - 2 * atr, 2)
        new_stop = max(new_stop, old_stop)

        if new_stop > old_stop:
            conn.execute(
                "UPDATE ai_positions SET stop_loss=? WHERE mode=? AND code=? AND status='open'",
                (new_stop, mode, code),
            )
            updates.append(f"{code}: 止损 {old_stop:.2f} → {new_stop:.2f}（ATR跟踪上移）")

    conn.commit()
    conn.close()
    return updates


def _get_real_price(code: str) -> float:
    """获取股票的真实最新价格（优先实时行情，退而求其次用最新日K收盘价）。"""
    # 尝试实时行情
    try:
        from desktop.realtime_data import get_realtime_quotes
        q = get_realtime_quotes([code], force=True)
        px = q.get(code, {}).get("price", 0)
        if px and px > 0:
            return float(px)
    except Exception:
        pass
    # 退而求其次：最新日K收盘价
    try:
        conn = RepoCompatConnection()
        cur = conn.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,),
        )
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return 0.0


def _load_kv_json(key: str, default=None):
    try:
        conn = RepoCompatConnection()
        row = conn.execute("SELECT value FROM kv_store WHERE key=?", (key,)).fetchone()
        conn.close()
        if not row or row[0] is None:
            return default
        return json.loads(row[0])
    except Exception:
        return default


def _extract_score_from_text(text: str) -> int:
    m = re.search(r"(?:综合|评分)\s*(\d{2,3})\s*分?", str(text or ""))
    return int(m.group(1)) if m else 0


def _lookup_candidate_meta(code: str) -> dict:
    meta = {"score": 0, "board": "", "strategy_views": "", "momentum_view": "", "sepa_view": ""}

    try:
        from desktop.scan_store import resolve_scan_results

        scan_rows, _, _ = resolve_scan_results()
    except Exception:
        scan_rows = []

    for item in scan_rows:
        if str(item.get("代码", "") or "") == code:
            try:
                meta["score"] = int(item.get("评分", 0) or 0)
            except Exception:
                meta["score"] = 0
            meta["board"] = str(item.get("板块", "") or "")
            break

    try:
        conn = RepoCompatConnection()
        if not meta["board"]:
            row = conn.execute("SELECT board FROM board_stocks WHERE code=? LIMIT 1", (code,)).fetchone()
            if row:
                meta["board"] = str(row[0] or "")
        rows = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        ).fetchall()
        conn.close()
        if len(rows) >= 50:
            rows = list(reversed(rows))
            closes = np.array([row[0] for row in rows])
            highs = np.array([row[1] for row in rows])
            lows = np.array([row[2] for row in rows])
            volumes = np.array([row[3] for row in rows])
            scores = _compute_strategy_scores(code, closes, highs, lows, volumes)
            meta["score"] = max(meta["score"], int(scores.get("score", 0) or 0))
            strategies = scores.get("strategies", {})
            meta["strategy_views"] = " ".join(
                f"{name}:{strategy.get('view', '')}"
                for name, strategy in strategies.items()
                if strategy.get("score", 0) > 0
            )
            meta["sepa_view"] = strategies.get("SEPA趋势", {}).get("view", "")
            meta["momentum_view"] = strategies.get("动量", {}).get("view", "")
    except Exception:
        pass

    return meta


def _daily_trade_counts(mode: str) -> tuple[int, int]:
    today_prefix = date.today().isoformat()
    try:
        conn = RepoCompatConnection()
        rows = conn.execute(
            """
            SELECT action, COUNT(1)
            FROM ai_trade_log
            WHERE mode=? AND substr(timestamp, 1, 10)=?
            GROUP BY action
            """,
            (mode, today_prefix),
        ).fetchall()
        conn.close()
    except Exception:
        return 0, 0
    counts = {str(action or "").upper(): int(count or 0) for action, count in rows}
    buys = counts.get("BUY", 0)
    trades = buys + counts.get("SELL", 0)
    return buys, trades


def _check_ai_buy_guard(mode: str, decision: dict) -> str | None:
    if mode not in _AI_GUARD_MODES:
        return None

    code = str(decision.get("code", "") or "")
    reason = str(decision.get("reason", "") or "")
    meta = _lookup_candidate_meta(code)
    score = int(decision.get("score", 0) or 0) or _extract_score_from_text(reason) or meta["score"]

    try:
        from desktop.market_state import get_market_state_snapshot
        market = get_market_state_snapshot() or {}
    except Exception:
        market = {}

    market_state = str(market.get("state", "neutral") or "neutral")
    min_score = _BUY_MIN_SCORE_BY_MARKET.get(market_state, 80)
    weak_boards = set(market.get("sector_bottom3", []) or [])
    rotation = _load_kv_json("sector_rotation", {}) or {}
    weak_boards.update(rotation.get("bottom3", []) or [])
    board = meta.get("board", "")

    buys_today, trades_today = _daily_trade_counts(mode)
    if trades_today >= _MAX_DAILY_TRADES:
        return f"今日交易已达上限{_MAX_DAILY_TRADES}笔，禁止继续高换手"
    if buys_today >= _MAX_DAILY_BUYS:
        return f"今日买入已达上限{_MAX_DAILY_BUYS}只，禁止继续扩仓"
    if market_state == "risk_off":
        return f"市场状态为 risk_off（{market.get('reason', '')}），只允许卖出/观察"
    if board and board in weak_boards:
        return f"命中弱势板块[{board}]，禁止买入"
    if score < min_score:
        return f"综合评分{score}低于当前市场门槛{min_score}"
    if meta.get("sepa_view") == "看空":
        return "SEPA趋势看空，禁止买入"
    if meta.get("momentum_view") == "弱势":
        return "动量弱势，禁止买入"
    if board:
        try:
            from desktop.arena.loss_analysis import get_board_return_window

            board_5d = get_board_return_window(board)
            if board_5d is not None and board_5d <= _WEAK_BOARD_5D_THRESHOLD:
                return f"板块[{board}]近5日{board_5d:+.1f}%未上涨，禁止追买"
        except Exception:
            pass
    return None


def _check_ai_sell_guard(mode: str, code: str, price: float) -> str | None:
    if mode not in _AI_GUARD_MODES:
        return None
    try:
        conn = RepoCompatConnection()
        row = conn.execute(
            "SELECT entry_date, entry_price, stop_loss FROM ai_positions WHERE mode=? AND code=? AND status='open'",
            (mode, code),
        ).fetchone()
        conn.close()
        if not row:
            return None
        entry_date, entry_price, stop_loss = row
        hold_days = (date.today() - date.fromisoformat(str(entry_date))).days
        pnl_pct = (price - float(entry_price)) / float(entry_price) * 100 if entry_price else 0
        if price <= float(stop_loss or 0) or pnl_pct <= -5:
            return None
        if hold_days < _MIN_HOLD_DAYS_FOR_AI_ROTATION_SELL:
            return f"持仓仅{hold_days}天，未触发止损前禁止为换仓卖出"
    except Exception:
        return None
    return None


def execute_ai_decisions(decisions: list[dict], mode: str = "auto") -> list[str]:
    """执行 AI 的买卖决策。mode: 'auto'=自主仓, 'manual'=推荐仓
    注意：买入/卖出价格始终使用真实市场价格，忽略 LLM 建议价。
    """
    results = []
    from desktop.ai_portfolio import get_state

    holding_codes = {
        str(p.get("code", "") or "")
        for p in get_state(mode).get("positions", [])
        if p.get("code")
    }

    for d in decisions:
        action = d.get("action", "").lower()
        code = d.get("code", "")
        reason = d.get("reason", "")

        if action == "buy":
            name = d.get("name", "")
            shares = int(d.get("shares", 0))
            if not code or not shares:
                results.append(f"跳过无效买入: {d}")
                continue
            if code in holding_codes:
                results.append(f"已持有 {code}，跳过重复买入")
                continue
            block_reason = _check_ai_buy_guard(mode, d)
            if block_reason:
                results.append(f"风控拦截买入 {code}: {block_reason}")
                continue
            real_price = _get_real_price(code)
            ai_price = float(d.get("price", 0))
            if real_price <= 0:
                real_price = ai_price
            if real_price <= 0:
                results.append(f"跳过 {code}: 无法获取真实价格")
                continue
            if ai_price > 0 and abs(real_price - ai_price) / ai_price > 0.05:
                _log.warning(
                    f"价格修正 {code}: AI建议{ai_price:.2f} → 真实{real_price:.2f} "
                    f"(偏差{(real_price/ai_price-1)*100:+.1f}%)"
                )
            # 动态仓位调整：根据评分和波动率调整买入股数
            try:
                score = int(d.get("score", 0) or 0)
                conn_vol = RepoCompatConnection()
                vol_rows = conn_vol.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 20",
                    (code,),
                ).fetchall()
                conn_vol.close()
                if len(vol_rows) >= 10:
                    vol_closes = [r[0] for r in reversed(vol_rows)]
                    volatility = float(np.std(vol_closes) / np.mean(vol_closes))
                    # 高评分多买、高波动少买
                    score_factor = min(1.5, max(0.5, score / 60)) if score > 0 else 1.0
                    vol_factor = min(1.5, max(0.5, 0.04 / max(volatility, 0.01)))
                    adj = score_factor * vol_factor
                    new_shares = int(shares * adj / 100) * 100
                    if new_shares >= 100 and new_shares != shares:
                        _log.info(f"仓位调整 {code}: {shares}→{new_shares}股 "
                                  f"(评分系数{score_factor:.2f} 波动系数{vol_factor:.2f})")
                        shares = new_shares
            except Exception:
                pass
            stop_loss = _calc_atr_stop(code, real_price)
            msg = buy(mode, code, name, real_price, shares, stop_loss, f"AI决策: {reason}")
            results.append(msg)
            holding_codes.add(code)

        elif action == "sell":
            price = _get_real_price(code)
            if price > 0:
                block_reason = _check_ai_sell_guard(mode, code, price)
                if block_reason:
                    results.append(f"风控拦截卖出 {code}: {block_reason}")
                    continue
                msg = sell(mode, code, price, f"AI决策: {reason}")
                results.append(msg)
            else:
                results.append(f"卖出失败 {code}: 无法获取价格")

        elif action == "hold":
            results.append(f"持有 {code}: {reason}")

    return results


def execute_sell_signals_across_modes(
    decisions: list[dict],
    modes: tuple[str, ...] = ("auto", "custom", "quantum"),
) -> list[str]:
    """Apply AI sell signals to matching holdings across selected simulated portfolios."""
    results: list[str] = []
    seen: set[tuple[str, str]] = set()
    sell_decisions = [
        item
        for item in decisions or []
        if str(item.get("action", "") or "").lower() == "sell" and str(item.get("code", "") or "")
    ]
    if not sell_decisions:
        return results

    for decision in sell_decisions:
        code = str(decision.get("code", "") or "")
        reason = str(decision.get("reason", "") or "")
        fallback_price = float(decision.get("price", 0) or 0)
        for mode in modes:
            key = (mode, code)
            if key in seen:
                continue
            seen.add(key)
            state = get_state(mode)
            positions = state.get("positions", []) if isinstance(state, dict) else []
            if not any(str(item.get("code", "") or "") == code for item in positions):
                continue
            price = _get_real_price(code) or fallback_price
            if price <= 0:
                results.append(f"[{mode}] 卖出失败 {code}: 无法获取价格")
                continue
            msg = sell(mode, code, price, f"AI卖出信号: {reason}")
            results.append(msg)
    return results


def run_auto_cycle(board: str = "人工智能") -> list[str]:
    """半自主仓：分析随时可跑，执行仅在交易时间。"""
    result = run_ai_decision(board, mode="auto")
    analysis = result.get("analysis", "")
    decisions = result.get("decisions", [])

    if not decisions:
        return [f"AI 分析完毕，暂无操作。分析: {analysis}"]

    from desktop.ai_portfolio import check_trading_time
    reject = check_trading_time()
    if reject:
        summary = "; ".join(
            f"{d.get('action','')}{d.get('code','')}" for d in decisions[:5]
        )
        return [f"📊 分析完成（{summary}），⏳ 非交易时间暂不执行: {reject}"]

    return execute_ai_decisions(decisions, mode="auto")


def run_full_auto_cycle(boards: list[str] = None) -> list[str]:
    """
    完全自主仓：多智能体协同决策（情报→分析→决策→执行）。
    分析随时可跑，实际买卖仅在交易时间执行。
    """
    if not boards:
        return ["⚠️ 未指定板块，请先勾选板块"]

    try:
        from desktop.agents import run_multi_agent_cycle
        from desktop.ai_portfolio import check_trading_time

        reject = check_trading_time()

        result = run_multi_agent_cycle(
            boards, mode="full_auto", execute=reject is None,
        )

        output = []
        for step in result.get("steps", []):
            output.append(f"{step['agent']} {step['status']}: {step['summary']}")

        if reject:
            decisions = result.get("decisions", [])
            if decisions:
                summary = "; ".join(
                    f"{d.get('action','')}{d.get('code','')}" for d in decisions[:5]
                )
                output.append(f"📊 决策已生成（{summary}），⏳ 非交易时间暂不执行: {reject}")
            else:
                output.append(f"📊 分析完成，暂无操作建议（当前非交易时间: {reject}）")
        else:
            output.extend(result.get("exec_results", []))

        return output
    except Exception as e:
        return [f"多智能体决策失败: {e}"]


