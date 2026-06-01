"""
Smoke verification for OpenClaw ABC phases:
  A) S2/S3 candidate alignment
  B) Decision price grounding
  C) Calibrated reflection injection
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def check(name: str, fn) -> bool:
    try:
        result = fn()
        print(f"[PASS] {name}: {result}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    tmpdir = tempfile.mkdtemp(prefix="finquanta_abc_verify_")
    db_path = Path(tmpdir) / "verify.db"
    os.environ["FINQUANTA_DB_BACKEND"] = "sqlite"
    os.environ["FINQUANTA_SQLITE_PATH"] = str(db_path)

    ok = True

    from core.ai.decision_memory import ensure_decision_memory_table
    from core.repositories.decision_repo import DecisionRepository
    from desktop.data_access import RepoCompatConnection, ensure_platform_tables

    ensure_decision_memory_table()
    ensure_platform_tables()
    from desktop.db import init_db

    init_db()
    repo = DecisionRepository()

    actual_payload = {
        "executed_buys": [{"code": "300750", "pnl_pct": 3.2, "correct": True}],
        "summary": {
            "executed_count": 1,
            "executed_correct": 1,
            "blocked_avoided_losses": 1,
            "blocked_missed_gains": 0,
        },
    }
    repo.save_memory(
        timestamp="2025-11-03T10:00:00",
        mode="auto",
        decisions=[{"action": "buy", "code": "300750", "board": "电池", "price": 188.5, "shares": 500}],
        raw_decisions=[{"action": "buy", "code": "300750", "board": "电池", "price": 999.0, "shares": 500}],
        analysis="电池板块试探性买入",
        market_regime="🟡 震荡",
        verification_summary={"verified_count": 1},
        guardrail_summary={"blocked_buy_count": 0},
    )
    row = RepoCompatConnection().execute(
        "SELECT id FROM ai_decision_memory ORDER BY id DESC LIMIT 1",
        (),
    ).fetchone()
    repo.mark_calibrated(int(row[0]), actual_payload)

    s2_candidates = [
        {
            "code": "300750",
            "name": "宁德时代",
            "score": 82,
            "price": 188.5,
            "board": "电池",
            "momentum_1m": 4.2,
            "strategy": "SEPA",
        },
        {
            "code": "300308",
            "name": "中际旭创",
            "score": 76,
            "price": 120.0,
            "board": "芯片",
            "momentum_1m": 2.0,
            "strategy": "VCP",
        },
    ]

    from desktop.agents import adapt_pipeline_candidates, run_multi_agent_cycle

    ok &= check(
        "phase_a_adapt_pipeline_candidates",
        lambda: (
            len(adapt_pipeline_candidates(s2_candidates)) == 2
            and adapt_pipeline_candidates(s2_candidates)[0]["code"] == "300750"
        ),
    )

    from core.ai.decision_grounding import normalize_buy_decisions

    ok &= check(
        "phase_b_normalize_buy_decisions",
        lambda: normalize_buy_decisions(
            [{"action": "buy", "code": "300750", "price": 999.0, "shares": 500}],
            {"300750": 188.5},
        )[0][0]["price"] == 188.5,
    )

    from core.ai.context_builder import build_decision_reflection_context_text

    reflection_text = build_decision_reflection_context_text(boards=["电池"])
    ok &= check(
        "phase_c_reflection_context",
        lambda: ("历史决策反思" in reflection_text and "执行1笔买入" in reflection_text),
    )

    import desktop.agents as agents

    original_gather = agents.IntelligenceAgent.gather
    original_analyze = agents.AnalysisAgent.analyze
    original_decide = agents.DecisionAgent.decide
    original_portfolio = None

    def fake_gather(boards):
        return {"market": {"total": 100, "up": 55, "down": 40}, "events": [], "boards": []}

    def fake_decide(*args, **kwargs):
        return json.dumps(
            {
                "analysis": "集成验证",
                "decisions": [
                    {
                        "action": "buy",
                        "code": "300750",
                        "name": "宁德时代",
                        "price": 999.0,
                        "shares": 500,
                        "board": "电池",
                    }
                ],
            },
            ensure_ascii=False,
        )

    agents.IntelligenceAgent.gather = staticmethod(fake_gather)
    agents.DecisionAgent.decide = staticmethod(fake_decide)

    try:
        from desktop import ai_trader

        original_portfolio = ai_trader._build_portfolio_context
        ai_trader._build_portfolio_context = lambda mode: "== 持仓上下文 =="

        result = run_multi_agent_cycle(
            boards=["电池", "芯片"],
            mode="auto",
            execute=False,
            persist_memory=False,
            prefilled_candidates=s2_candidates,
        )
    finally:
        agents.IntelligenceAgent.gather = original_gather
        agents.AnalysisAgent.analyze = original_analyze
        agents.DecisionAgent.decide = original_decide
        if original_portfolio is not None:
            ai_trader._build_portfolio_context = original_portfolio

    ok &= check(
        "integration_analysis_source",
        lambda: result.get("verification") is not None
        and any(
            step.get("summary", "").find("openclaw_s2") >= 0
            for step in result.get("steps", [])
            if "分析" in step.get("agent", "")
        ),
    )
    ok &= check(
        "integration_decision_grounding",
        lambda: bool(result.get("decision_grounding", {}).get("adjustments")),
    )
    ok &= check(
        "integration_reflection_context",
        lambda: "历史决策反思" in (result.get("decision_reflection_context") or ""),
    )
    ok &= check(
        "integration_final_buy_price",
        lambda: result.get("decisions", [{}])[0].get("price") == 188.5,
    )

    print(f"\nDatabase: {db_path}")
    print("RESULT:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
