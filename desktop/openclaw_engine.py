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

from core.ai.context_builder import build_openclaw_context_text
from desktop.data_access import get_repo, get_kv_json, set_kv_json
from desktop.scan_store import get_scan_results, get_scan_results_meta, resolve_scan_results
from desktop.task_orchestrator import log_system_event, run_task

_log = logging.getLogger("openclaw_engine")


def _apply_execution_policy(decisions: list[dict], policy: dict | None) -> dict:
    """
    根据协调者下发策略过滤可执行决策。
    policy 示例:
      {
        "allow_buy": True/False,
        "allow_sell": True/False,
        "allow_hold": True/False,
        "max_buy_count": 1
      }
    """
    policy = policy or {}
    allow_buy = bool(policy.get("allow_buy", True))
    allow_sell = bool(policy.get("allow_sell", True))
    allow_hold = bool(policy.get("allow_hold", True))
    max_buy_count = int(policy.get("max_buy_count", -1) or -1)

    filtered: list[dict] = []
    blocked: list[dict] = []
    buy_count = 0

    for item in decisions or []:
        action = str(item.get("action", "") or "").lower()
        should_keep = True
        reason = ""
        if action == "buy":
            if not allow_buy:
                should_keep = False
                reason = "策略分流: 禁止买入"
            elif max_buy_count >= 0 and buy_count >= max_buy_count:
                should_keep = False
                reason = "策略分流: 买入数量超限"
            else:
                buy_count += 1
        elif action == "sell":
            if not allow_sell:
                should_keep = False
                reason = "策略分流: 禁止卖出"
        elif action == "hold":
            if not allow_hold:
                should_keep = False
                reason = "策略分流: 禁止持有动作"

        if should_keep:
            filtered.append(item)
        else:
            blocked.append(
                {
                    "action": action,
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "price": item.get("price", 0),
                    "shares": item.get("shares", 0),
                    "reason": reason,
                }
            )

    return {"decisions": filtered, "blocked": blocked}


def _truncate_report_text(text: object, limit: int = 42) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 3)].rstrip("，。；,.; ") + "..."


def _format_report_clause(text: object, limit: int = 42) -> str:
    value = _truncate_report_text(text, limit=limit).rstrip("，。；,.; ")
    return f"{value}；" if value else "未填写原因；"


def build_openclaw_push_report(results: dict | None = None, *, report_date: date | None = None) -> dict:
    payload = results or {}
    candidates = payload.get("candidates", []) or []
    decisions = payload.get("decisions", []) or []
    sentiment = payload.get("news_sentiment", {}) or {}
    lines = [f"时间: {report_date or date.today()}", ""]

    section = 1
    if sentiment:
        lines.append(f"{section}. 📰 舆情分析")
        lines.append(
            "　　"
            + _format_report_clause(
                f"新闻 {sentiment.get('total', 0)} 条，"
                f"正面 {sentiment.get('positive', 0)} 条，"
                f"负面 {sentiment.get('negative', 0)} 条",
                limit=80,
            )
        )
        lines.append("")
        section += 1

    if candidates:
        lines.append(f"{section}. 📡 选股结果（共 {len(candidates)} 只候选）")
        for i, item in enumerate(candidates[:5], 1):
            lines.append(
                f"　　({i}) {item.get('code', '')} {item.get('name', '')}  "
                f"评分{item.get('score', '-')}  [{item.get('board', '')}]；"
            )
        if len(candidates) > 5:
            lines.append(f"　　... 及其他 {len(candidates) - 5} 只；")
        lines.append("")
        section += 1

    if decisions:
        max_decisions = 8
        labels = {"buy": "买入", "sell": "卖出", "hold": "持有"}
        lines.append(f"{section}. 🤖 AI决策（共 {len(decisions)} 条）")
        for i, item in enumerate(decisions[:max_decisions], 1):
            action = labels.get(str(item.get("action", "") or "").lower(), item.get("action", ""))
            reason = _format_report_clause(item.get("reason", ""), limit=46)
            lines.append(f"　　({i}) {action} {item.get('code', '')} {item.get('name', '')}  {reason}")
        if len(decisions) > max_decisions:
            lines.append(f"　　... 及其他 {len(decisions) - max_decisions} 条决策；")
        lines.append("")
        section += 1

    if payload.get("risk_summary"):
        lines.append(f"{section}. 🛡️ 风控摘要")
        lines.append(f"　　{_format_report_clause(payload.get('risk_summary'), limit=80)}")
        lines.append("")

    return {
        "title": "🦀 OpenClaw智能报告",
        "content": "\n".join(lines).strip(),
    }


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

    scan_rows = get_scan_results()
    scan_meta = get_scan_results_meta()
    scan_count = len(scan_rows)
    sources.append({
        "name": "选股雷达结果", "type": "策略",
        "status": "正常" if scan_count > 0 else "无数据",
        "last_update": str(scan_meta.get("written_at", "-"))[:19],
        "count": scan_count,
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
    coordinator_cls = None
    try:
        from desktop.agents import CoordinatorAgent

        coordinator_cls = CoordinatorAgent
        results["coordinator"] = CoordinatorAgent.plan_pipeline(boards)
        results["coordinator"]["routing"] = []
    except Exception:
        results["coordinator"] = {}

    def _hydrate_candidates_from_last_scan(limit: int = 30) -> int:
        if results.get("candidates"):
            return 0
        rows = resolve_scan_results()[0]
        if not isinstance(rows, list):
            rows = []
        hydrated = []
        for row in rows[: max(1, int(limit or 30))]:
            if not isinstance(row, dict):
                continue
            code = str(row.get("代码", "") or row.get("code", "") or "").strip()
            if not code:
                continue
            try:
                score = int(float(row.get("评分", row.get("score", 0)) or 0))
            except Exception:
                score = 0
            try:
                price = float(row.get("价格", row.get("price", 0)) or 0)
            except Exception:
                price = 0.0
            hydrated.append(
                {
                    "code": code,
                    "name": row.get("名称", row.get("name", code)),
                    "score": score,
                    "price": price,
                    "board": row.get("板块", row.get("board", "")),
                    "strategy": row.get("策略", row.get("strategy", "last_scan")),
                    "source": "last_scan_results",
                }
            )
        if hydrated:
            results["candidates"] = hydrated
        return len(hydrated)

    def _apply_orchestration(stage_key: str) -> dict:
        if coordinator_cls is None or not stage_key:
            return {}
        try:
            plan = coordinator_cls.inspect_stage_readiness(stage_key, results)
            if not isinstance(plan, dict):
                return {}
        except Exception as e:
            plan = {
                "stage": stage_key,
                "ready": True,
                "mode": "inspect_failed",
                "reason": f"编排检查失败，继续默认流程: {e}",
                "actions": [],
                "timestamp": datetime.now().isoformat(),
            }
        actions_done = []
        for action in plan.get("actions", []) or []:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type", "") or "")
            if action_type == "hydrate_last_scan_results":
                count = _hydrate_candidates_from_last_scan(int(action.get("limit", 30) or 30))
                item = dict(action)
                item["status"] = "done" if count else "no_data"
                item["count"] = count
                actions_done.append(item)
            elif action_type == "mark_degraded":
                results["learning_degraded"] = True
                item = dict(action)
                item["status"] = "done"
                actions_done.append(item)
            else:
                item = dict(action)
                item["status"] = "noted"
                actions_done.append(item)
        if actions_done:
            plan["actions_done"] = actions_done
        orchestration = results.get("coordinator", {}).setdefault("orchestration", [])
        if isinstance(orchestration, list):
            orchestration.append(plan)
        return plan

    def _step(idx, name, func, stage_key: str = "", preflight: bool = True):
        t0 = time.time()
        if callback:
            callback(idx, "运行中", "-", "...")
        if preflight:
            _apply_orchestration(stage_key)
        try:
            summary = run_task(name, "openclaw_pipeline", func)
            elapsed = f"{(time.time()-t0)*1000:.0f}ms"
            if callback:
                callback(idx, "完成", elapsed, summary)
            results["steps"].append({"name": name, "status": "ok", "elapsed": elapsed, "summary": summary})
            _log.info(f"pipeline step {idx}: {name} -> {summary}")
            log_system_event("openclaw", "pipeline", f"{name}完成", detail=str(summary)[:300])
        except Exception as e:
            recovery = {"retry": False, "mode": "no_recovery", "reason": ""}
            if coordinator_cls is not None:
                try:
                    recovery = coordinator_cls.recover_stage_failure(stage_key, name, str(e), results)
                except Exception:
                    recovery = {"retry": False, "mode": "no_recovery", "reason": ""}
            recoveries = results.get("coordinator", {}).setdefault("recoveries", [])
            if isinstance(recoveries, list):
                recoveries.append(
                    {
                        "stage": stage_key,
                        "name": name,
                        "mode": recovery.get("mode", "no_recovery"),
                        "reason": recovery.get("reason", ""),
                        "error": str(e)[:160],
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            if recovery.get("retry"):
                try:
                    retry_summary = run_task(f"{name}(恢复重试)", "openclaw_pipeline", func)
                    elapsed = f"{(time.time()-t0)*1000:.0f}ms"
                    summary = f"{retry_summary} | 协调者恢复: {recovery.get('reason', '')}"
                    if callback:
                        callback(idx, "完成", elapsed, summary)
                    results["steps"].append({
                        "name": name,
                        "status": "ok",
                        "elapsed": elapsed,
                        "summary": summary,
                        "recovered": True,
                        "recovery_mode": recovery.get("mode", "retry_once"),
                    })
                    log_system_event("openclaw", "pipeline", f"{name}恢复成功", detail=summary[:300])
                    return
                except Exception as retry_exc:
                    e = retry_exc
            elapsed = f"{(time.time()-t0)*1000:.0f}ms"
            if callback:
                callback(idx, "失败", elapsed, str(e)[:50])
            results["steps"].append({
                "name": name,
                "status": "error",
                "error": str(e),
                "recovery_mode": recovery.get("mode", "no_recovery"),
                "recovery_reason": recovery.get("reason", ""),
            })
            results["errors"].append(f"Step {idx} {name}: {e}")
            _log.error(f"pipeline step {idx} failed: {e}")
            log_system_event("openclaw", "pipeline", f"{name}失败", detail=str(e), level="error")

    def _route(stage_key: str) -> dict:
        if coordinator_cls is None:
            return {"run": True, "mode": "normal", "reason": "未启用协调者，默认执行"}
        try:
            decision = coordinator_cls.route_stage(stage_key, results)
            if not isinstance(decision, dict):
                decision = {"run": True, "mode": "normal", "reason": "路由返回无效，已默认执行"}
        except Exception as e:
            decision = {"run": True, "mode": "normal", "reason": f"路由异常，已默认执行: {e}"}
        routing = results.get("coordinator", {}).get("routing")
        if isinstance(routing, list):
            routing.append(
                {
                    "stage": stage_key,
                    "run": bool(decision.get("run", True)),
                    "mode": str(decision.get("mode", "normal") or "normal"),
                    "reason": str(decision.get("reason", "") or ""),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        return decision

    def _step_routed(idx, stage_key, name, func):
        _apply_orchestration(stage_key)
        decision = _route(stage_key)
        if not decision.get("run", True):
            reason = str(decision.get("reason", "协调者分流跳过") or "协调者分流跳过")
            mode = str(decision.get("mode", "skip") or "skip")
            if stage_key == "s6":
                blocked = [
                    {
                        "action": str(item.get("action", "") or "").lower(),
                        "code": item.get("code", ""),
                        "name": item.get("name", ""),
                        "price": item.get("price", 0),
                        "shares": item.get("shares", 0),
                        "reason": reason,
                    }
                    for item in (results.get("decisions", []) or [])
                ]
                results["executed_decisions"] = []
                results["execution_plan"] = {
                    "mode": mode,
                    "policy": decision.get("execution_policy", {}) if isinstance(decision, dict) else {},
                    "blocked_count": len(blocked),
                    "blocked": blocked,
                }
            if callback:
                callback(idx, "跳过", "-", reason)
            results["steps"].append(
                {
                    "name": name,
                    "status": "ok",
                    "elapsed": "0ms",
                    "summary": f"⏭ [{mode}] {reason}",
                    "skipped": True,
                    "route_mode": mode,
                    "route_reason": reason,
                }
            )
            _log.info(f"pipeline step {idx}: {name} -> skipped ({mode}) {reason}")
            log_system_event("openclaw", "pipeline", f"{name}跳过", detail=reason)
            return
        route_runtime = results.setdefault("_route_runtime", {})
        if isinstance(route_runtime, dict):
            route_runtime[stage_key] = decision
        _step(idx, name, func, stage_key=stage_key, preflight=False)

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

        from desktop.radar_scan import candidates_from_arena_snapshot, candidates_from_scan_rows
        from desktop.scan_store import resolve_scan_results

        scan_rows, _, _ = resolve_scan_results()
        candidates = candidates_from_scan_rows(scan_rows)
        source_note = "ui/daemon scan pool"

        if not candidates:
            candidates = candidates_from_arena_snapshot(per_strategy_top=3)
            source_note = "arena snapshot (19 strategies)"

        results["candidates"] = candidates[:30]
        if not candidates:
            return "0只候选(请先 UI 扫描或等待竞技场快照)"

        return (
            f"{len(candidates)}只候选({source_note}) "
            f"Top3: {', '.join(c['code'] for c in candidates[:3])}"
        )

    # ═══ S3: 多智能体协同研判 ═══
    def _s3():
        try:
            from desktop.agents import run_multi_agent_cycle
            ma_result = run_multi_agent_cycle(
                boards=boards,
                mode="auto",
                execute=False,
                persist_memory=False,
                prefilled_candidates=results.get("candidates") or None,
            )
            decisions = ma_result.get("decisions", [])
            results["decisions"] = decisions
            results["raw_decisions"] = ma_result.get("raw_decisions", [])
            results["verification"] = ma_result.get("verification", {})
            results["decision_guardrails"] = ma_result.get("decision_guardrails", {})
            results["agent_steps"] = ma_result.get("steps", [])
            results["agent_trace"] = ma_result.get("agent_trace", [])
            results["agent_trace_context"] = ma_result.get("trace", {})
            results["analysis"] = ma_result.get("analysis", "")
            analysis = ma_result.get("analysis", "")[:120]
            return f"{len(decisions)}条决策(多智能体) {analysis}"
        except Exception as e:
            # fallback 到单 LLM
            from desktop.ai_trader import run_ai_decision
            extra_prompt = build_openclaw_context_text(
                boards=boards,
                candidate_count=len(results.get("candidates", [])),
                news_sentiment=results.get("news_sentiment", {}),
                factor_coverage=len(results.get("factor_scores", {})),
            )
            result = run_ai_decision(",".join(boards), mode="auto", extra_prompt=extra_prompt)
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
        from desktop.agents import RiskAgent

        risk_report = RiskAgent.assess_openclaw(results)
        results["risk_report"] = risk_report
        results["risk_summary"] = risk_report.get("summary", "✅ 全部通过")
        return results["risk_summary"]

    # ═══ S6: 执行交易 ═══
    def _s6():
        decisions = results.get("decisions", [])
        if not decisions:
            return "无待执行指令"
        route_runtime = results.get("_route_runtime", {})
        route_payload = route_runtime.get("s6", {}) if isinstance(route_runtime, dict) else {}
        policy = route_payload.get("execution_policy", {}) if isinstance(route_payload, dict) else {}
        policy_result = _apply_execution_policy(decisions, policy if isinstance(policy, dict) else {})
        executable = policy_result.get("decisions", [])
        blocked_by_policy = policy_result.get("blocked", [])
        results["execution_plan"] = {
            "mode": route_payload.get("mode", "normal") if isinstance(route_payload, dict) else "normal",
            "policy": policy if isinstance(policy, dict) else {},
            "blocked_count": len(blocked_by_policy),
            "blocked": blocked_by_policy,
        }
        try:
            from desktop.agents import ApprovalAgent

            approval = ApprovalAgent.review_decisions(executable, mode="auto")
            results["approval_report"] = approval
            executable = approval.get("approved_decisions", executable)
            if approval.get("rejected_decisions"):
                results["execution_plan"]["approval_rejected"] = approval.get("rejected_decisions", [])
                results["execution_plan"]["approval_rejected_count"] = len(approval.get("rejected_decisions", []) or [])
        except Exception as e:
            results["approval_report"] = {"summary": f"审批跳过: {e}", "approved_decisions": executable}
        results["executed_decisions"] = executable
        if not executable:
            return f"策略分流后无待执行指令(拦截{len(blocked_by_policy)}条)"
        from desktop.ai_trader import execute_ai_decisions, execute_sell_signals_across_modes
        exec_results = execute_ai_decisions(executable, mode="auto")
        cross_mode_sells = execute_sell_signals_across_modes(executable, modes=("custom", "quantum"))
        if cross_mode_sells:
            exec_results.extend(cross_mode_sells)
            results["cross_mode_sell_results"] = cross_mode_sells
        approval_report = results.get("approval_report", {}) or {}
        rejected_count = len(approval_report.get("rejected_decisions", []) or [])
        if blocked_by_policy or rejected_count:
            return (
                f"{len(exec_results)} 条执行完成，"
                f"策略分流拦截 {len(blocked_by_policy)} 条，审批拒绝 {rejected_count} 条"
            )
        return f"{len(exec_results)} 条执行完成"

    # ═══ S7: 推送通知 ═══
    def _s7():
        candidates = results.get("candidates", [])
        decisions = results.get("decisions", [])
        sentiment = results.get("news_sentiment", {})
        report = build_openclaw_push_report(
            {
                "candidates": candidates,
                "decisions": decisions,
                "news_sentiment": sentiment,
                "risk_summary": results.get("risk_summary", ""),
            }
        )
        try:
            from signal_push import push_signal
            push_signal(report["title"], report["content"])
            return "推送成功"
        except Exception:
            return "推送跳过"

    # ═══ S8: 归因记录 ═══
    def _s8():
        try:
            from desktop.trend_verify import record_signals
            candidates = results.get("candidates", [])
            routed_recorded = 0
            if candidates:
                signals = [{"代码": c["code"], "名称": c["name"],
                           "评分": str(c["score"]), "价格": str(c.get("price", 0)),
                           "板块": c.get("board", "")}
                           for c in candidates[:10]]
                record_signals(signals)
            try:
                from desktop.trend_verify import record_routed_blocked_decisions

                routed_recorded = record_routed_blocked_decisions(
                    (results.get("execution_plan", {}) or {}).get("blocked", []) or [],
                    raw_decisions=results.get("raw_decisions", []) or [],
                )
            except Exception:
                routed_recorded = 0
            from desktop.agents import calibrate_decisions
            calibrate_decisions(5)
            suffix = f"，分流复盘{routed_recorded}个" if routed_recorded else ""
            return f"记录{min(len(candidates), 10)}个信号{suffix}，校准完成"
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

    _step(0, "感知采集(行情+新闻+NLP)", _s1, stage_key="s1")
    _step(1, "因子研究(多因子+学习权重)", _s2, stage_key="s2")
    _step(2, "多智能体协同研判", _s3, stage_key="s3")
    _step_routed(3, "s4", "仓位优化(组合优化器)", _s4)
    _step(4, "全面风控(VaR+回撤+舆情)", _s5, stage_key="s5")
    _step_routed(5, "s6", "执行交易", _s6)
    try:
        from core.ai.decision_memory import save_decision_memory

        save_decision_memory(
            {
                "timestamp": datetime.now().isoformat(),
                "mode": "auto",
                "steps": results.get("agent_steps", []),
                "decisions": results.get("decisions", []),
                "executed_decisions": results.get("executed_decisions", results.get("decisions", [])),
                "raw_decisions": results.get("raw_decisions", []),
                "analysis": results.get("analysis", ""),
                "verification": results.get("verification", {}),
                "decision_guardrails": results.get("decision_guardrails", {}),
                "execution_plan": results.get("execution_plan", {}),
            }
        )
    except Exception as e:
        results["errors"].append(f"决策记忆保存失败: {e}")
    _step_routed(6, "s7", "智能推送", _s7)
    _step_routed(7, "s8", "归因记录", _s8)
    _step_routed(8, "s9", "自主学习进化", _s9)

    try:
        from desktop.agents import CoordinatorAgent

        results["coordinator"]["execution"] = CoordinatorAgent.summarize_pipeline(results)
    except Exception:
        pass

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
