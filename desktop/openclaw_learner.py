"""
OpenClaw 自主学习引擎
采集各模块执行结果 → 评估策略表现 → 学习规律 → 优化参数 → 赋能完全自主仓

学习闭环：
  选股模块结果 ──→ 走势验证 ──→ 准确率统计 ──→ 策略权重调整
  AI决策记忆   ──→ 盈亏校准 ──→ 决策模式分析 ──→ LLM prompt优化
  短期选股     ──→ 事件回测 ──→ 事件有效性   ──→ 关键词权重调整
"""
import json
import logging
import numpy as np
from datetime import datetime, date, timedelta

from api_server.config import settings

from desktop.data_access import get_repo

_log = logging.getLogger("openclaw_learner")

_LEARN_DDL_SQLITE = """
    CREATE TABLE IF NOT EXISTS openclaw_learning (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        module TEXT,
        metric TEXT,
        value REAL,
        detail TEXT,
        applied INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS openclaw_strategy_weights (
        strategy TEXT PRIMARY KEY,
        weight REAL DEFAULT 1.0,
        accuracy REAL DEFAULT 0,
        avg_pnl_5d REAL DEFAULT 0,
        sample_count INTEGER DEFAULT 0,
        last_updated TEXT
    );
"""


def _ensure_table():
    if settings.db_backend == "postgres":
        return
    get_repo().executescript(_LEARN_DDL_SQLITE)


def _upsert_strategy_weight(
    repo, strategy: str, weight: float, acc: float, avg5: float, sample: int, now: str
) -> None:
    if settings.db_backend == "postgres":
        repo.execute(
            """
            INSERT INTO openclaw_strategy_weights
            (strategy, weight, accuracy, avg_pnl_5d, sample_count, last_updated)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT (strategy) DO UPDATE SET
            weight=EXCLUDED.weight, accuracy=EXCLUDED.accuracy,
            avg_pnl_5d=EXCLUDED.avg_pnl_5d, sample_count=EXCLUDED.sample_count,
            last_updated=EXCLUDED.last_updated
            """,
            (strategy, weight, acc, avg5, sample, now),
        )
    else:
        repo.execute(
            "INSERT OR REPLACE INTO openclaw_strategy_weights "
            "VALUES (?,?,?,?,?,?)",
            (strategy, weight, acc, avg5, sample, now),
        )


# ═══════════════════════════════════════
# 1. 采集各模块结果
# ═══════════════════════════════════════

def collect_scan_performance() -> dict:
    """采集选股模块历史表现：各策略的走势验证准确率。"""
    repo = get_repo()
    results = {}
    try:
        rows = repo.fetchall("""
            SELECT strategy, COUNT(*) as total,
                   SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) as wins,
                   AVG(CASE WHEN pnl_5d IS NOT NULL THEN pnl_5d END) as avg5,
                   AVG(CASE WHEN pnl_10d IS NOT NULL THEN pnl_10d END) as avg10
            FROM trend_verify WHERE correct >= 0
            GROUP BY strategy
        """, ())
        for strategy, total, wins, avg5, avg10 in rows:
            acc = wins / total * 100 if total > 0 else 0
            results[strategy or "SEPA"] = {
                "total": total, "wins": wins, "accuracy": round(acc, 1),
                "avg_pnl_5d": round(avg5 or 0, 2),
                "avg_pnl_10d": round(avg10 or 0, 2),
            }
    except Exception as e:
        _log.warning(f"collect scan perf: {e}")
    return results


def collect_ai_decision_performance() -> dict:
    """采集 AI 决策历史表现。"""
    repo = get_repo()
    result = {"total": 0, "correct": 0, "accuracy": 0, "avg_pnl": 0, "by_mode": {}}
    try:
        rows = repo.fetchall("""
            SELECT mode, COUNT(*) as total,
                   SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) as wins,
                   AVG(pnl_5d) as avg_pnl
            FROM ai_decision_memory WHERE calibrated=1
            GROUP BY mode
        """, ())
        for mode, total, wins, avg_pnl in rows:
            acc = wins / total * 100 if total > 0 else 0
            result["by_mode"][mode or "auto"] = {
                "total": total, "correct": wins,
                "accuracy": round(acc, 1), "avg_pnl": round(avg_pnl or 0, 2),
            }
            result["total"] += total
            result["correct"] += wins
        if result["total"] > 0:
            result["accuracy"] = round(result["correct"] / result["total"] * 100, 1)
    except Exception as e:
        _log.warning(f"collect ai perf: {e}")
    return result


def collect_portfolio_performance() -> dict:
    """采集各仓位的收益表现对比。"""
    try:
        from desktop.ai_portfolio import get_comparison
        comp = get_comparison()
        perf = {}
        for mode in ["full_auto", "auto", "manual", "custom", "quantum"]:
            c = comp.get(mode, {})
            perf[mode] = {
                "return_pct": c.get("return_pct", 0),
                "win_rate": c.get("win_rate", 0),
                "total_trades": c.get("total_trades", 0),
                "total_pnl": c.get("total_pnl", 0),
            }
        return perf
    except Exception as e:
        _log.warning(f"collect portfolio perf: {e}")
        return {}


# ═══════════════════════════════════════
# 2. 评估与学习
# ═══════════════════════════════════════

def evaluate_and_learn() -> dict:
    """
    核心学习函数：
    1. 采集所有模块的历史表现
    2. 评估各策略有效性
    3. 更新策略权重
    4. 生成优化建议
    """
    _ensure_table()
    repo = get_repo()
    now = datetime.now().isoformat()

    scan_perf = collect_scan_performance()
    ai_perf = collect_ai_decision_performance()
    portfolio_perf = collect_portfolio_performance()

    learnings = []

    # ── 学习1: 策略权重调整 ──
    for strategy, perf in scan_perf.items():
        acc = perf["accuracy"]
        avg5 = perf["avg_pnl_5d"]
        sample = perf["total"]

        # 权重 = 准确率 × 正收益倍数，样本少的降权
        confidence = min(1.0, sample / 20)
        weight = (acc / 50) * max(0.5, 1 + avg5 / 10) * confidence
        weight = round(max(0.1, min(3.0, weight)), 2)

        _upsert_strategy_weight(repo, strategy, weight, acc, avg5, sample, now)
        learnings.append({
            "module": "选股策略",
            "finding": f"{strategy}: 准确率{acc:.0f}%, 5日均涨{avg5:+.1f}%, 权重→{weight}",
            "weight": weight,
        })

        repo.execute(
            "INSERT INTO openclaw_learning (timestamp,module,metric,value,detail) "
            "VALUES (?,?,?,?,?)",
            (now, "scan", f"accuracy_{strategy}", acc,
             json.dumps(perf, ensure_ascii=False)),
        )

    # ── 学习2: AI 决策模式分析 ──
    if ai_perf["total"] > 0:
        repo.execute(
            "INSERT INTO openclaw_learning (timestamp,module,metric,value,detail) "
            "VALUES (?,?,?,?,?)",
            (now, "ai_decision", "overall_accuracy", ai_perf["accuracy"],
             json.dumps(ai_perf, ensure_ascii=False)),
        )
        learnings.append({
            "module": "AI决策",
            "finding": f"总决策{ai_perf['total']}次, 准确率{ai_perf['accuracy']:.0f}%",
        })

    # ── 学习3: 仓位表现对比 ──
    if portfolio_perf:
        best_mode = max(portfolio_perf, key=lambda m: portfolio_perf[m].get("return_pct", -999))
        worst_mode = min(portfolio_perf, key=lambda m: portfolio_perf[m].get("return_pct", 999))
        learnings.append({
            "module": "仓位对比",
            "finding": (
                f"最优: {best_mode}({portfolio_perf[best_mode]['return_pct']:+.2f}%) "
                f"最差: {worst_mode}({portfolio_perf[worst_mode]['return_pct']:+.2f}%)"
            ),
        })
        repo.execute(
            "INSERT INTO openclaw_learning (timestamp,module,metric,value,detail) "
            "VALUES (?,?,?,?,?)",
            (now, "portfolio", "best_mode_return",
             portfolio_perf[best_mode]["return_pct"],
             json.dumps(portfolio_perf, ensure_ascii=False)),
        )

    return {
        "scan_perf": scan_perf,
        "ai_perf": ai_perf,
        "portfolio_perf": portfolio_perf,
        "learnings": learnings,
        "timestamp": now,
    }


def get_strategy_weights() -> dict:
    """获取学习后的策略权重（供选股和 AI 决策使用）。"""
    _ensure_table()
    rows = get_repo().fetchall(
        "SELECT strategy, weight, accuracy, avg_pnl_5d, sample_count "
        "FROM openclaw_strategy_weights",
        (),
    )
    return {
        r[0]: {"weight": r[1], "accuracy": r[2], "avg_pnl_5d": r[3], "samples": r[4]}
        for r in rows
    }


# ═══════════════════════════════════════
# 3. 生成 AI 优化建议（用 LLM 分析学习数据）
# ═══════════════════════════════════════

def generate_evolution_advice(learn_result: dict) -> str:
    """让 LLM 基于学习数据给出自主进化建议。"""
    try:
        from desktop.ai_trader import _call_llm
        context = json.dumps(learn_result, ensure_ascii=False, default=str)
        prompt = (
            f"以下是量化交易系统各模块的历史表现数据：\n{context}\n\n"
            f"请分析：\n"
            f"1. 哪些选股策略表现好/差？建议如何调整策略权重？\n"
            f"2. AI 决策的准确率如何？哪些决策模式值得加强？\n"
            f"3. 5 个仓位中哪个最有效？为什么？\n"
            f"4. 对完全自主仓提出具体优化建议（买入条件/仓位/止损/板块偏好）\n"
            f"5. 下一步应该重点关注什么？\n\n"
            f"请用简洁、可执行的方式回答。"
        )
        return _call_llm(prompt, system="你是量化交易系统的自我进化引擎，负责分析历史数据并提出优化建议。")
    except Exception as e:
        return f"生成建议失败: {e}"


# ═══════════════════════════════════════
# 4. 赋能完全自主仓
# ═══════════════════════════════════════

def get_enhanced_full_auto_prompt() -> str:
    """基于学习结果，为完全自主仓生成增强的 LLM 系统提示。"""
    weights = get_strategy_weights()
    if not weights:
        return ""

    lines = ["\n== 策略学习反馈（自主进化引擎） =="]

    # 按权重排序
    sorted_w = sorted(weights.items(), key=lambda x: x[1]["weight"], reverse=True)
    lines.append("策略有效性排名（基于历史走势验证）：")
    for i, (strat, w) in enumerate(sorted_w, 1):
        lines.append(
            f"  {i}. {strat}: 权重{w['weight']:.1f} "
            f"准确率{w['accuracy']:.0f}% 5日均涨{w['avg_pnl_5d']:+.1f}% "
            f"(样本{w['samples']})"
        )

    # 指导建议
    best = sorted_w[0] if sorted_w else None
    worst = sorted_w[-1] if sorted_w else None
    if best and worst:
        lines.append(f"\n⭐ 重点关注 {best[0]} 策略的候选股（准确率最高）")
        if worst[1]["accuracy"] < 30:
            lines.append(f"⚠️ 回避 {worst[0]} 策略的候选（准确率过低）")

    lines.append("请将以上学习结果融入你的决策过程。")
    return "\n".join(lines)


def get_learning_history(limit: int = 20) -> list[dict]:
    """获取学习历史记录。"""
    _ensure_table()
    rows = get_repo().fetchall(
        "SELECT timestamp, module, metric, value, detail "
        "FROM openclaw_learning ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [
        {"timestamp": r[0], "module": r[1], "metric": r[2],
         "value": r[3], "detail": r[4]}
        for r in rows
    ]
