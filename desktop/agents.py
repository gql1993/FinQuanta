"""
多智能体协同决策系统
三个智能体各司其职，协同完成交易决策：

1. 情报智能体 (Intelligence Agent) — 负责数据采集和整理
2. 分析智能体 (Analysis Agent) — 负责策略分析和评分
3. 决策智能体 (Decision Agent) — 综合前两者的输出做最终交易决策

工作流: 情报 → 分析 → 决策 → 执行
"""
import os
import json
import numpy as np
import logging
from datetime import datetime, date

from core.ai.decision_memory import (
    calibrate_decisions as calibrate_decisions_core,
    ensure_decision_memory_table,
    get_decision_accuracy as get_decision_accuracy_core,
    save_decision_memory as save_decision_memory_core,
)
from desktop.data_access import RepoCompatConnection

_log = logging.getLogger("agents")


class IntelligenceAgent:
    """
    情报智能体：采集市场数据、新闻事件、基金动向，输出结构化情报摘要。
    不做判断，只做事实陈述。
    """
    NAME = "📡 情报智能体"

    SYSTEM_PROMPT = (
        "你是一个专业的金融情报分析员。你的职责是：\n"
        "1. 整理市场数据，客观陈述事实\n"
        "2. 提取关键信号（涨跌异动、资金流向、板块轮动）\n"
        "3. 汇总新闻事件和基金动向\n"
        "4. 不做主观判断，不给买卖建议\n"
        "输出格式：分为【市场概况】【板块动态】【资金信号】【事件要闻】【基金动向】五个模块。"
    )

    @staticmethod
    def gather(boards: list[str] = None) -> dict:
        """采集全方位情报数据。"""
        if not boards:
            return {"agent": "intelligence", "error": "未指定板块", "market": {}, "boards": [], "events": [], "fund_top": []}
        report = {"agent": "intelligence", "timestamp": datetime.now().isoformat()}

        conn = RepoCompatConnection()
        conn.execute("PRAGMA journal_mode=WAL")

        # 市场概况：取有数据的前50只股票的涨跌统计
        try:
            cur = conn.execute("""
                SELECT d1.code,
                    (SELECT close FROM daily_kline d2 WHERE d2.code=d1.code ORDER BY date DESC LIMIT 1) as last_c,
                    (SELECT close FROM daily_kline d3 WHERE d3.code=d1.code ORDER BY date DESC LIMIT 1 OFFSET 1) as prev_c
                FROM (SELECT DISTINCT code FROM daily_kline) d1 LIMIT 200
            """)
            stocks = []
            up, down, flat = 0, 0, 0
            for r in cur.fetchall():
                if r[1] and r[2] and r[2] > 0:
                    pct = (r[1] - r[2]) / r[2] * 100
                    stocks.append({"code": r[0], "price": r[1], "pct": round(pct, 2)})
                    if pct > 0.5:
                        up += 1
                    elif pct < -0.5:
                        down += 1
                    else:
                        flat += 1
            report["market"] = {
                "total": len(stocks), "up": up, "down": down, "flat": flat,
                "top_gainers": sorted(stocks, key=lambda x: x["pct"], reverse=True)[:5],
                "top_losers": sorted(stocks, key=lambda x: x["pct"])[:5],
            }
        except Exception:
            report["market"] = {"error": "市场数据读取失败"}

        # 板块动态
        try:
            board_stats = []
            for board in boards:
                cur_b = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
                codes = [r[0] for r in cur_b.fetchall()]
                pcts = []
                for code in codes[:30]:
                    cur2 = conn.execute(
                        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 2", (code,)
                    )
                    rows = cur2.fetchall()
                    if len(rows) == 2 and rows[1][0] > 0:
                        pcts.append((rows[0][0] / rows[1][0] - 1) * 100)
                avg = float(np.mean(pcts)) if pcts else 0
                board_stats.append({"board": board, "stocks": len(codes), "avg_pct": round(avg, 2)})
            report["boards"] = board_stats
        except Exception:
            report["boards"] = []

        # 事件要闻
        try:
            cur_e = conn.execute(
                "SELECT event_text, matched_boards, event_date FROM events ORDER BY id DESC LIMIT 5"
            )
            report["events"] = [
                {"text": r[0], "boards": r[1], "date": r[2]} for r in cur_e.fetchall()
            ]
        except Exception:
            report["events"] = []

        # 基金动向
        try:
            cur_f = conn.execute(
                "SELECT code, name, holding_funds, change_type FROM fund_holdings "
                "ORDER BY holding_funds DESC LIMIT 10"
            )
            report["fund_top"] = [
                {"code": r[0], "name": r[1], "funds": r[2], "change": r[3]}
                for r in cur_f.fetchall()
            ]
        except Exception:
            report["fund_top"] = []

        conn.close()
        return report

    @staticmethod
    def to_prompt(report: dict) -> str:
        """将情报数据转为自然语言摘要。"""
        lines = ["===== 情报智能体报告 ====="]

        m = report.get("market", {})
        if "error" not in m:
            lines.append(f"\n【市场概况】{m.get('total', 0)}只股票: 上涨{m.get('up', 0)} 下跌{m.get('down', 0)} 持平{m.get('flat', 0)}")
            for s in m.get("top_gainers", [])[:3]:
                lines.append(f"  涨幅前列: {s['code']} {s['pct']:+.2f}%")
            for s in m.get("top_losers", [])[:3]:
                lines.append(f"  跌幅前列: {s['code']} {s['pct']:+.2f}%")

        for b in report.get("boards", []):
            lines.append(f"\n【板块】{b['board']}: {b['stocks']}只, 均涨跌 {b['avg_pct']:+.2f}%")

        events = report.get("events", [])
        if events:
            lines.append("\n【事件要闻】")
            for e in events[:3]:
                lines.append(f"  {e.get('date', '')} {e.get('text', '')}")

        fund = report.get("fund_top", [])
        if fund:
            lines.append("\n【基金动向】")
            for f in fund[:5]:
                lines.append(f"  {f['code']} {f['name']}: {f['funds']}只基金, {f.get('change', '-')}")

        return "\n".join(lines)


class AnalysisAgent:
    """
    分析智能体：基于情报数据做多维度策略分析，输出评分和信号。
    只做分析判断，不做执行决策。
    """
    NAME = "🔬 分析智能体"

    SYSTEM_PROMPT = (
        "你是一个专业的量化策略分析师。你的职责是：\n"
        "1. 基于情报数据，分析市场趋势和板块轮动\n"
        "2. 对候选股票做多策略评分（趋势/动量/价值/情绪/事件/基金持仓）\n"
        "3. 识别潜在的风险和机会\n"
        "4. 输出结构化的分析报告，不做最终买卖决策\n"
        "输出格式：分为【趋势判断】【板块评级】【个股评分】【风险提示】四个模块。\n"
        "个股评分请用表格，包含代码、名称、趋势分、动量分、综合评分、信号。"
    )

    @staticmethod
    def analyze(intel_report: dict, boards: list[str] = None) -> dict:
        """基于情报做策略分析。"""
        if not boards:
            return {"agent": "analysis", "candidates": [], "market_regime": "未指定板块"}

        conn = RepoCompatConnection()
        conn.execute("PRAGMA journal_mode=WAL")

        candidates = []
        for board in boards[:5]:
            cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
            codes = [r[0] for r in cur.fetchall()]

            names = {}
            try:
                cur_n = conn.execute("SELECT code, name FROM stock_list")
                names = {r[0]: r[1] for r in cur_n.fetchall()}
            except Exception:
                pass

            for code in codes[:20]:
                cur2 = conn.execute(
                    "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
                    (code,),
                )
                rows = cur2.fetchall()
                if len(rows) < 20:
                    continue
                rows = rows[::-1]
                closes = np.array([r[0] for r in rows])
                vols = np.array([r[3] for r in rows])
                n = len(closes)
                price = float(closes[-1])
                if price <= 0:
                    continue

                # 趋势分
                ma20 = float(np.mean(closes[-20:]))
                ma50 = float(np.mean(closes[-50:])) if n >= 50 else ma20
                trend_score = 0
                if price > ma20 > ma50:
                    trend_score = 80
                elif price > ma20:
                    trend_score = 60
                elif price < ma20 < ma50:
                    trend_score = 20
                else:
                    trend_score = 40

                # 动量分
                mom5 = (closes[-1] / closes[-6] - 1) * 100 if n >= 6 else 0
                mom20 = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else 0
                momentum_score = min(100, max(0, 50 + mom5 * 3 + mom20))

                # 量能分
                vol_avg = float(np.mean(vols[-20:])) if n >= 20 and np.mean(vols[-20:]) > 0 else 1
                vol_ratio = float(vols[-1]) / vol_avg
                volume_score = min(100, int(vol_ratio * 40))

                # 综合
                total = int(trend_score * 0.4 + momentum_score * 0.3 + volume_score * 0.3)

                signals = []
                if trend_score >= 70:
                    signals.append("多头趋势")
                if mom5 > 3:
                    signals.append(f"5日强势{mom5:+.1f}%")
                if vol_ratio > 1.5:
                    signals.append("放量")

                # 基金持仓加分
                try:
                    cur_f = conn.execute(
                        "SELECT holding_funds, change_type FROM fund_holdings WHERE code=? LIMIT 1", (code,)
                    )
                    fr = cur_f.fetchone()
                    if fr and fr[0] and fr[0] >= 100:
                        total += 5
                        signals.append(f"基金{fr[0]}只")
                    if fr and fr[1] and "增持" in str(fr[1]):
                        total += 5
                        signals.append("基金增持")
                except Exception:
                    pass

                candidates.append({
                    "code": code, "name": names.get(code, ""),
                    "board": board, "price": round(price, 2),
                    "trend": trend_score, "momentum": round(momentum_score),
                    "volume": volume_score, "total": min(100, total),
                    "signals": signals,
                })

        conn.close()
        candidates.sort(key=lambda x: x["total"], reverse=True)

        return {
            "agent": "analysis",
            "timestamp": datetime.now().isoformat(),
            "candidates": candidates[:30],
            "market_regime": _detect_regime(intel_report),
        }

    @staticmethod
    def to_prompt(analysis: dict) -> str:
        """将分析结果转为自然语言。"""
        lines = ["===== 分析智能体报告 ====="]

        regime = analysis.get("market_regime", "中性")
        lines.append(f"\n【市场环境判断】{regime}")

        candidates = analysis.get("candidates", [])
        if candidates:
            lines.append("\n【个股评分 Top15】")
            lines.append("| 代码 | 名称 | 板块 | 趋势 | 动量 | 综合 | 信号 |")
            lines.append("|------|------|------|------|------|------|------|")
            for c in candidates[:15]:
                sig = ", ".join(c["signals"][:3]) if c["signals"] else "-"
                lines.append(
                    f"| {c['code']} | {c['name']} | {c['board']} | "
                    f"{c['trend']} | {c['momentum']} | {c['total']} | {sig} |"
                )

        return "\n".join(lines)


class DecisionAgent:
    """
    决策智能体：综合情报和分析结果，做最终买卖决策。
    """
    NAME = "🎯 决策智能体"

    SYSTEM_PROMPT = (
        "你是最终决策者。你的职责是：\n"
        "1. 综合情报智能体的市场数据和分析智能体的评分\n"
        "2. 结合当前持仓情况，做出最终的买卖决策\n"
        "3. 控制风险：单只股票不超过总资金10%，总持仓不超过10只\n"
        "4. 明确给出操作指令和理由\n\n"
        "输出严格的 JSON 格式：\n"
        '{"analysis": "一句话总结", "decisions": [\n'
        '  {"action": "buy", "code": "300502", "name": "新易盛", "price": 380, "shares": 500, "reason": "趋势强+放量突破"},\n'
        '  {"action": "sell", "code": "002049", "name": "紫光国微", "reason": "跌破止损线"},\n'
        '  {"action": "hold", "code": "688981", "name": "中芯国际", "reason": "趋势良好继续持有"}\n'
        "]}"
    )

    @staticmethod
    def decide(intel_prompt: str, analysis_prompt: str, portfolio_context: str) -> str:
        """调用 LLM 做最终决策。"""
        from desktop.ai_trader import _call_llm

        prompt = (
            f"以下是情报智能体和分析智能体的报告，请做出最终交易决策。\n\n"
            f"{intel_prompt}\n\n"
            f"{analysis_prompt}\n\n"
            f"{portfolio_context}\n\n"
            f"请输出 JSON 格式的交易决策："
        )
        return _call_llm(prompt, system=DecisionAgent.SYSTEM_PROMPT)


def _detect_regime(intel: dict) -> str:
    """基于情报判断市场环境。"""
    m = intel.get("market", {})
    up = m.get("up", 0)
    down = m.get("down", 0)
    total = m.get("total", 1)
    if total == 0:
        return "数据不足"
    ratio = up / max(total, 1)
    if ratio > 0.65:
        return "🟢 强势（多数上涨，可积极操作）"
    elif ratio > 0.45:
        return "🟡 震荡（涨跌参半，精选个股）"
    else:
        return "🔴 弱势（多数下跌，控制仓位）"


def _init_memory_table():
    ensure_decision_memory_table()


_init_memory_table()


def _save_decision_memory(result: dict):
    """保存完整决策上下文到数据库，供后续校准。"""
    save_decision_memory_core(result)


def calibrate_decisions(days_after: int = 5) -> list[dict]:
    """
    校准历史决策：检查 N 天前的买入决策，实际收益是多少。
    更新 actual_results 和 calibrated 字段。
    """
    return calibrate_decisions_core(days_after=days_after)


def get_decision_accuracy(limit: int = 50) -> dict:
    """统计 AI 决策的历史准确率。"""
    return get_decision_accuracy_core(limit=limit)


def run_multi_agent_cycle(boards: list[str] = None, mode: str = "full_auto",
                          execute: bool = True) -> dict:
    """
    多智能体协同决策：情报 → 分析 → 决策 → 执行。
    execute=False 时只做分析不执行（非交易时间）。
    """
    if not boards:
        return {"error": "未指定板块", "timestamp": "", "steps": [], "decisions": [], "exec_results": ["未指定板块"]}

    result = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "steps": [],
    }

    # Step 1: 情报智能体
    _log.info("Step 1: Intelligence Agent gathering...")
    intel = IntelligenceAgent.gather(boards)
    intel_prompt = IntelligenceAgent.to_prompt(intel)
    result["steps"].append({
        "agent": IntelligenceAgent.NAME,
        "status": "✅ 完成",
        "summary": f"采集 {intel.get('market', {}).get('total', 0)} 只股票, {len(intel.get('events', []))} 条事件",
        "output": intel_prompt,
    })

    # Step 2: 分析智能体
    _log.info("Step 2: Analysis Agent analyzing...")
    analysis = AnalysisAgent.analyze(intel, boards)
    analysis_prompt = AnalysisAgent.to_prompt(analysis)
    result["steps"].append({
        "agent": AnalysisAgent.NAME,
        "status": "✅ 完成",
        "summary": f"评分 {len(analysis.get('candidates', []))} 只候选, 环境: {analysis.get('market_regime', '-')}",
        "output": analysis_prompt,
    })

    # Step 3: 构建持仓上下文
    from desktop.ai_trader import _build_portfolio_context
    portfolio = _build_portfolio_context(mode)

    # Step 4: 决策智能体
    _log.info("Step 3: Decision Agent deciding...")
    response = DecisionAgent.decide(intel_prompt, analysis_prompt, portfolio)
    result["steps"].append({
        "agent": DecisionAgent.NAME,
        "status": "✅ 完成",
        "summary": "已输出决策",
        "output": response,
    })

    # 解析决策
    import json as _json
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = _json.loads(response[start:end])
        else:
            parsed = {"analysis": response, "decisions": []}
    except Exception:
        parsed = {"analysis": response, "decisions": []}

    result["decisions"] = parsed.get("decisions", [])
    result["analysis"] = parsed.get("analysis", "")

    # Step 5: 执行（仅在交易时间）
    if result["decisions"] and execute:
        from desktop.ai_trader import execute_ai_decisions
        exec_results = execute_ai_decisions(result["decisions"], mode=mode)
        result["steps"].append({
            "agent": "⚡ 执行引擎",
            "status": "✅ 完成",
            "summary": f"执行 {len(exec_results)} 条",
            "output": "\n".join(exec_results),
        })
        result["exec_results"] = exec_results
    elif result["decisions"] and not execute:
        n = len(result["decisions"])
        result["steps"].append({
            "agent": "⏳ 执行引擎",
            "status": "⏸️ 等待开盘",
            "summary": f"{n} 条决策待执行（非交易时间）",
            "output": "",
        })
        result["exec_results"] = [f"⏳ {n} 条决策已生成，等待交易时间执行"]
    else:
        result["exec_results"] = ["暂无操作"]

    # Step 6: 保存决策记忆（供后续学习和校准）
    _save_decision_memory(result)

    # Step 7: 更新跟踪止损
    if mode == "full_auto":
        try:
            from desktop.ai_trader import update_trailing_stops
            stop_updates = update_trailing_stops(mode)
            if stop_updates:
                result["steps"].append({
                    "agent": "🛡️ 风控引擎",
                    "status": "✅ 完成",
                    "summary": f"ATR跟踪止损更新 {len(stop_updates)} 只",
                    "output": "\n".join(stop_updates),
                })
                result["exec_results"].extend(stop_updates)
        except Exception:
            pass

    return result
