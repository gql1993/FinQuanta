"""
OpenClaw 全流程智能中枢引擎
9步管线：感知采集 → 因子研究 → 多智能体研判 → 仓位优化 → 风控检查 → 执行 → 推送 → 归因 → 自主学习

接入模块：
  - realtime_data     实时行情
  - event_strategy    事件/新闻
  - fund_strategy     基金持仓
  - news_nlp          情绪分析
  - factor_research   因子研究
  - agents            多智能体
  - portfolio_optimizer 组合优化
  - ai_portfolio      风控/执行
  - trend_verify      走势验证
  - openclaw_learner  自主学习
"""
import json
import time
import logging
import numpy as np
from datetime import datetime, date

from desktop.data_access import get_repo, get_kv_json, set_kv_json
from desktop.task_orchestrator import log_system_event, run_task

_log = logging.getLogger("openclaw_engine")


def get_data_sources_status() -> list[dict]:
    """返回各数据源的状态摘要。"""
    repo = get_repo()
    sources = []

    r = repo.fetchone("SELECT COUNT(DISTINCT code), MAX(date) FROM daily_kline", ())
    sources.append({
        "name": "日K线数据(腾讯)", "type": "行情",
        "status": "正常" if r[0] > 100 else "数据不足",
        "last_update": r[1] or "-", "count": r[0],
    })

    try:
        r2 = repo.fetchone("SELECT COUNT(*), MAX(updated_at) FROM realtime_quotes", ())
        sources.append({
            "name": "实时行情(新浪)", "type": "行情",
            "status": "正常" if r2[0] > 0 else "无数据",
            "last_update": r2[1][:19] if r2[1] else "-", "count": r2[0],
        })
    except Exception:
        sources.append({"name": "实时行情(新浪)", "type": "行情",
                        "status": "未初始化", "last_update": "-", "count": 0})

    r3 = repo.fetchone("SELECT COUNT(DISTINCT board), COUNT(*) FROM board_stocks", ())
    try:
        r3b = repo.fetchone(
            "SELECT MAX(date) FROM daily_kline WHERE code IN (SELECT code FROM board_stocks LIMIT 100)",
            (),
        )
        board_update = r3b[0] if r3b and r3b[0] else "-"
    except Exception:
        board_update = "-"
    sources.append({
        "name": "板块成分股", "type": "基础",
        "status": "正常" if r3[0] > 0 else "无数据",
        "last_update": board_update, "count": r3[1],
    })

    r4 = repo.fetchone("SELECT value, updated_at FROM kv_store WHERE key='last_scan_results'", ())
    scan_count = 0
    if r4 and r4[0] is not None:
        raw = r4[0]
        try:
            if isinstance(raw, str):
                scan_count = len(json.loads(raw))
            elif isinstance(raw, list):
                scan_count = len(raw)
            else:
                scan_count = len(raw) if hasattr(raw, "__len__") and not isinstance(raw, (str, bytes)) else 0
        except Exception:
            scan_count = 0
    sources.append({
        "name": "选股雷达结果", "type": "策略",
        "status": "正常" if scan_count > 0 else "无数据",
        "last_update": str(r4[1])[:19] if r4 and r4[1] is not None else "-", "count": scan_count,
    })

    try:
        r5 = repo.fetchone("SELECT COUNT(*) FROM fund_holdings", ())
        r5b = repo.fetchone("SELECT MAX(report_date) FROM fund_holdings", ())
        sources.append({
            "name": "基金持仓数据", "type": "基本面",
            "status": "正常" if r5[0] > 0 else "无数据",
            "last_update": r5b[0] if r5b and r5b[0] else "-", "count": r5[0],
        })
    except Exception:
        sources.append({"name": "基金持仓数据", "type": "基本面",
                        "status": "暂无", "last_update": "-", "count": 0})

    try:
        r6 = repo.fetchone("SELECT COUNT(*), MAX(timestamp) FROM ai_decision_memory", ())
        sources.append({
            "name": "AI决策记忆", "type": "学习",
            "status": "正常" if r6[0] > 0 else "暂无记录",
            "last_update": str(r6[1])[:19] if r6[1] else "-", "count": r6[0],
        })
    except Exception:
        sources.append({"name": "AI决策记忆", "type": "学习",
                        "status": "暂无记录", "last_update": "-", "count": 0})

    # 新闻NLP
    try:
        r7 = repo.fetchone("SELECT COUNT(*) FROM events", ())
        sources.append({
            "name": "新闻/事件库", "type": "舆情",
            "status": "正常" if r7[0] > 0 else "暂无",
            "last_update": "-", "count": r7[0],
        })
    except Exception:
        sources.append({"name": "新闻/事件库", "type": "舆情",
                        "status": "暂无", "last_update": "-", "count": 0})

    return sources


def run_full_pipeline(boards: list[str] = None, callback=None) -> dict:
    """
    执行完整 9 步智能管线（全模块接入版）。
    """
    boards = boards or ["人工智能", "芯片", "量子科技"]
    results = {"steps": [], "candidates": [], "decisions": [], "errors": [],
               "news_sentiment": {}, "factor_scores": {}, "portfolio_weights": {}}

    def _step(idx, name, func):
        t0 = time.time()
        if callback:
            callback(idx, "运行中", "-", "...")
        try:
            summary = run_task(name, "openclaw_pipeline", func)
            elapsed = f"{(time.time()-t0)*1000:.0f}ms"
            if callback:
                callback(idx, "完成", elapsed, summary)
            results["steps"].append({"name": name, "status": "ok", "elapsed": elapsed, "summary": summary})
            _log.info(f"pipeline step {idx}: {name} -> {summary}")
            log_system_event("openclaw", "pipeline", f"{name}完成", detail=str(summary)[:300])
        except Exception as e:
            elapsed = f"{(time.time()-t0)*1000:.0f}ms"
            if callback:
                callback(idx, "失败", elapsed, str(e)[:50])
            results["steps"].append({"name": name, "status": "error", "error": str(e)})
            results["errors"].append(f"Step {idx} {name}: {e}")
            _log.error(f"pipeline step {idx} failed: {e}")
            log_system_event("openclaw", "pipeline", f"{name}失败", detail=str(e), level="error")

    # ═══ S1: 感知层 — 多源数据采集 ═══
    def _s1():
        parts = []
        # 1a. 实时行情
        try:
            from desktop.realtime_data import get_realtime_quotes
            repo = get_repo()
            codes = [r[0] for r in repo.fetchall("SELECT DISTINCT code FROM board_stocks LIMIT 200", ())]
            if codes:
                quotes = get_realtime_quotes(codes[:100], force=True)
                parts.append(f"行情{len(quotes)}只")
        except Exception as e:
            parts.append(f"行情失败:{e}")

        # 1b. 新闻资讯 + NLP情绪分析
        try:
            from desktop.event_strategy import fetch_news_eastmoney
            news = fetch_news_eastmoney(limit=20)
            if news:
                # NLP情绪分析
                try:
                    from desktop.news_nlp import batch_analyze
                    sentiments = batch_analyze([n.get("title", "") for n in news[:10]])
                    pos = sum(1 for s in sentiments if s.get("sentiment") == "positive")
                    neg = sum(1 for s in sentiments if s.get("sentiment") == "negative")
                    results["news_sentiment"] = {
                        "total": len(sentiments), "positive": pos, "negative": neg,
                        "ratio": round(pos / max(len(sentiments), 1), 2),
                    }
                    parts.append(f"新闻{len(news)}条(正面{pos}/负面{neg})")
                except Exception:
                    parts.append(f"新闻{len(news)}条(NLP跳过)")
            else:
                parts.append("新闻0条")
        except Exception as e:
            parts.append(f"新闻跳过:{str(e)[:20]}")

        # 1c. 基金持仓检查
        try:
            from desktop.fund_strategy import get_star_managers
            managers = get_star_managers()
            if managers:
                parts.append(f"基金经理{len(managers)}位")
        except Exception:
            pass

        return " | ".join(parts)

    # ═══ S2: 因子研究 — 多因子筛选 + 学习权重 ═══
    def _s2():
        repo = get_repo()
        codes = [r[0] for r in repo.fetchall(
            "SELECT code, COUNT(*) FROM daily_kline GROUP BY code "
            "HAVING COUNT(*) >= 50 ORDER BY COUNT(*) DESC LIMIT 500",
            (),
        )]

        names = {}
        try:
            names = {r[0]: r[1] for r in repo.fetchall("SELECT code, name FROM stock_list", ())}
        except Exception:
            pass

        board_map = {}
        try:
            for r in repo.fetchall("SELECT code, board FROM board_stocks", ()):
                if r[0] not in board_map:
                    board_map[r[0]] = r[1]
        except Exception:
            pass

        # 加载学习权重
        strategy_weights = {}
        try:
            from desktop.openclaw_learner import get_strategy_weights
            strategy_weights = get_strategy_weights()
        except Exception:
            pass
        sepa_w = strategy_weights.get("SEPA", {}).get("weight", 1.0)

        # 因子研究模块
        factor_scores = {}
        try:
            from desktop.factor_research import compute_factor_bundle_from_arrays
            for code in codes[:200]:
                try:
                    rows = repo.fetchall(
                        "SELECT close, high, low, volume FROM daily_kline "
                        "WHERE code=? ORDER BY date DESC LIMIT 260",
                        (code,),
                    )
                    if len(rows) < 50:
                        continue
                    rows = rows[::-1]
                    closes = np.array([r[0] for r in rows])
                    highs = np.array([r[1] for r in rows])
                    lows = np.array([r[2] for r in rows])
                    vols = np.array([r[3] for r in rows])
                    factor_scores[code] = compute_factor_bundle_from_arrays(closes, highs, lows, vols)
                except Exception:
                    pass
            results["factor_scores"] = factor_scores
        except Exception:
            pass

        from desktop.strategy_engine import build_context, score_candidate
        from desktop.strategy_rotator import get_current_best_strategy
        current_strategy = get_current_best_strategy()

        candidates = []
        for code in codes:
            rows = repo.fetchall(
                "SELECT close, high, low, volume FROM daily_kline "
                "WHERE code=? ORDER BY date DESC LIMIT 260", (code,)
            )
            if len(rows) < 50:
                continue
            rows = rows[::-1]
            closes = np.array([r[0] for r in rows])
            highs = np.array([r[1] for r in rows])
            n = len(closes)
            p = float(closes[-1])
            if p <= 0:
                continue

            ctx = build_context(code, closes, highs, lows, vols)
            scored = score_candidate(current_strategy, ctx)
            score = scored["score"]

            # 因子加分
            fs = factor_scores.get(code, {})
            if fs.get("momentum_20d", 0) > 5:
                score += 5
            if fs.get("volatility_20d", 999) < 0.03:
                score += 5

            # 学习权重加成
            score = int(score * sepa_w)

            if score >= 40:
                candidates.append({
                    "code": code, "name": names.get(code, code),
                    "score": score, "price": round(p, 2),
                    "board": board_map.get(code, ""),
                    "momentum_1m": round((p / closes[-22] - 1) * 100, 2) if n >= 22 else 0,
                    "volatility": round(float(np.std(closes[-20:]) / np.mean(closes[-20:]) * 100), 2) if n >= 20 else 0,
                    "strategy": scored["strategy"],
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        results["candidates"] = candidates[:30]

        set_kv_json(
            "last_scan_results",
            [
                {"代码": c["code"], "名称": c["name"], "评分": str(c["score"]),
                 "价格": str(c["price"]), "板块": c.get("board", ""),
                 "建议买入": "强烈买入" if c["score"] >= 70 else "建议买入",
                }
                for c in candidates[:50]
            ],
        )
        n_factor = len(factor_scores)
        return (f"{len(candidates)}只候选(因子{n_factor}只) "
                f"Top3: {', '.join(c['code'] for c in candidates[:3])}")

    # ═══ S3: 多智能体协同研判 ═══
    def _s3():
        try:
            from desktop.agents import run_multi_agent_cycle
            ma_result = run_multi_agent_cycle(boards=boards, mode="auto", execute=False)
            decisions = ma_result.get("decisions", [])
            results["decisions"] = decisions
            results["agent_steps"] = ma_result.get("steps", [])
            analysis = ma_result.get("analysis", "")[:120]
            return f"{len(decisions)}条决策(多智能体) {analysis}"
        except Exception as e:
            # fallback 到单 LLM
            from desktop.ai_trader import run_ai_decision
            result = run_ai_decision(",".join(boards), mode="auto")
            decisions = result.get("decisions", [])
            results["decisions"] = decisions
            return f"{len(decisions)}条决策(单LLM) {result.get('analysis','')[:60]}"

    # ═══ S4: 仓位优化 ═══
    def _s4():
        decisions = results.get("decisions", [])
        buys = [d for d in decisions if d.get("action") == "buy"]
        sells = [d for d in decisions if d.get("action") == "sell"]
        holds = [d for d in decisions if d.get("action") == "hold"]

        # 用 portfolio_optimizer 优化买入权重
        opt_msg = ""
        if buys:
            try:
                from desktop.portfolio_optimizer import optimize_portfolio
                buy_codes = [d.get("code", "") for d in buys if d.get("code")]
                if len(buy_codes) >= 2:
                    opt_result = optimize_portfolio(buy_codes)
                    if opt_result:
                        results["portfolio_weights"] = opt_result
                        opt_msg = f" 优化权重:{opt_result.get('method','')}"
            except Exception as e:
                opt_msg = f" 优化跳过:{str(e)[:20]}"

        return f"买入{len(buys)} 卖出{len(sells)} 持有{len(holds)}{opt_msg}"

    # ═══ S5: 全面风控检查 ═══
    def _s5():
        from desktop.ai_portfolio import get_state
        warnings = []

        for mode, label in [("auto", "半自主"), ("full_auto", "完全自主")]:
            state = get_state(mode)
            n_pos = len(state["positions"])
            cash_ratio = state["cash"] / max(state["initial_capital"], 1) * 100

            if n_pos >= 10:
                warnings.append(f"{label}持仓{n_pos}≥10")
            if cash_ratio < 10:
                warnings.append(f"{label}现金{cash_ratio:.0f}%<10%")

            # VaR 检查（从缓存读取）
            try:
                risk = get_kv_json("portfolio_risk")
                if isinstance(risk, dict):
                    var95 = abs(risk.get("var95", 0))
                    if var95 > 100000:
                        warnings.append(f"VaR95=¥{var95:,.0f}过高")
                    dd = abs(risk.get("drawdown", 0))
                    if dd > 0.1:
                        warnings.append(f"回撤{dd:.1%}超10%")
            except Exception:
                pass

        # 新闻情绪检查
        sentiment = results.get("news_sentiment", {})
        if sentiment.get("ratio", 0.5) < 0.3:
            warnings.append(f"舆情偏空(正面率{sentiment['ratio']:.0%})")

        if warnings:
            return f"⚠ {'; '.join(warnings)}"
        return "✅ 全部通过"

    # ═══ S6: 执行交易 ═══
    def _s6():
        decisions = results.get("decisions", [])
        if not decisions:
            return "无待执行指令"
        from desktop.ai_trader import execute_ai_decisions
        exec_results = execute_ai_decisions(decisions, mode="auto")
        return f"{len(exec_results)} 条执行完成"

    # ═══ S7: 推送通知 ═══
    def _s7():
        candidates = results.get("candidates", [])
        decisions = results.get("decisions", [])
        sentiment = results.get("news_sentiment", {})

        lines = [f"🦀 OpenClaw 智能报告", f"　　时间: {date.today()}", ""]

        section = 1
        if sentiment:
            lines.append(f"{section}. 📰 舆情分析")
            lines.append(f"　　新闻 {sentiment.get('total',0)} 条，"
                         f"正面 {sentiment.get('positive',0)} 条，"
                         f"负面 {sentiment.get('negative',0)} 条")
            lines.append("")
            section += 1

        if candidates:
            lines.append(f"{section}. 📡 选股结果（共 {len(candidates)} 只候选）")
            for i, c in enumerate(candidates[:5], 1):
                lines.append(f"　　({i}) {c['code']} {c['name']}  "
                             f"评分{c['score']}  [{c.get('board','')}]")
            if len(candidates) > 5:
                lines.append(f"　　... 及其他 {len(candidates)-5} 只")
            lines.append("")
            section += 1

        if decisions:
            lines.append(f"{section}. 🤖 AI决策（共 {len(decisions)} 条）")
            labels = {"buy": "买入", "sell": "卖出", "hold": "持有"}
            for i, d in enumerate(decisions[:5], 1):
                action = labels.get(d.get("action", ""), d.get("action", ""))
                lines.append(f"　　({i}) {action} {d.get('code','')} {d.get('name','')}"
                             f"  {d.get('reason','')[:25]}")
            lines.append("")
            section += 1

        msg = "\n".join(lines)
        try:
            from signal_push import push_signal
            push_signal("🦀 OpenClaw智能报告", msg)
            return "推送成功"
        except Exception:
            return "推送跳过"

    # ═══ S8: 归因记录 ═══
    def _s8():
        try:
            from desktop.trend_verify import record_signals
            candidates = results.get("candidates", [])
            if candidates:
                signals = [{"代码": c["code"], "名称": c["name"],
                           "评分": str(c["score"]), "价格": str(c.get("price", 0)),
                           "板块": c.get("board", "")}
                           for c in candidates[:10]]
                record_signals(signals)
            from desktop.agents import calibrate_decisions
            calibrate_decisions(5)
            return f"记录{min(len(candidates), 10)}个信号，校准完成"
        except Exception as e:
            return f"部分完成: {e}"

    # ═══ S9: 自主学习进化 ═══
    def _s9():
        try:
            from desktop.openclaw_learner import evaluate_and_learn
            learn = evaluate_and_learn()
            n = len(learn.get("learnings", []))
            return f"{n}条学习发现，策略权重已更新"
        except Exception as e:
            return f"学习跳过: {e}"

    _step(0, "感知采集(行情+新闻+NLP)", _s1)
    _step(1, "因子研究(多因子+学习权重)", _s2)
    _step(2, "多智能体协同研判", _s3)
    _step(3, "仓位优化(组合优化器)", _s4)
    _step(4, "全面风控(VaR+回撤+舆情)", _s5)
    _step(5, "执行交易", _s6)
    _step(6, "智能推送", _s7)
    _step(7, "归因记录", _s8)
    _step(8, "自主学习进化", _s9)

    return results


def get_performance_summary() -> dict:
    """获取 OpenClaw 管线的绩效摘要。"""
    try:
        from desktop.ai_portfolio import get_comparison
        comp = get_comparison()
        auto = comp.get("auto", {})
        full = comp.get("full_auto", {})

        accuracy = "-"
        try:
            from desktop.trend_verify import get_accuracy_stats
            stats = get_accuracy_stats()
            if stats.get("total", 0) > 0:
                accuracy = f"{stats['accuracy']:.1f}%"
        except Exception:
            pass

        best_mode = max(comp, key=lambda m: comp[m].get("return_pct", -999))
        best_ret = comp[best_mode].get("return_pct", 0)

        return {
            "total_return": f"{best_ret:+.2f}%",
            "win_rate": f"{auto.get('win_rate', 0):.1f}%",
            "sharpe": "-",
            "max_dd": "-",
            "profit_factor": "-",
            "accuracy": accuracy,
        }
    except Exception:
        return {}
