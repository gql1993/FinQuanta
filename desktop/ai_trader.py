"""
AI 决策引擎
调用 DeepSeek API 分析持仓+市场数据，输出买卖决策并自动执行。
"""
import os
import json
import logging
import urllib.request
import numpy as np
from datetime import datetime

_log = logging.getLogger("ai_trader")

from desktop.ai_portfolio import get_state, buy, sell, get_log
from desktop.data_access import RepoCompatConnection


def _get_api_config() -> dict:
    """从设置中读取 API 配置。"""
    cfg_path = os.path.join("data_cache", "push_config.json")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = "https://api.deepseek.com/v1"
    model = "deepseek-chat"

    if not api_key and os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            api_key = cfg.get("ai_api_key", "") or api_key
            base_url = cfg.get("ai_base_url", "") or base_url
            model = cfg.get("ai_model", "") or model
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
        except Exception:
            pass

    return {"api_key": api_key, "base_url": base_url, "model": model}


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
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            if attempt == 0 and "timed out" in str(e).lower():
                import time
                time.sleep(2)
                continue
            break
    return f"ERROR: API 调用失败: {last_err}"


def _build_market_context() -> str:
    """从 SQLite 构建当前市场上下文。"""
    conn = RepoCompatConnection()

    state_lines = []
    try:
        from desktop.market_state import get_market_state_snapshot
        ms = get_market_state_snapshot()
        state_lines.append("== 市场状态机 ==")
        state_lines.append(f"状态: {ms.get('state', 'neutral')}")
        state_lines.append(f"原因: {ms.get('reason', '')}")
        if ms.get("sector_top3"):
            state_lines.append(f"强势板块: {', '.join(ms['sector_top3'][:3])}")
        if ms.get("sector_bottom3"):
            state_lines.append(f"弱势板块: {', '.join(ms['sector_bottom3'][:3])}")
        state_lines.append("")
    except Exception:
        pass

    # 获取有数据的前 20 只强势股
    cur = conn.execute("""
        SELECT code, 
            (SELECT close FROM daily_kline d2 WHERE d2.code=d1.code ORDER BY date DESC LIMIT 1) as last_close,
            (SELECT close FROM daily_kline d3 WHERE d3.code=d1.code ORDER BY date DESC LIMIT 1 OFFSET 1) as prev_close
        FROM (SELECT DISTINCT code FROM daily_kline) d1
        LIMIT 100
    """)
    stocks = []
    for r in cur.fetchall():
        code, last, prev = r
        if last and prev and prev > 0:
            pct = (last - prev) / prev * 100
            stocks.append((code, last, pct))

    conn.close()

    stocks.sort(key=lambda x: x[2], reverse=True)
    top_gainers = stocks[:10]
    top_losers = stocks[-5:]

    lines = state_lines + ["== 市场快照 =="]
    lines.append("涨幅前10:")
    for code, price, pct in top_gainers:
        lines.append(f"  {code} ¥{price:.2f} {pct:+.2f}%")
    lines.append("跌幅前5:")
    for code, price, pct in top_losers:
        lines.append(f"  {code} ¥{price:.2f} {pct:+.2f}%")

    return "\n".join(lines)


def _build_portfolio_context(mode: str = "auto") -> str:
    """构建当前 AI 持仓上下文。"""
    state = get_state(mode)
    label = "AI自主仓" if mode == "auto" else "AI推荐仓"
    lines = [
        f"== {label} ==",
        f"现金: ¥{state['cash']:,.2f}",
        f"初始资金: ¥{state['initial_capital']:,.0f}",
        f"持仓数: {len(state['positions'])}",
    ]

    conn = RepoCompatConnection()
    for pos in state["positions"]:
        code = pos["code"]
        cur = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        )
        rows_db = cur.fetchall()
        if rows_db:
            rows_db = rows_db[::-1]
            closes = np.array([r[0] for r in rows_db])
            highs_a = np.array([r[1] for r in rows_db])
            lows_a = np.array([r[2] for r in rows_db])
            vols_a = np.array([r[3] for r in rows_db])
            current_price = float(closes[-1])
            scores = _compute_strategy_scores(code, closes, highs_a, lows_a, vols_a)
            strategy_views = " ".join(f"{k}:{v['view']}" for k, v in scores["strategies"].items() if v["score"] > 0)
        else:
            current_price = pos["entry_price"]
            scores = {"score": 0}
            strategy_views = "无数据"

        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"] * 100
        lines.append(
            f"  {code} {pos['name']} 买{pos['entry_price']:.2f} "
            f"现{current_price:.2f} 盈亏{pnl_pct:+.2f}% "
            f"{pos['shares']}股 {pos['entry_date']} | "
            f"策略评分{scores['score']} {strategy_views}"
        )
    conn.close()

    if state["closed_trades"]:
        lines.append(f"最近交易:")
        for t in state["closed_trades"][:5]:
            lines.append(f"  {t['code']} {t['entry_date']}→{t['exit_date']} 盈亏¥{t['pnl']:+,.0f} {t['reason']}")

    return "\n".join(lines)


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
    """
    构建候选股票上下文：
    数据来源1: 选股雷达最近扫描结果（已评分的 Top100）
    数据来源2: 按板块分组评分，取每板块 Top10 精选
    两路合并去重，确保高分股不遗漏。
    """
    conn = RepoCompatConnection()
    conn.execute("PRAGMA journal_mode=WAL")

    boards = [b.strip() for b in board.split(",") if b.strip()]
    if not boards:
        return "== 候选股票 ==\n⚠️ 未指定有效板块，无法生成候选列表"

    names = {}
    try:
        cur_n = conn.execute("SELECT code, name FROM stock_list")
        names = {r[0]: r[1] for r in cur_n.fetchall()}
    except Exception:
        pass

    # 来源1: 读取选股雷达缓存的扫描结果
    scan_candidates = []
    try:
        cur_sc = conn.execute("SELECT value, updated_at FROM kv_store WHERE key='last_scan_results'")
        row_sc = cur_sc.fetchone()
        if row_sc:
            scan_items = json.loads(row_sc[0])
            for s in scan_items[:50]:
                code = s.get("代码", "")
                if not code:
                    continue
                sc = int(s.get("评分", 0))
                signals = []
                if s.get("VCP") == "✓":
                    signals.append("VCP收缩")
                if s.get("突破") == "✓":
                    signals.append("突破")
                if s.get("建议买入", ""):
                    signals.append(s["建议买入"])
                scan_candidates.append((
                    code, s.get("名称", names.get(code, "")),
                    float(s.get("价格", "0").replace(",", "") or 0),
                    0,
                    {"score": sc, "signals": signals, "strategies": {}},
                    s.get("板块", "雷达精选"),
                ))
    except Exception:
        pass

    # 按板块分组评分，每板块取 Top10
    seen = set()
    candidates = []
    board_tops = {}

    for b in boards:
        cur_b = conn.execute("SELECT code FROM board_stocks WHERE board=?", (b,))
        codes_in_board = [r[0] for r in cur_b.fetchall()]
        board_candidates = []

        for code in codes_in_board[:80]:
            if code in seen:
                continue
            cur2 = conn.execute(
                "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
                (code,),
            )
            rows = cur2.fetchall()
            if len(rows) < 50:
                continue
            rows = rows[::-1]
            closes = np.array([r[0] for r in rows])
            highs = np.array([r[1] for r in rows])
            lows = np.array([r[2] for r in rows])
            vols = np.array([r[3] for r in rows])
            scores = _compute_strategy_scores(code, closes, highs, lows, vols)
            price = float(closes[-1])
            prev = float(closes[-2]) if len(closes) >= 2 else price
            pct = (price - prev) / prev * 100 if prev > 0 else 0
            board_candidates.append((code, names.get(code, ""), price, pct, scores, b))

        board_candidates.sort(key=lambda x: x[4]["score"], reverse=True)
        top_n = board_candidates[:10]
        board_tops[b] = len(top_n)
        for item in top_n:
            seen.add(item[0])
            candidates.append(item)

    conn.close()

    # 合并选股雷达结果（去重）
    for sc in scan_candidates:
        if sc[0] not in seen:
            seen.add(sc[0])
            candidates.append(sc)

    candidates.sort(key=lambda x: x[4]["score"], reverse=True)

    n_scan = len(scan_candidates)
    n_strong = sum(1 for c in candidates if c[4]["score"] >= 60)
    board_summary = ", ".join(f"{b}({n}只)" for b, n in board_tops.items())
    if n_scan > 0:
        board_summary += f", 雷达精选({n_scan}只)"
    lines = [
        f"== 候选股票（各板块Top10精选，共{len(candidates)}只，≥60分:{n_strong}只）==",
        f"板块来源: {board_summary}",
        "格式: 代码 名称 [板块] 现价 日涨跌% | 综合评分 | 策略判定 | 信号 | 建议",
    ]
    for code, name, price, pct, scores, brd in candidates[:limit]:
        strategy_views = " ".join(f"{k}:{v['view']}" for k, v in scores["strategies"].items() if v["score"] > 0)
        signal_str = ",".join(scores["signals"][:5]) if scores["signals"] else "无"
        sc = scores["score"]
        if sc >= 80:
            advice = "★★★ 强烈买入"
        elif sc >= 60:
            advice = "★★ 建议买入"
        elif sc >= 40:
            advice = "★ 观望"
        else:
            advice = "- 不买"
        lines.append(
            f"  {code} {name} [{brd}] ¥{price:.2f} {pct:+.2f}% | "
            f"综合{sc}分 | {strategy_views} | {signal_str} | {advice}"
        )

    if n_strong > 3:
        lines.append(f"\n⚠️ 当前有 {n_strong} 只达到买入标准（≥60分），建议积极布局多只，分散在不同板块。")
    elif n_strong > 0:
        lines.append(f"\n📌 {n_strong} 只达到买入标准，可精选买入。")

    return "\n".join(lines)


SYSTEM_PROMPT = """你是一个专业的 A 股量化交易 AI 决策引擎。你管理一个独立的 AI 模拟仓。

你的决策流程：
1. 系统已用本地策略引擎对候选股票计算了多策略评分（7个维度）：
   - SEPA趋势模板（均线排列+趋势健康度）
   - VCP形态（波动收缩+突破信号）
   - 价值评估（超跌+低估值）
   - 动量指标（短期/中期涨幅）
   - 情绪博弈（量比+涨停+赚钱效应）
   - 事件驱动（异动+放量冲击）
   - 基金持仓（机构重仓+增减持）
2. 综合所有策略评分，优先选择多策略共振（3个以上维度看多）的股票
3. 候选列表中标注了"★★★ 强烈买入"的股票，你应该重点考虑买入

交易规则：
1. 最多同时持有 10 只股票（分散风险）
2. 单只仓位不超过总资金的 15%
3. 止损线 8%，止盈目标 20%
4. 策略评分 ≥ 60 的应该买入，≥ 80 的必须买入
5. 如果候选列表中有多只 ≥60 分的股票，应该同时买入多只（不要只买一两只）
6. 持有股票如果 SEPA 转空 + 动量转弱，应卖出
7. 持有超过 20 天且涨幅不足 3% 的应卖出
8. A 股 T+1，最少买 100 股
9. 买入价格使用候选列表中的"现价"
10. 每只股票的买入股数 = 可用资金 ÷ (10 - 当前持仓数) ÷ 现价，取100的整数倍

重要：如果候选列表中有5只以上评分≥60的股票，你至少要买入3-5只，不要过于保守。

你必须以 JSON 格式回复：
{
  "analysis": "综合分析（说明市场环境和决策理由）",
  "decisions": [
    {"action": "buy", "code": "300502", "name": "新易盛", "price": 378.95, "shares": 500, "reason": "综合82分，SEPA看多+VCP突破+基金增持"},
    {"action": "buy", "code": "300308", "name": "中际旭创", "price": 180.50, "shares": 800, "reason": "综合75分，多头排列+放量+基金重仓"},
    {"action": "sell", "code": "002049", "reason": "SEPA转空+动量弱+持有超20天"},
    {"action": "hold", "code": "688981", "reason": "趋势良好继续持有"}
  ]
}

必须返回合法 JSON。"""


def _build_decision_history_context() -> str:
    """构建历史决策绩效反馈，帮助 LLM 从过去的决策中学习。"""
    try:
        conn = RepoCompatConnection()
        rows = conn.execute(
            "SELECT timestamp, decisions, actual_results "
            "FROM ai_decision_memory WHERE calibrated=1 "
            "ORDER BY timestamp DESC LIMIT 5"
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["== 历史决策回顾（近5次已校准） =="]
        for ts, dec_json, result_json in rows:
            try:
                decs = json.loads(dec_json) if dec_json else []
                results = json.loads(result_json) if result_json else {}
                pnl = results.get("avg_pnl", 0)
                correct = results.get("correct_ratio", 0)
                n = len(decs) if isinstance(decs, list) else 0
                lines.append(
                    f"  {ts[:10]}: {n}条决策, 准确率{correct:.0%}, 均收益{pnl:+.1f}%"
                )
            except Exception:
                pass
        if len(lines) <= 1:
            return ""
        lines.append("请参考历史表现，避免重复犯错，强化有效模式。")
        return "\n".join(lines)
    except Exception:
        return ""


def run_ai_decision(board: str = "人工智能", mode: str = "auto", extra_prompt: str = "") -> dict:
    """运行一次 AI 决策。mode: 'auto'/'manual'/'full_auto'"""
    market = _build_market_context()
    portfolio = _build_portfolio_context(mode)
    candidates = _build_candidates_context(board)
    history = _build_decision_history_context()

    # 所有模式：注入策略轮动 + 板块轮动 + 学习引擎反馈
    evolution_ctx = ""
    try:
        from desktop.openclaw_learner import get_enhanced_full_auto_prompt
        evolution_ctx = get_enhanced_full_auto_prompt()
    except Exception:
        pass
    # 策略轮动和板块轮动
    rotation_ctx = ""
    try:
        conn_r = RepoCompatConnection()
        sr = conn_r.execute("SELECT value FROM kv_store WHERE key='strategy_rotation'").fetchone()
        if sr:
            sd = json.loads(sr[0])
            rotation_ctx += f"\n== 策略轮动 ==\n当前最强策略: {sd.get('best_name','SEPA')}(综合分{sd.get('best_score',0):.0f})\n"
        br = conn_r.execute("SELECT value FROM kv_store WHERE key='sector_rotation'").fetchone()
        if br:
            bd = json.loads(br[0])
            top3 = bd.get("top3", [])
            if top3:
                rotation_ctx += f"最强板块: {', '.join(top3[:3])}，建议重点关注\n"
                bottom3 = bd.get("bottom3", [])
                if bottom3:
                    rotation_ctx += f"最弱板块: {', '.join(bottom3[:3])}，建议回避\n"
        conn_r.close()
    except Exception:
        pass

    prompt = f"""请基于以下数据做出交易决策：

{market}

{portfolio}

{candidates}

{history}

{evolution_ctx}

{rotation_ctx}

{extra_prompt}

请输出 JSON 格式的交易决策："""

    response = _call_llm(prompt, system=SYSTEM_PROMPT)

    if response.startswith("ERROR:"):
        return {"error": response, "decisions": [], "analysis": response}

    # 解析 JSON
    try:
        # 提取 JSON 部分
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(response[start:end])
        else:
            result = {"analysis": response, "decisions": []}
    except json.JSONDecodeError:
        result = {"analysis": response, "decisions": []}

    return result


def _calc_atr_stop(code: str, entry_price: float, multiplier: float = 2.0) -> float:
    """基于 ATR（20日平均真实波幅）计算动态止损价。"""
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT high, low, close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 21",
        (code,),
    )
    rows = cur.fetchall()
    conn.close()

    if len(rows) < 5:
        return round(entry_price * 0.92, 2)

    rows = rows[::-1]
    tr_list = []
    for i in range(1, len(rows)):
        h, l, prev_c = rows[i][0], rows[i][1], rows[i - 1][2]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)

    atr = float(np.mean(tr_list[-20:])) if len(tr_list) >= 20 else float(np.mean(tr_list))
    stop = entry_price - multiplier * atr
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


def execute_ai_decisions(decisions: list[dict], mode: str = "auto") -> list[str]:
    """执行 AI 的买卖决策。mode: 'auto'=自主仓, 'manual'=推荐仓
    注意：买入/卖出价格始终使用真实市场价格，忽略 LLM 建议价。
    """
    results = []
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

        elif action == "sell":
            price = _get_real_price(code)
            if price > 0:
                msg = sell(mode, code, price, f"AI决策: {reason}")
                results.append(msg)
            else:
                results.append(f"卖出失败 {code}: 无法获取价格")

        elif action == "hold":
            results.append(f"持有 {code}: {reason}")

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


