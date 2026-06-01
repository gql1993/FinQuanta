import json
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_runtime_mode_resolution_defaults():
    from core.runtime.mode import LOCAL_MODE, PLATFORM_MODE, resolve_runtime_mode_context

    local_ctx = resolve_runtime_mode_context(
        runtime_mode=None,
        db_backend="sqlite",
        api_base="http://127.0.0.1:9000",
    )
    platform_ctx = resolve_runtime_mode_context(
        runtime_mode=None,
        db_backend="postgres",
        api_base="http://127.0.0.1:9000",
    )

    assert local_ctx.runtime_mode == LOCAL_MODE
    assert local_ctx.is_local_mode is True
    assert platform_ctx.runtime_mode == PLATFORM_MODE
    assert platform_ctx.is_platform_mode is True


def test_feature_flags_env_override(monkeypatch):
    from core.config.feature_flags import is_feature_enabled

    monkeypatch.delenv("FINQUANTA_FEATURE_OPENCLAW_PIPELINE", raising=False)
    assert is_feature_enabled("openclaw_pipeline") is True

    monkeypatch.setenv("FINQUANTA_FEATURE_OPENCLAW_PIPELINE", "0")
    assert is_feature_enabled("openclaw_pipeline") is False

    monkeypatch.setenv("FINQUANTA_FEATURE_TRADE_APPROVAL", "1")
    assert is_feature_enabled("trade_approval") is True


def test_settings_center_int_override(monkeypatch):
    from core.config.settings_center import settings_center

    monkeypatch.setenv("FINQUANTA_WEB_OPS_CENTER_CACHE_TTL", "12")
    assert settings_center.get_int("FINQUANTA_WEB_OPS_CENTER_CACHE_TTL", 5) == 12

    monkeypatch.setenv("FINQUANTA_WEB_OPS_CENTER_CACHE_TTL", "invalid")
    assert settings_center.get_int("FINQUANTA_WEB_OPS_CENTER_CACHE_TTL", 5) == 5


def test_infrastructure_db_backends_available():
    import tempfile
    from pathlib import Path

    from infrastructure.db.postgres import PostgresBackend
    from infrastructure.db.sqlite import SQLiteBackend

    assert PostgresBackend.normalize_sql("SELECT ? FROM t WHERE id=?") == "SELECT %s FROM t WHERE id=%s"

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "refactor_test.db")
        backend = SQLiteBackend(db_path)
        backend.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        backend.execute("INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)", ("k", "v"))
        row = backend.fetchone("SELECT value FROM kv_store WHERE key=?", ("k",))
        assert row and row[0] == "v"


def test_sync_export_import_services_roundtrip(tmp_path):
    from core.sync.export_service import build_export_payload, export_to_file
    from core.sync.import_service import import_from_file

    class FakeRepo:
        def __init__(self):
            self.store = {"manual_portfolio": {"cash": 100}, "ai_config": {"model": "x"}}

        def kv_get(self, key, default=None):
            return self.store.get(key, default)

        def kv_set(self, key, value):
            self.store[key] = value

    src = FakeRepo()
    payload = build_export_payload(keys=["manual_portfolio", "ai_config"], repository=src)
    assert payload["data"]["manual_portfolio"]["cash"] == 100

    out_file = tmp_path / "sync_export.json"
    exported = export_to_file(str(out_file), keys=["manual_portfolio", "ai_config"], repository=src)
    assert exported["key_count"] == 2
    assert out_file.exists()

    dst = FakeRepo()
    dst.store = {"manual_portfolio": {"cash": 50}}
    imported = import_from_file(str(out_file), overwrite=False, repository=dst)
    assert imported["total"] == 2
    assert imported["skipped"] == 1
    assert imported["imported"] == 1
    assert dst.store["manual_portfolio"]["cash"] == 50
    assert dst.store["ai_config"]["model"] == "x"


def test_snapshot_service_manual_summary_separates_realized_and_unrealized(monkeypatch):
    import core.application.snapshot_service as snapshot_service

    monkeypatch.setattr(
        snapshot_service,
        "_load_latest_prices",
        lambda codes: {"000001": 12.0},
    )

    summary = snapshot_service._build_manual_portfolio_summary(
        {
            "cash": 995000.0,
            "initial_capital": 1000000.0,
            "positions": [
                {"code": "000001", "entry_price": 10.0, "shares": 1000},
            ],
            "history": [
                {"action": "BUY", "code": "000001", "price": 10.0, "shares": 1000},
                {"action": "SELL", "code": "000002", "pnl": 5000.0},
            ],
        }
    )

    assert summary["unrealized_pnl"] == 2000.0
    assert summary["realized_pnl"] == 5000.0
    assert summary["total_pnl"] == 7000.0
    assert summary["return_pct"] == 0.7
    assert summary["total_trades"] == 2


def test_trend_verify_classifies_market_drag_failure():
    from desktop.trend_verify import _classify_failure_profile

    result = _classify_failure_profile(
        {
            "best_pnl": -6.2,
            "max_gain": 1.1,
            "max_loss": -8.5,
            "index_pnl": -3.8,
            "weak_volume": False,
            "ma_break": True,
            "consecutive_down": 4,
            "market_regime": "弱市",
        }
    )

    assert result["root_cause"] == "市场拖累"
    assert "市场拖累" in result["failure_tags"]
    assert result["market_regime"] == "弱市"


def test_trend_verify_service_failure_summary_shape():
    from core.application.trend_verify_service import get_trend_failure_summary

    payload = get_trend_failure_summary(limit=5)
    assert isinstance(payload, dict)
    assert "failed_total" in payload
    assert "top_root_causes" in payload
    assert "top_tags" in payload


def test_trend_verify_records_routed_blocked_decisions(monkeypatch):
    import desktop.trend_verify as trend_verify

    executed_sql: list[tuple[str, tuple]] = []

    class FakeCursor:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    class FakeConn:
        def execute(self, sql, params=()):
            executed_sql.append((sql, tuple(params) if isinstance(params, (list, tuple)) else ()))
            if "MAX(date)" in sql:
                return FakeCursor([("2026-04-20",)])
            if "SELECT code, board FROM board_stocks" in sql:
                return FakeCursor([("300750", "电池")])
            if "SELECT id FROM trend_verify" in sql:
                return FakeCursor([])
            if "SELECT close FROM daily_kline" in sql:
                return FakeCursor([(188.0,)])
            return FakeCursor([])

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(trend_verify, "RepoCompatConnection", lambda: FakeConn())
    monkeypatch.setattr(trend_verify, "_ensure_schema", lambda conn: None)

    count = trend_verify.record_routed_blocked_decisions(
        [{"action": "buy", "code": "300750", "name": "宁德时代", "reason": "策略分流: 买入数量超限"}],
        raw_decisions=[{"action": "buy", "code": "300750", "price": 188.0, "score": 90}],
    )

    assert count == 1
    insert_calls = [item for item in executed_sql if "INSERT INTO trend_verify" in item[0]]
    assert insert_calls
    assert "CoordinatorRoute" in insert_calls[0][1]
    assert "routed_blocked" in insert_calls[0][1]


def test_verification_agent_marks_risky_candidates(monkeypatch):
    import desktop.trend_verify as trend_verify
    from desktop.agents import VerificationAgent

    monkeypatch.setattr(
        trend_verify,
        "get_records",
        lambda **kwargs: [
            {"code": "600519", "board": "白酒"},
            {"code": "600519", "board": "白酒"},
            {"code": "000001", "board": "银行"},
        ],
    )
    monkeypatch.setattr(
        trend_verify,
        "get_accuracy_stats",
        lambda: {"accuracy": 42.0},
    )
    monkeypatch.setattr(
        trend_verify,
        "get_failure_summary",
        lambda **kwargs: {"top_root_causes": [{"label": "市场拖累"}]},
    )

    result = VerificationAgent.verify(
        {
            "market_regime": "🔴 弱势（多数下跌，控制仓位）",
            "candidates": [
                {"code": "600519", "name": "贵州茅台", "board": "白酒", "total": 52},
                {"code": "300750", "name": "宁德时代", "board": "电池", "total": 78},
            ],
        }
    )

    assert result["accuracy"] == 42.0
    rejected = result["rejected_candidates"][0]
    verified = result["verified_candidates"][0]
    assert rejected["code"] == "600519"
    assert rejected["verification_score"] < 45
    assert rejected["board_risk_level"] in {"medium", "high"}
    assert "history_fail" in rejected["verification_reason_tags"]
    assert verified["code"] == "300750"
    assert verified["verification_score"] >= 75


def test_verification_guardrails_block_rejected_buys():
    from desktop.agents import _apply_verification_guardrails

    guard = _apply_verification_guardrails(
        [
            {"action": "buy", "code": "600519", "name": "贵州茅台", "reason": "test buy"},
            {"action": "buy", "code": "300750", "name": "宁德时代", "reason": "test maybe"},
            {"action": "sell", "code": "000001", "name": "平安银行", "reason": "test sell"},
        ],
        {
            "verified_candidates": [],
            "questionable_candidates": [
                {
                    "code": "300750",
                    "name": "宁德时代",
                    "verification_notes": ["综合评分中等，建议二次确认"],
                    "verification_score": 63,
                }
            ],
            "rejected_candidates": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "verification_notes": ["该股近120天失败信号 2 次"],
                    "verification_score": 38,
                }
            ],
        },
    )

    filtered = guard["filtered_decisions"]
    assert len(filtered) == 2
    assert all(item.get("code") != "600519" for item in filtered)
    maybe_buy = next(item for item in filtered if item.get("code") == "300750")
    assert maybe_buy["verification"] == "questionable"
    assert "验证存疑" in maybe_buy["reason"]
    assert guard["blocked_buys"][0]["code"] == "600519"


def test_save_decision_memory_includes_verification_summaries(monkeypatch):
    import core.ai.decision_memory as decision_memory

    captured = {}

    class FakeRepo:
        def ensure_table(self):
            return None

        def save_memory(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(decision_memory, "decision_repo", FakeRepo())

    decision_memory.save_decision_memory(
        {
            "timestamp": "2026-04-14T00:00:00",
            "mode": "auto",
            "decisions": [{"action": "buy", "code": "300750"}],
            "raw_decisions": [{"action": "buy", "code": "300750"}, {"action": "buy", "code": "600519"}],
            "analysis": "test",
            "steps": [
                {"agent": "📡 情报智能体", "summary": "采集 10 只股票, 2 条事件"},
                {"agent": "🔬 分析智能体", "summary": "评分 6 只候选, 环境: 🟡 震荡"},
            ],
            "verification": {
                "verified_candidates": [{"code": "300750"}],
                "questionable_candidates": [{"code": "000001"}],
                "rejected_candidates": [{"code": "600519"}],
                "top_failure_roots": ["市场拖累"],
                "accuracy": 44.5,
            },
            "decision_guardrails": {
                "blocked_buys": [{"code": "600519"}],
                "annotated_buys": [{"code": "000001"}],
                "summary": "拦截高风险买入 1 条，标记存疑买入 1 条",
            },
            "execution_plan": {
                "mode": "limit_buy",
                "policy": {"max_buy_count": 1},
                "blocked": [{"action": "buy", "code": "000333", "reason": "策略分流: 买入数量超限"}],
            },
        }
    )

    assert captured["raw_decisions"][1]["code"] == "600519"
    assert captured["verification_summary"]["rejected_count"] == 1
    assert captured["guardrail_summary"]["blocked_buy_count"] == 1
    assert captured["execution_plan"]["mode"] == "limit_buy"
    assert captured["execution_plan"]["blocked_count"] == 1


def test_decision_accuracy_supports_structured_actual_results(monkeypatch):
    import core.ai.decision_memory as decision_memory

    class FakeRepo:
        def ensure_table(self):
            return None

        def get_recent_calibrated_results(self, limit=50):
            import json

            return [
                json.dumps(
                    {
                        "executed_buys": [
                            {"code": "300750", "pnl_pct": 5.0, "correct": True},
                            {"code": "000001", "pnl_pct": -2.0, "correct": False},
                        ],
                        "blocked_buys": [
                            {"code": "600519", "pnl_pct": -4.0, "correct": False},
                        ],
                    },
                    ensure_ascii=False,
                )
            ]

    monkeypatch.setattr(decision_memory, "decision_repo", FakeRepo())
    payload = decision_memory.get_decision_accuracy(limit=5)

    assert payload["total_decisions"] == 2
    assert payload["correct"] == 1
    assert payload["accuracy"] == 50.0
    assert payload["avg_pnl"] == 1.5


def test_openclaw_learner_collects_verification_effectiveness(monkeypatch):
    import desktop.openclaw_learner as learner
    import core.repositories.decision_repo as decision_repo_module

    class FakeDecisionRepo:
        def get_recent_calibrated_memories(self, limit=120):
            import json

            return [
                (
                    "2026-04-14T00:00:00",
                    "auto",
                    json.dumps(
                        {
                            "executed_buys": [
                                {"code": "300750", "pnl_pct": 6.0, "correct": True},
                                {"code": "000001", "pnl_pct": -3.0, "correct": False},
                            ],
                            "blocked_buys": [
                                {"code": "600519", "pnl_pct": -5.0, "correct": False},
                                {"code": "000333", "pnl_pct": 4.0, "correct": True},
                            ],
                            "routed_blocked_buys": [
                                {"code": "002594", "pnl_pct": -2.5, "correct": False},
                                {"code": "300059", "pnl_pct": 3.5, "correct": True},
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps({"verified_count": 3, "questionable_count": 1, "rejected_count": 2}, ensure_ascii=False),
                    json.dumps({"blocked_buy_count": 2, "annotated_buy_count": 1}, ensure_ascii=False),
                    json.dumps({"mode": "limit_buy", "blocked_count": 2}, ensure_ascii=False),
                )
            ]

        @staticmethod
        def _load_json(raw, default):
            import json

            try:
                return json.loads(raw) if raw else default
            except Exception:
                return default

    monkeypatch.setattr(decision_repo_module, "DecisionRepository", lambda: FakeDecisionRepo())
    payload = learner.collect_ai_decision_performance()

    assert payload["total"] == 2
    assert payload["correct"] == 1
    assert payload["verification_effectiveness"]["blocked_buy_count"] == 2
    assert payload["verification_effectiveness"]["avoided_losses"] == 1
    assert payload["verification_effectiveness"]["missed_gains"] == 1
    assert payload["coordinator_effectiveness"]["routed_blocked_count"] == 2
    assert payload["coordinator_effectiveness"]["avoided_losses"] == 1
    assert payload["coordinator_effectiveness"]["missed_gains"] == 1
    assert payload["coordinator_effectiveness"]["limit_buy_count"] == 1


def test_openclaw_learner_verification_effect_summary_text():
    from desktop.openclaw_learner import _build_coordinator_effect_summary, _build_verification_effect_summary

    text = _build_verification_effect_summary(
        {
            "verification_effectiveness": {
                "blocked_buy_count": 3,
                "avoided_losses": 2,
                "missed_gains": 1,
                "annotated_buy_count": 4,
                "verified_candidates": 10,
                "questionable_candidates": 5,
                "rejected_candidates": 2,
                "avoided_loss_rate": 66.7,
            }
        }
    )

    assert "拦截买入3次" in text
    assert "避免亏损2次" in text
    assert "避免亏损率66.7%" in text

    coord_text = _build_coordinator_effect_summary(
        {
            "coordinator_effectiveness": {
                "routed_blocked_count": 2,
                "avoided_losses": 1,
                "missed_gains": 1,
                "avoided_loss_rate": 50.0,
                "sell_only_count": 1,
                "limit_buy_count": 1,
                "observe_only_count": 0,
            }
        }
    )
    assert "分流拦截2次" in coord_text
    assert "limit_buy 1次" in coord_text


def test_portfolio_recommendations_include_guardrail_payload(monkeypatch):
    import core.application.portfolio_service as portfolio_service

    class FakeRepo:
        def get_latest_auto_decision_memory(self):
            return {
                "timestamp": "2026-04-14T00:00:00",
                "analysis": "ok",
                "items": [{"action": "buy", "code": "300750"}],
                "raw_items": [{"action": "buy", "code": "300750"}, {"action": "buy", "code": "600519"}],
                "verification_summary": {"verified_count": 1, "rejected_count": 1},
                "guardrail_summary": {"blocked_buy_count": 1},
                "execution_plan": {"mode": "sell_only", "blocked_count": 1},
            }

    monkeypatch.setattr(portfolio_service, "portfolio_repo", FakeRepo())
    payload = portfolio_service.get_portfolio_recommendations(limit=10)

    assert payload["raw_items"][1]["code"] == "600519"
    assert payload["verification_summary"]["rejected_count"] == 1
    assert payload["guardrail_summary"]["blocked_buy_count"] == 1
    assert payload["execution_plan"]["mode"] == "sell_only"


def test_coordinator_agent_plan_and_summary_shape():
    from desktop.agents import CoordinatorAgent

    plan = CoordinatorAgent.plan_pipeline(["人工智能", "芯片", "量子科技"])
    summary = CoordinatorAgent.summarize_pipeline(
        {
            "steps": [{"status": "ok"}, {"status": "ok"}, {"status": "error"}],
            "candidates": [{"code": "300750"}],
            "decisions": [{"action": "buy", "code": "300750"}],
            "decision_guardrails": {
                "blocked_buys": [{"code": "600519"}],
                "annotated_buys": [{"code": "000001"}],
            },
        }
    )

    assert plan["focus_boards"][0] == "人工智能"
    assert "stage_plan" in plan
    assert summary["blocked_buy_count"] == 1
    assert "next_action" in summary


def test_multi_agent_cycle_emits_agent_trace(monkeypatch):
    import desktop.agents as agents

    monkeypatch.setattr(
        agents.IntelligenceAgent,
        "gather",
        staticmethod(lambda boards: {"market": {"total": 3, "up": 2, "down": 1}, "events": [], "boards": []}),
    )
    monkeypatch.setattr(
        agents.AnalysisAgent,
        "analyze",
        staticmethod(
            lambda intel, boards, prefilled_candidates=None: {
                "market_regime": "🟡 震荡",
                "candidates": [
                    {
                        "code": "300750",
                        "name": "宁德时代",
                        "board": "电池",
                        "total": 80,
                        "trend": 80,
                        "momentum": 76,
                        "signals": ["多头趋势"],
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        agents.VerificationAgent,
        "verify",
        staticmethod(
            lambda analysis: {
                "verified_candidates": [
                    {
                        "code": "300750",
                        "name": "宁德时代",
                        "verification": "verified",
                        "verification_score": 82,
                    }
                ],
                "questionable_candidates": [],
                "rejected_candidates": [],
                "all_candidates": [
                    {
                        "code": "300750",
                        "name": "宁德时代",
                        "verification": "verified",
                        "verification_score": 82,
                    }
                ],
                "risk_flags": [],
                "accuracy": 50.0,
                "top_failure_roots": [],
            }
        ),
    )
    monkeypatch.setattr(
        agents.DecisionAgent,
        "decide",
        staticmethod(
            lambda *args, **kwargs: '{"analysis":"ok","decisions":[{"action":"buy","code":"300750","name":"宁德时代","price":188.0}]}'
        ),
    )
    monkeypatch.setattr("desktop.ai_trader._build_portfolio_context", lambda mode: "portfolio context")

    result = agents.run_multi_agent_cycle(
        boards=["电池"],
        mode="auto",
        execute=False,
        persist_memory=False,
    )

    trace_items = result.get("agent_trace", [])
    keys = {item.get("agent_key") for item in trace_items}
    assert result.get("trace", {}).get("trace_id_hex")
    assert {"intelligence", "analysis", "verification", "decision", "verification_guardrail"}.issubset(keys)
    assert all(item.get("status") == "ok" for item in trace_items)


def test_adapt_pipeline_candidates_maps_s2_fields():
    import desktop.agents as agents

    adapted = agents.adapt_pipeline_candidates(
        [
            {
                "code": "300750",
                "name": "宁德时代",
                "score": 82,
                "price": 188.5,
                "board": "电池",
                "momentum_1m": 4.2,
                "strategy": "SEPA",
            },
            {"code": "300750", "name": "重复", "score": 10},
            {"name": "missing-code", "score": 50},
        ]
    )

    assert len(adapted) == 1
    item = adapted[0]
    assert item["code"] == "300750"
    assert item["total"] == 82
    assert item["price"] == 188.5
    assert item["board"] == "电池"
    assert item["candidate_source"] == "openclaw_s2"
    assert "SEPA" in item["signals"]
    assert item["momentum"] == round(min(100, max(0, 50 + 4.2 * 3)))


def test_analysis_agent_uses_prefilled_candidates(monkeypatch):
    import desktop.agents as agents

    monkeypatch.setattr(
        agents,
        "_enrich_pipeline_candidates",
        lambda candidates, conn: candidates,
    )

    intel = {"market": {"total": 10, "up": 6, "down": 3}}
    prefilled = [
        {
            "code": "688981",
            "name": "中芯国际",
            "score": 76,
            "price": 45.6,
            "board": "芯片",
            "momentum_1m": 2.0,
            "strategy": "VCP",
        }
    ]

    result = agents.AnalysisAgent.analyze(
        intel,
        ["芯片"],
        prefilled_candidates=prefilled,
    )

    assert result["candidate_source"] == "openclaw_s2"
    assert result["prefilled_count"] == 1
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["code"] == "688981"
    assert result["candidates"][0]["total"] == 76


def test_multi_agent_cycle_passes_prefilled_candidates(monkeypatch):
    import desktop.agents as agents

    captured: dict = {}

    def fake_analyze(intel, boards, prefilled_candidates=None):
        captured["prefilled_candidates"] = prefilled_candidates
        return {
            "market_regime": "🟡 震荡",
            "candidates": [],
            "candidate_source": "openclaw_s2" if prefilled_candidates else "board_scan",
            "prefilled_count": len(prefilled_candidates or []),
        }

    monkeypatch.setattr(
        agents.IntelligenceAgent,
        "gather",
        staticmethod(lambda boards: {"market": {"total": 3, "up": 2, "down": 1}, "events": [], "boards": []}),
    )
    monkeypatch.setattr(agents.AnalysisAgent, "analyze", staticmethod(fake_analyze))
    monkeypatch.setattr(
        agents.VerificationAgent,
        "verify",
        staticmethod(lambda analysis: {"verified_candidates": [], "questionable_candidates": [], "rejected_candidates": []}),
    )
    monkeypatch.setattr(
        agents.DecisionAgent,
        "decide",
        staticmethod(lambda *args, **kwargs: '{"analysis":"ok","decisions":[]}'),
    )
    monkeypatch.setattr("desktop.ai_trader._build_portfolio_context", lambda mode: "portfolio context")

    prefilled = [{"code": "300308", "name": "中际旭创", "score": 80, "price": 120.0, "board": "芯片"}]
    result = agents.run_multi_agent_cycle(
        boards=["芯片"],
        mode="auto",
        execute=False,
        persist_memory=False,
        prefilled_candidates=prefilled,
    )

    assert captured["prefilled_candidates"] == prefilled
    analysis_trace = next(item for item in result["agent_trace"] if item.get("agent_key") == "analysis")
    assert analysis_trace["input_summary"]["prefilled_count"] == "1"
    assert analysis_trace["input_summary"]["candidate_source"] == "openclaw_s2"


def test_normalize_buy_decisions_overwrites_price():
    from core.ai.decision_grounding import normalize_buy_decisions

    normalized, adjustments = normalize_buy_decisions(
        [{"action": "buy", "code": "300750", "price": 999.0, "shares": 500}],
        {"300750": 188.5},
        tolerance=0.01,
    )

    assert normalized[0]["price"] == 188.5
    assert adjustments[0]["reason"] == "price_grounded"
    assert adjustments[0]["shares_to"] == 2600


def test_build_grounded_price_map_from_verification():
    from core.ai.decision_grounding import build_grounded_price_map_from_verification

    price_map = build_grounded_price_map_from_verification(
        {
            "verified_candidates": [{"code": "300308", "price": 120.0}],
            "questionable_candidates": [{"code": "688981", "price": 45.6}],
        }
    )

    assert price_map == {"300308": 120.0, "688981": 45.6}


def test_verified_candidate_context_includes_price():
    import desktop.agents as agents

    text = agents._build_verified_candidate_context(
        {
            "verified_candidates": [
                {
                    "code": "300750",
                    "name": "宁德时代",
                    "price": 188.5,
                    "total": 82,
                    "verification_score": 80,
                    "board_risk_level": "low",
                }
            ],
            "questionable_candidates": [],
            "rejected_candidates": [],
        }
    )

    assert "现价¥188.50" in text
    assert "【价格约束】" in text


def test_apply_decision_price_grounding_uses_candidate_map(monkeypatch):
    from core.ai.decision_engine import apply_decision_price_grounding

    monkeypatch.setattr(
        "core.ai.decision_engine.build_candidates_context",
        lambda board="人工智能", limit=30: {
            "items": [{"code": "300502", "price": 378.95}],
        },
    )

    result = apply_decision_price_grounding(
        {
            "analysis": "ok",
            "decisions": [{"action": "buy", "code": "300502", "price": 400.0, "shares": 100}],
        },
        board="人工智能",
    )

    assert result["decisions"][0]["price"] == 378.95
    assert result["decision_grounding"]["adjustments"]


def test_summarize_actual_payload_from_calibrated_structure():
    from core.ai.context_builder import _summarize_actual_payload

    stats = _summarize_actual_payload(
        {
            "executed_buys": [
                {"code": "300750", "pnl_pct": 4.2, "correct": True},
                {"code": "688981", "pnl_pct": -2.1, "correct": False},
            ],
            "summary": {
                "executed_count": 2,
                "executed_correct": 1,
                "blocked_avoided_losses": 1,
                "blocked_missed_gains": 0,
            },
        }
    )

    assert stats["executed_count"] == 2
    assert stats["executed_correct"] == 1
    assert stats["correct_ratio"] == 0.5
    assert stats["avg_pnl"] == 1.05
    assert stats["blocked_avoided_losses"] == 1


def test_build_decision_history_context_reads_calibrated_summary():
    from core.ai.context_builder import build_decision_history_context

    row = (
        "2025-11-03T10:00:00",
        "auto",
        json.dumps([{"action": "buy", "code": "300750", "board": "电池"}]),
        json.dumps(
            {
                "executed_buys": [{"code": "300750", "pnl_pct": 3.5, "correct": True}],
                "summary": {"executed_count": 1, "executed_correct": 1},
            }
        ),
        json.dumps({"verified_count": 2}),
        json.dumps({"blocked_buy_count": 1}),
        "🟡 震荡",
        "测试分析",
    )

    class FakeConn:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchall(self):
            return [row]

        def close(self):
            return None

    import core.ai.context_builder as context_builder

    original = context_builder.RepoCompatConnection
    context_builder.RepoCompatConnection = FakeConn
    try:
        context = build_decision_history_context(limit=1)
    finally:
        context_builder.RepoCompatConnection = original

    assert len(context["items"]) == 1
    item = context["items"][0]
    assert item["correct_ratio"] == 1.0
    assert item["avg_pnl"] == 3.5
    assert item["executed_count"] == 1


def test_build_decision_reflection_filters_boards():
    from core.ai.context_builder import build_decision_reflection_context

    rows = [
        (
            "2025-11-03T10:00:00",
            "auto",
            json.dumps([{"action": "buy", "code": "300750", "board": "电池"}]),
            json.dumps(
                {
                    "executed_buys": [{"code": "300750", "pnl_pct": -2.0, "correct": False}],
                    "summary": {"executed_count": 1, "executed_correct": 0},
                }
            ),
            "{}",
            "{}",
            "🔴 弱势",
            "",
        ),
        (
            "2025-11-02T10:00:00",
            "auto",
            json.dumps([{"action": "buy", "code": "300308", "board": "芯片"}]),
            json.dumps(
                {
                    "executed_buys": [{"code": "300308", "pnl_pct": 5.0, "correct": True}],
                    "summary": {"executed_count": 1, "executed_correct": 1},
                }
            ),
            "{}",
            "{}",
            "🟢 强势",
            "",
        ),
    ]

    class FakeConn:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchall(self):
            return rows

        def close(self):
            return None

    import core.ai.context_builder as context_builder

    original = context_builder.RepoCompatConnection
    context_builder.RepoCompatConnection = FakeConn
    try:
        context = build_decision_reflection_context(boards=["电池"], limit=1)
    finally:
        context_builder.RepoCompatConnection = original

    assert len(context["reflection_lines"]) == 1
    assert "300750" not in context["reflection_lines"][0]
    assert "执行1笔买入" in context["reflection_lines"][0]


def test_multi_agent_cycle_passes_reflection_to_decide(monkeypatch):
    import desktop.agents as agents

    captured: dict = {}

    def fake_decide(*args, **kwargs):
        captured.update(kwargs)
        return '{"analysis":"ok","decisions":[]}'

    monkeypatch.setattr(
        agents.IntelligenceAgent,
        "gather",
        staticmethod(lambda boards: {"market": {"total": 3, "up": 2, "down": 1}, "events": [], "boards": []}),
    )
    monkeypatch.setattr(
        agents.AnalysisAgent,
        "analyze",
        staticmethod(lambda intel, boards, prefilled_candidates=None: {"market_regime": "🟡 震荡", "candidates": []}),
    )
    monkeypatch.setattr(
        agents.VerificationAgent,
        "verify",
        staticmethod(lambda analysis: {"verified_candidates": [], "questionable_candidates": [], "rejected_candidates": []}),
    )
    monkeypatch.setattr(agents.DecisionAgent, "decide", staticmethod(fake_decide))
    monkeypatch.setattr("desktop.ai_trader._build_portfolio_context", lambda mode: "portfolio context")
    monkeypatch.setattr(
        "core.ai.context_builder.build_decision_reflection_context_text",
        lambda boards=None, limit=None: "== 历史决策反思（已校准）==\n  2025-11-03；测试反思",
    )
    monkeypatch.setattr(
        "core.ai.context_builder.build_learning_feedback_context_text",
        lambda: "== 学习反馈 ==\n策略权重已更新",
    )

    result = agents.run_multi_agent_cycle(
        boards=["芯片"],
        mode="auto",
        execute=False,
        persist_memory=False,
    )

    assert "reflection_context" in captured
    assert "learning_context" in captured
    assert "历史决策反思" in captured["reflection_context"]
    assert "学习反馈" in captured["learning_context"]
    assert "历史决策反思" in result.get("decision_reflection_context", "")


def test_risk_agent_reports_warnings(monkeypatch):
    import desktop.agents as agents

    monkeypatch.setattr(
        "desktop.ai_portfolio.get_state",
        lambda mode: {"positions": list(range(10)) if mode == "auto" else [], "cash": 5000, "initial_capital": 1000000},
    )
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: {"var95": 120000, "drawdown": 0.12})

    report = agents.RiskAgent.assess_openclaw({"news_sentiment": {"ratio": 0.2}})

    assert report["ok"] is False
    assert report["warnings"]
    assert "VaR95" in report["summary"]


def test_risk_agent_flags_concentration_stop_loss_and_pending_buys(monkeypatch):
    import desktop.agents as agents

    def fake_state(mode):
        if mode == "auto":
            return {
                "positions": [
                    {
                        "code": "300750",
                        "entry_price": 100.0,
                        "shares": 500,
                        "stop_loss": 0,
                    },
                    {
                        "code": "002049",
                        "entry_price": 20.0,
                        "shares": 100,
                        "stop_loss": 18.0,
                    },
                ],
                "cash": 3000.0,
                "initial_capital": 100000.0,
            }
        return {"positions": [], "cash": 100000.0, "initial_capital": 100000.0}

    monkeypatch.setattr("desktop.ai_portfolio.get_state", fake_state)
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: {})

    report = agents.RiskAgent.assess_openclaw(
        {
            "decisions": [
                {"action": "buy", "code": "300750", "price": 50.0, "shares": 1000},
            ]
        }
    )

    assert report["ok"] is False
    assert report["metrics"]["auto"]["max_position_ratio"] > 35
    assert report["metrics"]["auto"]["stop_loss_missing"] == 1
    assert report["metrics"]["auto"]["duplicate_buy_codes"] == ["300750"]
    assert any("执行后现金" in warning for warning in report["warnings"])
    assert any("重复加仓" in warning for warning in report["warnings"])


def test_approval_agent_filters_rejected_buys(monkeypatch):
    import desktop.agents as agents

    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(
        agents,
        "get_unattended_trade_guard_config",
        lambda: {
            "enabled": False,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 50000.0,
            "max_single_buy_amount": 20000.0,
            "max_daily_buy_count": 3,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": [],
            "whitelist": [],
        },
    )
    monkeypatch.setattr(agents, "_record_unattended_trade_usage", lambda approved_buys: None)

    def fake_eval(**kwargs):
        return {
            "approved": kwargs["shares"] % 100 == 0 and kwargs["shares"] > 0,
            "message": "approved" if kwargs["shares"] % 100 == 0 and kwargs["shares"] > 0 else "bad lot",
            "policy": {"stage": "execute"},
            "normalized": kwargs,
        }

    monkeypatch.setattr("core.risk.approval_service.evaluate_trade_request", fake_eval)

    report = agents.ApprovalAgent.review_decisions(
        [
            {"action": "buy", "code": "300750", "name": "宁德时代", "shares": 200, "price": 9.5},
            {"action": "buy", "code": "600519", "name": "贵州茅台", "shares": 50, "price": 9.5},
            {"action": "hold", "code": "000001", "name": "平安银行"},
        ],
        mode="auto",
    )

    assert len(report["approved_decisions"]) == 2
    assert len(report["rejected_decisions"]) == 1
    assert report["rejected_decisions"][0]["code"] == "600519"


def test_approval_agent_unattended_guard_blocks_buy_by_default(monkeypatch):
    import desktop.agents as agents

    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: default)

    report = agents.ApprovalAgent.review_decisions(
        [{"action": "buy", "code": "300750", "name": "宁德时代", "shares": 100, "price": 10.0}],
        mode="auto",
    )

    assert not report["approved_decisions"]
    assert report["rejected_decisions"][0]["policy"]["stage"] == "unattended_trade_guard"
    assert "无人值守买入未开启" in report["rejected_decisions"][0]["message"]
    assert "仿真门禁未通过" in report["rejected_decisions"][0]["message"]


def test_approval_agent_unattended_guard_enforces_limits_and_blacklist(monkeypatch):
    import desktop.agents as agents

    saved = {}
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(
        agents,
        "get_kv_json",
        lambda key, default=None: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 2000.0,
            "max_single_buy_amount": 1500.0,
            "max_daily_buy_count": 1,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": ["600519"],
            "whitelist": [],
        }
        if key == agents._UNATTENDED_TRADE_GUARD_KEY
        else default,
    )
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: saved.__setitem__(key, value))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    report = agents.ApprovalAgent.review_decisions(
        [
            {"action": "buy", "code": "300750", "name": "宁德时代", "shares": 100, "price": 10.0},
            {"action": "buy", "code": "600519", "name": "贵州茅台", "shares": 100, "price": 10.0},
            {"action": "buy", "code": "000001", "name": "平安银行", "shares": 200, "price": 10.0},
        ],
        mode="auto",
    )

    assert len(report["approved_decisions"]) == 1
    assert len(report["rejected_decisions"]) == 2
    assert any("黑名单" in item["message"] for item in report["rejected_decisions"])
    assert any("每日买入次数" in item["message"] or "单票买入金额" in item["message"] for item in report["rejected_decisions"])
    assert saved[agents._UNATTENDED_TRADE_USAGE_KEY]["buy_count"] == 1


def test_approval_agent_unattended_guard_enforces_concentration_and_cooldown(monkeypatch):
    import desktop.agents as agents

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 100000.0,
            "max_single_buy_amount": 50000.0,
            "max_daily_buy_count": 10,
            "max_batch_buy_amount": 2500.0,
            "max_batch_buy_count": 2,
            "max_symbol_daily_buy_count": 1,
            "max_sector_daily_buy_amount": 2000.0,
            "max_sector_daily_buy_count": 1,
            "buy_cooldown_minutes": 0,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": [],
            "whitelist": [],
        },
        agents._UNATTENDED_TRADE_USAGE_KEY: {
            "date": __import__("datetime").date.today().isoformat(),
            "buy_count": 1,
            "buy_amount": 1000.0,
            "symbols": {"300750": {"count": 1, "amount": 1000.0}},
            "sectors": {"新能源": {"count": 1, "amount": 1000.0}},
            "last_buy_at": "",
        },
    }
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    report = agents.ApprovalAgent.review_decisions(
        [
            {"action": "buy", "code": "300750", "name": "宁德时代", "shares": 100, "price": 10.0, "sector": "新能源"},
            {"action": "buy", "code": "300014", "name": "亿纬锂能", "shares": 150, "price": 10.0, "sector": "新能源"},
            {"action": "buy", "code": "000001", "name": "平安银行", "shares": 300, "price": 10.0, "sector": "银行"},
        ],
        mode="auto",
    )

    messages = " | ".join(item["message"] for item in report["rejected_decisions"])
    assert not report["approved_decisions"]
    assert "单票每日无人值守买入次数" in messages
    assert "板块每日无人值守买入" in messages
    assert "单批无人值守买入金额" in messages


def test_approval_agent_unattended_guard_enforces_buy_cooldown(monkeypatch):
    import desktop.agents as agents

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 100000.0,
            "max_single_buy_amount": 50000.0,
            "max_daily_buy_count": 10,
            "max_batch_buy_amount": 100000.0,
            "max_batch_buy_count": 10,
            "max_symbol_daily_buy_count": 10,
            "max_sector_daily_buy_amount": 100000.0,
            "max_sector_daily_buy_count": 10,
            "buy_cooldown_minutes": 30,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": [],
            "whitelist": [],
        },
        agents._UNATTENDED_TRADE_USAGE_KEY: {
            "date": __import__("datetime").date.today().isoformat(),
            "buy_count": 1,
            "buy_amount": 1000.0,
            "symbols": {},
            "sectors": {},
            "last_buy_at": __import__("datetime").datetime.now().isoformat(),
        },
    }
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    report = agents.ApprovalAgent.review_decisions(
        [{"action": "buy", "code": "000001", "name": "平安银行", "shares": 100, "price": 10.0}],
        mode="auto",
    )

    assert "买入冷却" in report["rejected_decisions"][0]["message"]


def test_openclaw_guard_replay_captures_usage_without_persisting(monkeypatch):
    import desktop.agents as agents
    from infra.replay_openclaw_guard import build_replay_decisions, run_replay

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 100000.0,
            "max_single_buy_amount": 50000.0,
            "max_daily_buy_count": 10,
            "max_batch_buy_amount": 100000.0,
            "max_batch_buy_count": 10,
            "max_symbol_daily_buy_count": 10,
            "max_sector_daily_buy_amount": 100000.0,
            "max_sector_daily_buy_count": 10,
            "buy_cooldown_minutes": 0,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": [],
            "whitelist": [],
        },
    }
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    decisions = build_replay_decisions(
        [{"代码": "300750", "名称": "宁德时代", "价格": "10", "板块": "新能源", "建议买入": "强烈买入"}],
        default_shares=100,
        limit=10,
    )
    result = run_replay(decisions, mode="auto")

    assert result["approved_count"] == 1
    assert agents._UNATTENDED_TRADE_USAGE_KEY in result["captured_writes"]
    assert agents._UNATTENDED_TRADE_USAGE_KEY not in store


def test_openclaw_service_guard_replay_records_audit_history(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.agents as agents

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 100000.0,
            "max_single_buy_amount": 50000.0,
            "max_daily_buy_count": 10,
            "max_batch_buy_amount": 100000.0,
            "max_batch_buy_count": 10,
            "max_symbol_daily_buy_count": 10,
            "max_sector_daily_buy_amount": 100000.0,
            "max_sector_daily_buy_count": 10,
            "buy_cooldown_minutes": 0,
            "require_simulation_pass": False,
            "simulation_min_success_runs": 3,
            "blacklist": [],
            "whitelist": [],
        },
        "last_scan_results": [
            {"代码": "300750", "名称": "宁德时代", "价格": "10", "板块": "新能源", "建议买入": "强烈买入"}
        ],
    }
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    result = openclaw_service.run_unattended_trade_guard_replay({"limit": 10, "shares": 100})
    replay = openclaw_service.get_unattended_trade_guard_replay_history()

    assert result["ok"] is True
    assert result["approved_count"] == 1
    assert replay["last"]["approved_count"] == 1
    assert replay["history"][0]["source"] == "last_scan_results"
    assert agents._UNATTENDED_TRADE_USAGE_KEY not in store


def test_openclaw_historical_replay_report_summarizes_full_chain(monkeypatch):
    import core.application.openclaw_service as openclaw_service

    store = {
        "openclaw_daemon_run_history": [
            {"status": "success", "summary": "ok"},
            {"status": "warning", "summary": "no execution"},
            {"status": "error", "summary": "gateway down"},
        ],
        "openclaw_guard_replay_last": {"approved_count": 1, "rejected_count": 1},
        "openclaw_guard_replay_history": [{"approved_count": 1, "rejected_count": 1}],
    }

    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(
        openclaw_service,
        "get_unattended_trade_guard",
        lambda: {
            "config": {"enabled": True, "unattended_buy_enabled": False},
            "usage": {},
            "simulation": {"passed": True, "consecutive_success_runs": 3, "required_success_runs": 3},
            "replay": {"last": {"approved_count": 1}, "history": [{"approved_count": 1}]},
        },
    )
    monkeypatch.setattr(
        openclaw_service,
        "run_unattended_trade_guard_replay",
        lambda payload: {"ok": True, "input_count": 2, "approved_count": 1, "rejected_count": 1, "skipped_count": 0},
    )
    monkeypatch.setattr("desktop.agents.get_decision_accuracy", lambda limit=30: {"accuracy": 66.7, "total": 3})
    monkeypatch.setattr("desktop.trend_verify.get_accuracy_stats", lambda: {"accuracy": 50.0, "total": 2})
    monkeypatch.setattr("desktop.trend_verify.get_failure_summary", lambda limit=100, since_days=180: {"items": []})

    report = openclaw_service.build_openclaw_historical_replay_report({"limit": 3, "include_guard_replay": True})

    assert report["daemon"]["status_counts"]["success"] == 1
    assert report["daemon"]["status_counts"]["warning"] == 1
    assert report["daemon"]["status_counts"]["error"] == 1
    assert report["daemon"]["success_rate"] == 33.33
    assert report["trade_guard"]["replay_result"]["rejected_count"] == 1
    assert report["decision_accuracy"]["accuracy"] == 66.7
    assert any(item["code"] == "historical_errors" for item in report["findings"])


def test_approval_agent_requires_simulation_gate_before_unattended_buy(monkeypatch):
    import desktop.agents as agents

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "unattended_buy_enabled": True,
            "allow_sell_when_buy_disabled": True,
            "max_daily_buy_amount": 50000.0,
            "max_single_buy_amount": 20000.0,
            "max_daily_buy_count": 3,
            "require_simulation_pass": True,
            "simulation_min_success_runs": 2,
            "blacklist": [],
            "whitelist": [],
        },
        agents._UNATTENDED_SIMULATION_STATE_KEY: {
            "passed": False,
            "consecutive_success_runs": 1,
            "required_success_runs": 2,
        },
    }
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 10.0)
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(
        "core.risk.approval_service.evaluate_trade_request",
        lambda **kwargs: {"approved": True, "message": "approved", "policy": {}, "normalized": kwargs},
    )

    rejected = agents.ApprovalAgent.review_decisions(
        [{"action": "buy", "code": "300750", "name": "宁德时代", "shares": 100, "price": 10.0}],
        mode="auto",
    )
    store[agents._UNATTENDED_SIMULATION_STATE_KEY] = agents.record_unattended_trade_guard_simulation("success", "ok")
    approved = agents.ApprovalAgent.review_decisions(
        [{"action": "buy", "code": "300750", "name": "宁德时代", "shares": 100, "price": 10.0}],
        mode="auto",
    )

    assert "仿真门禁未通过" in rejected["rejected_decisions"][0]["message"]
    assert store[agents._UNATTENDED_SIMULATION_STATE_KEY]["passed"] is True
    assert len(approved["approved_decisions"]) == 1


def test_unattended_trade_guard_simulation_keeps_gate_on_transient_gateway_error(monkeypatch):
    import desktop.agents as agents

    store = {
        agents._UNATTENDED_TRADE_GUARD_KEY: {
            "enabled": True,
            "simulation_min_success_runs": 3,
        },
        agents._UNATTENDED_SIMULATION_STATE_KEY: {
            "passed": True,
            "consecutive_success_runs": 3,
            "required_success_runs": 3,
            "last_status": "success",
        },
    }
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))

    transient = agents.record_unattended_trade_guard_simulation("error", "OpenClaw后台执行异常: gateway down")
    real_error = agents.record_unattended_trade_guard_simulation("error", "OpenClaw后台执行异常: invalid decision")

    assert transient["passed"] is True
    assert transient["consecutive_success_runs"] == 3
    assert transient["last_status"] == "transient_error"
    assert real_error["passed"] is False
    assert real_error["consecutive_success_runs"] == 0


def test_coordinator_agent_routes_execute_stage_to_observe_only():
    from desktop.agents import CoordinatorAgent

    route = CoordinatorAgent.route_stage(
        "s6",
        {
            "decisions": [
                {"action": "buy", "code": "600519"},
                {"action": "buy", "code": "300750"},
            ],
            "decision_guardrails": {
                "blocked_buys": [{"code": "600519"}, {"code": "300750"}],
            },
            "news_sentiment": {"ratio": 0.4},
            "risk_summary": "✅ 全部通过",
        },
    )

    assert route["run"] is False
    assert route["mode"] == "observe_only"


def test_coordinator_agent_inspects_stage_readiness_for_orchestration():
    from desktop.agents import CoordinatorAgent

    hydrate = CoordinatorAgent.inspect_stage_readiness("s3", {"candidates": []})
    rerun = CoordinatorAgent.inspect_stage_readiness(
        "s4",
        {
            "candidates": [{"code": "300750"}],
            "decisions": [],
        },
    )
    execution = CoordinatorAgent.inspect_stage_readiness(
        "s6",
        {
            "decisions": [{"action": "buy", "code": "300750"}],
        },
    )
    learning = CoordinatorAgent.inspect_stage_readiness(
        "s9",
        {
            "errors": ["s1 failed", "s2 failed"],
        },
    )

    assert hydrate["mode"] == "hydrate_candidates"
    assert hydrate["actions"][0]["type"] == "hydrate_last_scan_results"
    assert rerun["ready"] is False
    assert rerun["actions"][0]["type"] == "recommend_rerun"
    assert execution["mode"] == "require_risk_check"
    assert execution["actions"][0]["target"] == "s5"
    assert learning["mode"] == "degraded_learning"


def test_coordinator_agent_routes_learning_stage_skip_on_many_errors():
    from desktop.agents import CoordinatorAgent

    route = CoordinatorAgent.route_stage(
        "s9",
        {
            "errors": [
                "Step 1 failed",
                "Step 2 failed",
                "Step 3 failed",
            ]
        },
    )

    assert route["run"] is False
    assert route["mode"] == "skip"


def test_coordinator_agent_retries_retryable_stage_once():
    from desktop.agents import CoordinatorAgent

    results = {"errors": []}
    first = CoordinatorAgent.recover_stage_failure("s1", "感知采集", "network down", results)
    second = CoordinatorAgent.recover_stage_failure("s1", "感知采集", "network down", results)
    execute = CoordinatorAgent.recover_stage_failure("s6", "执行交易", "broker down", {"errors": []})

    assert first["retry"] is True
    assert first["mode"] == "retry_once"
    assert second["retry"] is False
    assert execute["mode"] == "manual_review"


def test_coordinator_agent_routes_execute_stage_sell_only_when_risk_warn():
    from desktop.agents import CoordinatorAgent

    route = CoordinatorAgent.route_stage(
        "s6",
        {
            "decisions": [
                {"action": "buy", "code": "300750"},
                {"action": "sell", "code": "000001"},
            ],
            "risk_summary": "⚠ 回撤12%超10%",
            "news_sentiment": {"ratio": 0.5},
        },
    )

    assert route["run"] is True
    assert route["mode"] == "sell_only"
    assert route["execution_policy"]["allow_buy"] is False


def test_coordinator_policy_config_controls_limit_buy(monkeypatch):
    import desktop.agents as agents
    from desktop.agents import CoordinatorAgent

    store = {}
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))
    agents.set_coordinator_policy_config(
        {
            "sell_only_sentiment_ratio": 0.2,
            "limit_buy_sentiment_ratio": 0.45,
            "limit_buy_max_count": 2,
        }
    )

    route = CoordinatorAgent.route_stage(
        "s6",
        {
            "decisions": [
                {"action": "buy", "code": "300750"},
                {"action": "buy", "code": "600519"},
                {"action": "sell", "code": "000001"},
            ],
            "risk_summary": "✅ 全部通过",
            "news_sentiment": {"ratio": 0.4},
        },
    )

    assert route["mode"] == "limit_buy"
    assert route["execution_policy"]["max_buy_count"] == 2


def test_coordinator_policy_adapts_from_learning(monkeypatch):
    import desktop.agents as agents

    store = {}
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    agents.set_coordinator_policy_config(
        {
            "sell_only_sentiment_ratio": 0.25,
            "limit_buy_sentiment_ratio": 0.35,
            "limit_buy_max_count": 2,
            "learning_min_samples": 2,
        }
    )

    result = agents.adapt_coordinator_policy_from_learning(
        {
            "coordinator_effectiveness": {
                "routed_blocked_count": 2,
                "avoided_losses": 2,
                "missed_gains": 0,
                "avoided_loss_rate": 100.0,
            }
        }
    )

    assert result["changed"] is True
    assert result["config"]["sell_only_sentiment_ratio"] > 0.25
    assert result["config"]["limit_buy_sentiment_ratio"] > 0.35
    assert result["config"]["limit_buy_max_count"] == 1


def test_execution_policy_filters_buys_with_limit():
    from desktop.openclaw_engine import _apply_execution_policy

    payload = _apply_execution_policy(
        [
            {"action": "buy", "code": "300750"},
            {"action": "buy", "code": "600519"},
            {"action": "sell", "code": "000001"},
        ],
        {
            "allow_buy": True,
            "allow_sell": True,
            "allow_hold": True,
            "max_buy_count": 1,
        },
    )

    assert len(payload["decisions"]) == 2
    assert payload["decisions"][0]["code"] == "300750"
    assert payload["decisions"][1]["code"] == "000001"
    assert payload["blocked"][0]["code"] == "600519"


def test_openclaw_push_report_formats_truncated_decisions():
    from datetime import date

    from desktop.openclaw_engine import build_openclaw_push_report

    decisions = [
        {
            "action": "sell",
            "code": f"30000{i}",
            "name": f"测试{i}",
            "reason": "持仓超限且亏损较多，表现不佳，为买入优质股腾出资金并降低组合风险",
        }
        for i in range(1, 10)
    ]

    report = build_openclaw_push_report({"decisions": decisions}, report_date=date(2026, 4, 27))
    content = report["content"]

    assert content.startswith("时间: 2026-04-27")
    assert "🦀 OpenClaw 智能报告" not in content
    assert "🤖 AI决策（共 9 条）" in content
    assert "　　(8) 卖出 300008 测试8" in content
    assert "　　... 及其他 1 条决策；" in content
    assert "..." in content
    assert all(line.endswith("；") for line in content.splitlines() if line.startswith("　　("))


def test_execute_sell_signals_across_modes_sells_matching_holdings(monkeypatch):
    import desktop.ai_trader as ai_trader

    states = {
        "auto": {"positions": [{"code": "300750", "shares": 100}]},
        "custom": {"positions": [{"code": "300750", "shares": 100}]},
        "quantum": {"positions": [{"code": "300750", "shares": 100}]},
    }
    sold = []
    monkeypatch.setattr(ai_trader, "get_state", lambda mode: states.get(mode, {"positions": []}))
    monkeypatch.setattr(ai_trader, "_get_real_price", lambda code: 10.0)
    monkeypatch.setattr(
        ai_trader,
        "sell",
        lambda mode, code, price, reason="": sold.append((mode, code, price, reason)) or f"[{mode}] sold {code}",
    )

    result = ai_trader.execute_sell_signals_across_modes(
        [{"action": "sell", "code": "300750", "reason": "趋势转弱"}],
        modes=("auto", "custom", "quantum"),
    )

    assert result == ["[auto] sold 300750", "[custom] sold 300750", "[quantum] sold 300750"]
    assert [item[0] for item in sold] == ["auto", "custom", "quantum"]
    assert all("趋势转弱" in item[3] for item in sold)


def test_auto_sell_executes_sell_signals_for_strategy_portfolios(monkeypatch):
    import desktop.auto_sell as auto_sell

    modes = ["full_auto", "auto", "manual", "custom", "quantum"]
    monkeypatch.setattr(auto_sell, "update_atr_stops", lambda: [])
    monkeypatch.setattr(auto_sell, "check_add_position_signals", lambda mode="full_auto": [])
    monkeypatch.setattr(
        auto_sell,
        "check_sell_signals",
        lambda mode: [
            {
                "mode": mode,
                "code": f"30000{idx}",
                "name": mode,
                "rule": "测试卖出",
                "reason": "卖出信号",
                "action": "sell_all",
                "price": 10.0,
                "pnl_pct": -3.0,
            }
        ]
        if (idx := modes.index(mode) + 1)
        else [],
    )
    monkeypatch.setattr("desktop.ai_portfolio.check_trading_time", lambda: None)
    monkeypatch.setattr(
        "desktop.ai_portfolio.sell",
        lambda mode, code, price, reason="": f"[{mode}] 卖出 {code}",
    )
    monkeypatch.setattr("signal_push.push_signal", lambda title, content: {"wecom": True})

    result = auto_sell.execute_auto_sell()

    assert len(result["executed"]) == 5
    assert not result["suggested"]
    assert any("[auto] 卖出" in item for item in result["executed"])
    assert any("[manual] 卖出" in item for item in result["executed"])
    assert any("[custom] 卖出" in item for item in result["executed"])
    assert any("[quantum] 卖出" in item for item in result["executed"])


def test_ai_decision_execution_blocks_low_score_buys(monkeypatch):
    import desktop.ai_trader as ai_trader

    monkeypatch.setattr(
        ai_trader,
        "_lookup_candidate_meta",
        lambda code: {
            "score": 60,
            "board": "人工智能",
            "strategy_views": "SEPA趋势:看多 动量:中性",
            "sepa_view": "看多",
            "momentum_view": "中性",
        },
    )
    monkeypatch.setattr(ai_trader, "_daily_trade_counts", lambda mode: (0, 0))
    monkeypatch.setattr(
        "desktop.market_state.get_market_state_snapshot",
        lambda: {"state": "neutral", "sector_bottom3": [], "reason": ""},
    )

    result = ai_trader.execute_ai_decisions(
        [
            {
                "action": "buy",
                "code": "300001",
                "name": "测试股",
                "price": 10,
                "shares": 100,
                "score": 60,
                "reason": "综合60分，测试买入",
            }
        ],
        mode="auto",
    )

    assert result == ["风控拦截买入 300001: 综合评分60低于当前市场门槛80"]


def test_audit_event_models_roundtrip():
    from core.audit.event_models import create_system_event, event_from_log_row

    event = create_system_event(
        source="approval",
        category="trade",
        title="审批执行",
        detail="执行买入",
        level="info",
        trace_id="trace-123",
        decision_id="decision-abc",
        metadata={"mode": "auto"},
        timestamp="2026-01-01T00:00:00",
    )
    row = event.to_log_row()
    parsed = event_from_log_row(row)

    assert parsed["source"] == "approval"
    assert parsed["category"] == "trade"
    assert parsed["detail"] == "执行买入"
    assert parsed["trace_id"] == "trace-123"
    assert parsed["decision_id"] == "decision-abc"
    assert parsed["metadata"]["mode"] == "auto"


def test_structured_logging_record_shape():
    from core.observability.structured_logging import build_structured_record

    record = build_structured_record(
        "trade.approval.executed",
        level="warning",
        trace_id="trace-001",
        decision_id="decision-001",
        source="approval",
        category="trade",
        metadata={"mode": "auto"},
        code="600519",
    )
    assert record["event"] == "trade.approval.executed"
    assert record["level"] == "WARNING"
    assert record["trace_id"] == "trace-001"
    assert record["decision_id"] == "decision-001"
    assert record["source"] == "approval"
    assert record["category"] == "trade"
    assert record["metadata"]["mode"] == "auto"
    assert record["code"] == "600519"


def test_metrics_and_tracing_skeleton_roundtrip():
    from core.observability.metrics import (
        get_metrics_snapshot,
        inc_counter,
        observe_histogram,
        reset_metrics,
    )
    from core.observability.tracing import (
        build_traceparent,
        create_trace_id,
        export_otel_traces,
        finish_span,
        parse_traceparent,
        start_span,
    )

    reset_metrics()
    trace_id = create_trace_id("smoke")
    span = start_span("test.span", trace_id=trace_id, metadata={"phase": "m4-07"})
    inc_counter("unit_test_counter_total", labels={"phase": "m4_07"})
    observe_histogram("unit_test_duration_ms", 12.5, labels={"phase": "m4_07"})
    finished = finish_span(span, status="ok")
    snapshot = get_metrics_snapshot()

    assert trace_id.startswith("smoke-")
    assert finished["status"] == "ok"
    assert finished["duration_ms"] >= 0.0
    traceparent = build_traceparent("a" * 32, "b" * 16, sampled=True)
    parsed = parse_traceparent(traceparent)
    assert parsed["sampled"] is True
    assert len(export_otel_traces(limit=10).get("resource_spans", [])) >= 1
    assert snapshot["counters"]["unit_test_counter_total|phase=m4_07"] == 1.0
    assert snapshot["histograms"]["unit_test_duration_ms|phase=m4_07"]["count"] == 1


def test_trace_index_and_lookup_models():
    from core.observability.tracing import (
        build_trace_graph,
        get_trace_index,
        get_trace_spans,
        parse_traceparent,
        start_span,
        finish_span,
        summarize_trace,
    )

    root = start_span("unit.trace.root")
    child = start_span("unit.trace.child", traceparent=root.get("traceparent", ""))
    finish_span(child, status="ok")
    finished_root = finish_span(root, status="ok")
    trace_hex = parse_traceparent(root.get("traceparent", "")).get("trace_id_hex", "")

    items = get_trace_spans(trace_hex, limit=20)
    summary = summarize_trace(items)
    graph = build_trace_graph(items)
    index = get_trace_index(limit=200)

    assert trace_hex
    assert len(items) >= 2
    assert summary["span_count"] >= 2
    assert graph["node_count"] >= 2
    assert "unit.trace.root" in summary["root_span_names"]
    assert any(entry.get("trace_id_hex", "") == trace_hex for entry in index)
    assert finished_root.get("status") == "ok"


def test_observability_alerts_triggered_by_thresholds():
    from core.observability.alerts import evaluate_metrics_alerts

    payload = evaluate_metrics_alerts(
        {
            "counters": {"trade_approval_rejected_total|action=buy,mode=auto": 3.0},
            "histograms": {"trade_approval_duration_ms|action=buy,status=executed": {"max": 4200.0, "avg": 1200.0}},
        },
        rejected_threshold=2,
        duration_ms_threshold=3000.0,
    )
    assert payload["status"] == "alerting"
    assert len(payload["alerts"]) >= 1
    assert payload["summary"]["approval_rejected_total"] == 3.0


def test_observability_exporters_shapes():
    from core.observability.exporters import export_otel_metrics, export_prometheus_text

    snapshot = {
        "counters": {"trade_approval_rejected_total|action=buy,mode=auto": 2.0},
        "histograms": {"trade_approval_duration_ms|action=buy,status=executed": {"count": 1, "sum": 120.0, "min": 120.0, "max": 120.0, "avg": 120.0}},
    }
    prom = export_prometheus_text(snapshot)
    otel = export_otel_metrics(snapshot)

    assert "trade_approval_rejected_total" in prom
    assert 'action="buy"' in prom
    assert isinstance(otel.get("resource_metrics"), list)
    assert otel["resource_metrics"][0]["scope_metrics"][0]["metrics"]


def test_observability_trend_and_policy_models():
    from core.observability.alert_policy import build_alert_policy
    from core.observability.alert_dispatcher import dispatch_routed_alerts, get_dispatch_receipts
    from core.observability.alert_router import build_alert_routing_policy, route_alerts
    from core.observability.alerts import evaluate_observability_alerts
    from core.observability.otel_collector import push_otel_collector, reset_collector_state
    from core.observability.trends import build_event_trend_report

    events = [
        {
            "timestamp": "2026-04-10T01:00:00+00:00",
            "source": "approval",
            "category": "trade",
            "title": "交易审批拒绝 BUY 600519",
            "level": "warning",
        }
    ]
    trend = build_event_trend_report(events, window_days=2)
    policy = build_alert_policy(
        policy_name="test-policy",
        rejected_threshold=1,
        duration_ms_threshold=10.0,
        event_error_threshold=1,
        approval_rejected_daily_threshold=1,
    )
    payload = evaluate_observability_alerts(
        {"counters": {"trade_approval_rejected_total": 2.0}, "histograms": {}},
        trend,
        policy=policy,
    )

    assert trend["window_days"] == 2
    assert policy["name"] == "test-policy"
    assert payload["policy"]["name"] == "test-policy"
    assert payload["status"] == "alerting"
    routing_policy = build_alert_routing_policy(
        policy_name="test-routing",
        suppress_seconds=10,
        escalate_after=2,
        default_channels=["in_app_feed"],
        escalation_channels=["wechat_personal"],
    )
    routed = route_alerts(
        payload["alerts"],
        routing_policy=routing_policy,
        notifiers=[
            {"channels": ["in_app_feed"]},
            {"channels": ["wechat_personal"]},
        ],
        dry_run=True,
    )
    assert routed["policy"]["name"] == "test-routing"
    assert routed["decision_count"] >= 1
    dispatched = dispatch_routed_alerts(payload["alerts"], routed, dry_run=True, receipt_limit=200)
    assert dispatched["dispatch_count"] >= 1
    assert isinstance(get_dispatch_receipts(limit=5), list)
    reset_collector_state()
    pushed = push_otel_collector(
        endpoint="",
        metrics_snapshot={"counters": {}, "histograms": {}},
        signals=("metrics",),
        dry_run=True,
    )
    assert pushed["status"] == "ok"


def test_operational_health_report_summarizes_oncall_signals(monkeypatch):
    import api_server.auth as auth
    import core.application.openclaw_service as openclaw_service
    import core.application.ops_service as ops_service
    import desktop.daemon_scheduler as daemon_scheduler

    monkeypatch.setattr(
        daemon_scheduler,
        "get_daemon_runtime_status",
        lambda: {
            "active": True,
            "leader_pid": 123,
            "heartbeat_age_seconds": 5,
            "next_task": {"task_key": "openclaw_pipeline", "task_name": "OpenClaw", "scheduled_at": "2026-04-27 10:25"},
            "push_status": {"last_result": "success", "count_today": 1, "last_success_at": "2026-04-27T09:00:00"},
            "duplicate_lock": {"detected": False},
        },
    )
    monkeypatch.setattr(
        openclaw_service,
        "get_openclaw_daemon_status",
        lambda: {
            "openclaw": {
                "readiness": {"ready": True, "status": "ready", "summary": "就绪", "errors": [], "warnings": []},
                "last_run": {"status": "success", "summary": "steps=9"},
                "alert_state": {"consecutive_errors": 0},
            }
        },
    )
    monkeypatch.setattr(
        openclaw_service,
        "get_unattended_trade_guard",
        lambda: {"simulation": {"passed": True, "consecutive_success_runs": 3, "required_success_runs": 3}},
    )
    monkeypatch.setattr(auth, "get_auth_security_status", lambda: {"status": "ready", "findings": []})
    monkeypatch.setattr(ops_service, "get_recent_system_events", lambda limit: [{"level": "info"}])
    monkeypatch.setattr(ops_service, "get_recent_task_runs", lambda limit: [{"task": "openclaw"}])
    monkeypatch.setattr(
        ops_service,
        "get_metrics_snapshot",
        lambda: {"counters": {"system_events_total": 1.0}, "histograms": {}},
    )

    report = ops_service.build_operational_health_report(limit=10)

    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["signals"]["daemon"]["active"] is True
    assert report["signals"]["openclaw"]["simulation"]["passed"] is True
    assert report["signals"]["metrics"]["counter_count"] == 1


def test_daemon_health_allows_active_daemon_with_no_pending_task():
    from core.application.ops_service import build_daemon_health_report

    report = build_daemon_health_report(
        {
            "active": True,
            "leader_pid": 123,
            "next_task": {},
            "push_status": {"last_result": "skipped_no_channel"},
            "duplicate_lock": {"detected": False},
        }
    )

    checks = {item["name"]: item for item in report["checks"]}
    assert report["ok"] is True
    assert checks["next_task"]["ok"] is True


def test_operational_health_report_flags_security_and_simulation(monkeypatch):
    import api_server.auth as auth
    import core.application.openclaw_service as openclaw_service
    import core.application.ops_service as ops_service
    import desktop.daemon_scheduler as daemon_scheduler

    monkeypatch.setattr(
        daemon_scheduler,
        "get_daemon_runtime_status",
        lambda: {
            "active": False,
            "leader_pid": 0,
            "next_task": {},
            "push_status": {"last_result": "failed"},
            "duplicate_lock": {"detected": False},
        },
    )
    monkeypatch.setattr(
        openclaw_service,
        "get_openclaw_daemon_status",
        lambda: {
            "openclaw": {
                "readiness": {"ready": False, "summary": "未就绪", "errors": ["daemon 未运行"], "warnings": []},
                "last_run": {"status": "error", "summary": "gateway down"},
                "alert_state": {"consecutive_errors": 1},
            }
        },
    )
    monkeypatch.setattr(
        openclaw_service,
        "get_unattended_trade_guard",
        lambda: {"simulation": {"passed": False, "consecutive_success_runs": 0, "required_success_runs": 3}},
    )
    monkeypatch.setattr(
        auth,
        "get_auth_security_status",
        lambda: {
            "status": "warning",
            "findings": [{"level": "warning", "code": "default_admin_password", "message": "默认密码"}],
        },
    )
    monkeypatch.setattr(ops_service, "get_recent_system_events", lambda limit: [{"level": "error"}])
    monkeypatch.setattr(ops_service, "get_recent_task_runs", lambda limit: [])
    monkeypatch.setattr(ops_service, "get_metrics_snapshot", lambda: {"counters": {}, "histograms": {}})

    report = ops_service.build_operational_health_report(limit=10)
    codes = {item["code"] for item in report["findings"]}

    assert report["status"] == "error"
    assert "daemon_unhealthy" in codes
    assert "openclaw_not_ready" in codes
    assert "simulation_gate_not_passed" in codes
    assert "security_default_admin_password" in codes
    assert report["runbook"]


def test_decision_models_normalize_payload():
    from core.ai.decision_models import normalize_decision_payload

    payload = normalize_decision_payload(
        {
            "action": "BUY",
            "code": "600519",
            "name": "贵州茅台",
            "price": 123.4,
            "shares": 300,
            "reason": "signal",
            "score": 88,
            "board": "白酒",
        }
    )

    result = payload.to_dict()
    assert result["action"] == "buy"
    assert result["code"] == "600519"
    assert result["score"] == 88
    assert result["board"] == "白酒"


def test_decision_engine_parses_json_response():
    from core.ai.decision_engine import parse_ai_decision_response

    response = """
    分析如下
    {
      "analysis": "市场偏强",
      "decisions": [
        {"action": "BUY", "code": "600519", "name": "贵州茅台", "price": 123.4, "shares": 300, "reason": "强势"}
      ]
    }
    """

    parsed = parse_ai_decision_response(response)
    assert parsed["parse_status"] == "json"
    assert parsed["analysis"] == "市场偏强"
    assert parsed["decisions"][0]["action"] == "buy"
    assert parsed["decisions"][0]["code"] == "600519"


def test_decision_engine_handles_invalid_json():
    from core.ai.decision_engine import parse_ai_decision_response

    parsed = parse_ai_decision_response("not-json-response")
    assert parsed["parse_status"] == "plain_text"
    assert parsed["decisions"] == []


def test_risk_approval_rejects_invalid_buy(monkeypatch):
    from core.risk import approval_service

    class FakeRiskManager:
        def check_new_order(self, side, symbol, volume, price):
            class Result:
                ok = True
                reason = ""

            return Result()

    monkeypatch.setattr(approval_service, "RiskManager", FakeRiskManager)

    result = approval_service.evaluate_trade_request(
        mode="auto",
        action="BUY",
        code="600519",
        name="贵州茅台",
        price=123.4,
        shares=250,
        reason="invalid lot",
    )

    assert result["approved"] is False
    assert "multiple of 100" in result["message"]


def test_risk_approval_accepts_valid_sell(monkeypatch):
    from core.risk import approval_service

    class FakeRiskManager:
        def check_new_order(self, side, symbol, volume, price):
            class Result:
                ok = True
                reason = ""

            return Result()

    monkeypatch.setattr(approval_service, "RiskManager", FakeRiskManager)

    result = approval_service.evaluate_trade_request(
        mode="auto",
        action="SELL",
        code="600519",
        name="贵州茅台",
        price=123.4,
        shares=0,
        reason="take profit",
    )

    assert result["approved"] is True
    assert result["policy"]["stage"] == "execute"


def test_registry_lists_have_expected_shape():
    from core.registry import (
        list_registered_agents,
        list_registered_notifiers,
        list_registered_providers,
        list_registered_strategies,
        list_registered_workflows,
    )

    providers = list_registered_providers()
    strategies = list_registered_strategies()
    notifiers = list_registered_notifiers()
    workflows = list_registered_workflows()
    agents = list_registered_agents()

    assert providers
    assert strategies
    assert notifiers
    assert workflows
    assert agents
    assert all("key" in item for item in providers)
    assert all("capabilities" in item for item in providers)
    assert all("key" in item and "name" in item for item in strategies)
    assert all("key" in item and "channels" in item for item in notifiers)
    assert all("key" in item and "handler_path" in item for item in workflows)
    assert all("key" in item and "entrypoint" in item for item in agents)
    assert any(item.get("key") == "coordinator" for item in agents)
    assert any(item.get("key") == "risk" for item in agents)
    assert any(item.get("key") == "approval" for item in agents)


def test_registry_overview_contains_observability_meta():
    from core.application.registry_service import get_registry_overview

    payload = get_registry_overview()
    meta = payload.get("meta", {})
    assert payload.get("provider_count", 0) > 0
    assert payload.get("strategy_count", 0) > 0
    assert payload.get("notifier_count", 0) > 0
    assert payload.get("workflow_count", 0) > 0
    assert payload.get("agent_count", 0) > 0
    assert "T" in str(meta.get("refreshed_at", ""))
    assert "T" in str(meta.get("expires_at", ""))
    assert meta.get("source") == "core.registry"
    assert meta.get("agent_source") == "core.registry.agent_registry"
    assert len(str(meta.get("change_token", ""))) >= 20
    assert isinstance(meta.get("cache_ttl_seconds"), int)
    assert isinstance(meta.get("cached"), bool)


def test_registry_overview_cache_meta(monkeypatch):
    import core.application.registry_service as registry_service

    monkeypatch.setenv("FINQUANTA_REGISTRY_CACHE_TTL", "60")
    registry_service._REGISTRY_CACHE.clear()

    first = registry_service.get_registry_overview(force_refresh=True)
    second = registry_service.get_registry_overview()

    assert first.get("meta", {}).get("cached") is False
    assert second.get("meta", {}).get("cached") is True
    assert first.get("meta", {}).get("change_token") == second.get("meta", {}).get("change_token")
    assert first.get("meta", {}).get("refreshed_at") == second.get("meta", {}).get("refreshed_at")


def test_api_routes_include_registry_endpoints():
    from api_server.main import app

    route_paths = {route.path for route in app.routes}
    assert "/api/ops/health" in route_paths
    assert "/api/registry" in route_paths
    assert "/api/registry/providers" in route_paths
    assert "/api/registry/strategies" in route_paths
    assert "/api/registry/notifiers" in route_paths
    assert "/api/registry/workflows" in route_paths
    assert "/api/registry/agents" in route_paths
    assert "/api/observability/metrics" in route_paths
    assert "/api/observability/metrics/prometheus" in route_paths
    assert "/api/observability/metrics/otel" in route_paths
    assert "/api/observability/traces" in route_paths
    assert "/api/observability/traces/index" in route_paths
    assert "/api/observability/traces/trace/{trace_id}" in route_paths
    assert "/api/observability/traces/otel" in route_paths
    assert "/api/observability/traces/config" in route_paths
    assert "/api/observability/traces/backends/presets" in route_paths
    assert "/api/observability/dashboard/template" in route_paths
    assert "/api/observability/dashboard/panel-input" in route_paths
    assert "/api/observability/collector/state" in route_paths
    assert "/api/observability/collector/push" in route_paths
    assert "/api/observability/trace/context" in route_paths
    assert "/api/observability/trends" in route_paths
    assert "/api/observability/alerts/policy" in route_paths
    assert "/api/observability/alerts/routing" in route_paths
    assert "/api/observability/alerts/route" in route_paths
    assert "/api/observability/alerts/routing/state" in route_paths
    assert "/api/observability/alerts/dispatch" in route_paths
    assert "/api/observability/alerts/dispatch/receipts" in route_paths
    assert "/api/observability/alerts" in route_paths
    assert "/api/admin/security-check" in route_paths
    assert "/api/admin/production-security-report" in route_paths
    assert "/api/admin/tokens/revoke-others" in route_paths
    assert "/api/sync/export" in route_paths
    assert "/api/sync/import" in route_paths
    assert "/api/trend-verify/records" in route_paths
    assert "/api/trend-verify/stats" in route_paths
    assert "/api/trend-verify/failure-summary" in route_paths
    assert "/api/trend-verify/batch-analyze" in route_paths
    assert "/api/openclaw/daemon/status" in route_paths
    assert "/api/admin/tokens/cleanup-expired" in route_paths
    assert "/api/openclaw/config-audit" in route_paths
    assert "/api/openclaw/config-audit/rollback" in route_paths
    assert "/api/openclaw/daemon/alert-policy" in route_paths
    assert "/api/openclaw/daemon/alert-policy/reset" in route_paths
    assert "/api/openclaw/coordinator-policy" in route_paths
    assert "/api/openclaw/coordinator-policy/reset" in route_paths
    assert "/api/openclaw/unattended-trade-guard" in route_paths
    assert "/api/openclaw/unattended-trade-guard/reset" in route_paths
    assert "/api/openclaw/unattended-trade-guard/replay" in route_paths
    assert "/api/openclaw/replay/history" in route_paths


def test_openclaw_admin_permission_is_admin_only():
    from api_server.auth import ROLE_PERMISSIONS, has_permission

    admin = {"permissions": sorted(ROLE_PERMISSIONS["admin"])}
    operator = {"permissions": sorted(ROLE_PERMISSIONS["operator"])}
    viewer = {"permissions": sorted(ROLE_PERMISSIONS["viewer"])}

    assert has_permission(admin, "openclaw:admin") is True
    assert has_permission(operator, "openclaw:run") is True
    assert has_permission(operator, "openclaw:admin") is False
    assert has_permission(viewer, "openclaw:admin") is False


def test_openclaw_config_mutation_requires_admin_permission(monkeypatch):
    from fastapi import HTTPException

    from api_server import main as api_main
    from api_server.schemas import (
        CoordinatorPolicyRequest,
        OpenClawGuardReplayRequest,
        OpenClawHistoricalReplayRequest,
        TriggerRequest,
    )

    operator = {"username": "op", "role": "operator", "permissions": ["openclaw:run"]}
    monkeypatch.setattr(api_main, "require_user", lambda authorization: operator)
    monkeypatch.setattr(api_main, "run_unattended_trade_guard_replay", lambda payload: {"ok": True})
    monkeypatch.setattr(api_main, "build_openclaw_historical_replay_report", lambda payload: {"verdict": "ready"})

    try:
        api_main.api_openclaw_coordinator_policy_update(
            CoordinatorPolicyRequest(limit_buy_max_count=2),
            authorization="Bearer token",
        )
        assert False, "operator must not update OpenClaw production config"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "openclaw:admin" in str(exc.detail)

    replay = api_main.api_openclaw_unattended_trade_guard_replay(
        OpenClawGuardReplayRequest(limit=1),
        authorization="Bearer token",
    )
    assert replay.ok is True
    historical = api_main.api_openclaw_historical_replay(
        OpenClawHistoricalReplayRequest(limit=1),
        authorization="Bearer token",
    )
    assert historical.ok is True
    dry_run = api_main.api_openclaw_pipeline_run(
        TriggerRequest(dry_run=True),
        authorization="Bearer token",
    )
    assert dry_run.data["dry_run"] is True


def test_auth_security_status_flags_default_admin_password(monkeypatch):
    from datetime import datetime, timedelta

    import api_server.auth as auth

    class FakeRepo:
        def __init__(self):
            self.users = {
                "admin": (auth._hash_password("admin123"), "admin", "2026-01-01T00:00:00"),
                "op": (auth._hash_password("changed"), "operator", "2026-01-01T00:00:00"),
            }
            self.tokens = [
                ("admin", "admin", (datetime.now() + timedelta(days=1)).isoformat(), (datetime.now() - timedelta(days=9)).isoformat()),
                ("op", "operator", (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() - timedelta(days=2)).isoformat()),
            ]

        def executescript(self, sql):
            return None

        def execute(self, sql, params=()):
            return None

        def fetchone(self, sql, params=()):
            if "SELECT username FROM api_users" in sql:
                username = params[0]
                return (username,) if username in self.users else None
            if "SELECT password FROM api_users" in sql:
                username = params[0]
                row = self.users.get(username)
                return (row[0],) if row else None
            return None

        def fetchall(self, sql, params=()):
            if "SELECT username, role, updated_at FROM api_users" in sql:
                return [(username, row[1], row[2]) for username, row in self.users.items()]
            if "SELECT username, role, expires_at, created_at FROM api_tokens" in sql:
                return list(self.tokens)
            if "SELECT timestamp, actor, username, action, success, detail FROM auth_audit_log" in sql:
                return []
            return []

    monkeypatch.setattr(auth, "repo", FakeRepo())

    status = auth.get_auth_security_status()

    assert status["status"] == "warning"
    assert status["default_admin_password"] is True
    assert status["role_counts"]["admin"] == 1
    assert status["role_counts"]["operator"] == 1
    assert status["tokens"]["active"] == 1
    assert status["tokens"]["expired"] == 1
    assert status["tokens"]["active_admin"] == 1
    assert status["tokens"]["old_active"] == 1
    assert any(item["code"] == "default_admin_password" for item in status["findings"])
    assert any(item["code"] == "old_active_tokens" for item in status["findings"])


def test_production_security_report_recommends_admin_hardening(monkeypatch):
    import api_server.auth as auth

    security = {
        "status": "warning",
        "default_admin_password": True,
        "role_counts": {"admin": 1, "operator": 1, "viewer": 0},
        "tokens": {"active": 3, "active_admin": 2, "old_active": 1},
        "audit_summary": {"recent_count": 2, "failed_auth_count": 0},
        "findings": [
            {"level": "warning", "code": "default_admin_password", "message": "默认密码"},
            {"level": "warning", "code": "old_active_tokens", "message": "旧 token"},
        ],
    }
    monkeypatch.setattr(auth, "get_auth_security_status", lambda: security)

    report = auth.build_production_security_report()

    assert report["status"] == "error"
    assert report["ready"] is False
    assert report["checklist"][0]["ok"] is False
    assert any("change-password" in item for item in report["recommended_actions"])


def test_cleanup_expired_tokens_deletes_expired_and_invalid(monkeypatch):
    from datetime import datetime, timedelta

    import api_server.auth as auth

    class FakeRepo:
        def __init__(self):
            self.tokens = {
                "active": ("op", (datetime.now() + timedelta(days=1)).isoformat()),
                "expired": ("op", (datetime.now() - timedelta(days=1)).isoformat()),
                "invalid": ("op", "bad-date"),
            }
            self.audit = []

        def executescript(self, sql):
            return None

        def fetchone(self, sql, params=()):
            if "SELECT username FROM api_users" in sql:
                return ("admin",)
            return None

        def fetchall(self, sql, params=()):
            if "SELECT token, username, expires_at FROM api_tokens" in sql:
                return [(token, username, expires_at) for token, (username, expires_at) in self.tokens.items()]
            return []

        def execute(self, sql, params=()):
            if sql.startswith("DELETE FROM api_tokens WHERE token"):
                self.tokens.pop(params[0], None)
            elif sql.startswith("INSERT INTO auth_audit_log"):
                self.audit.append(params)

    fake = FakeRepo()
    monkeypatch.setattr(auth, "repo", fake)

    result = auth.cleanup_expired_tokens(actor="admin")

    assert result == {"deleted": 2, "expired": 1, "invalid": 1, "remaining_active": 1}
    assert sorted(fake.tokens.keys()) == ["active"]
    assert fake.audit
    assert fake.audit[-1][4] == "cleanup_tokens"
    assert "deleted=2" in fake.audit[-1][6]


def test_revoke_other_user_tokens_keeps_current_token(monkeypatch):
    import api_server.auth as auth

    class FakeRepo:
        def __init__(self):
            self.tokens = {"keep": "admin", "old1": "admin", "old2": "admin", "op": "op"}
            self.audit = []

        def executescript(self, sql):
            return None

        def fetchone(self, sql, params=()):
            if "SELECT username FROM api_users" in sql:
                return ("admin",)
            return None

        def fetchall(self, sql, params=()):
            if "SELECT token FROM api_tokens WHERE username=? AND token<>?" in sql:
                username, keep = params
                return [(token,) for token, owner in self.tokens.items() if owner == username and token != keep]
            return []

        def execute(self, sql, params=()):
            if sql.startswith("DELETE FROM api_tokens WHERE username=? AND token<>?"):
                username, keep = params
                for token, owner in list(self.tokens.items()):
                    if owner == username and token != keep:
                        self.tokens.pop(token, None)
            elif sql.startswith("INSERT INTO auth_audit_log"):
                self.audit.append(params)

    fake = FakeRepo()
    monkeypatch.setattr(auth, "repo", fake)

    count = auth.revoke_other_user_tokens("admin", keep_token="keep", actor="admin")

    assert count == 2
    assert fake.tokens == {"keep": "admin", "op": "op"}
    assert fake.audit[-1][4] == "revoke_other_tokens"


def test_dashboard_panel_input_supports_read_token(monkeypatch):
    from fastapi.testclient import TestClient

    from api_server.main import app
    from api_server.main import settings as api_settings

    monkeypatch.setattr(api_settings, "observability_read_token", "demo-read-token")
    client = TestClient(app)
    resp = client.get("/api/observability/dashboard/panel-input?obs_token=demo-read-token")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is True
    assert "trace" in payload.get("data", {})


def test_ops_center_payload_includes_registry(monkeypatch):
    from core.application import ops_service

    monkeypatch.setattr(ops_service, "get_system_snapshot", lambda refresh=False: {"ok": True})
    monkeypatch.setattr(ops_service, "get_recent_task_runs", lambda limit=20: [{"task": "scan"}])
    monkeypatch.setattr(ops_service, "get_recent_system_events", lambda limit=20: [{"title": "evt"}])
    monkeypatch.setattr(ops_service, "get_operation_log", lambda limit=20: [{"action": "run"}])
    monkeypatch.setattr(
        ops_service,
        "get_registry_overview",
        lambda: {
            "provider_count": 4,
            "strategy_count": 8,
            "notifier_count": 2,
            "workflow_count": 3,
            "agent_count": 6,
            "providers": [],
            "strategies": [],
            "notifiers": [],
            "workflows": [],
            "agents": [],
            "meta": {
                "source": "core.registry",
                "refreshed_at": "2026-01-01T00:00:00+00:00",
                "change_token": "x" * 40,
            },
        },
    )

    payload = ops_service.get_ops_center_payload(limit=5, refresh_snapshot=True)
    assert "registry" in payload
    assert payload["registry_changed"] is True
    assert payload["registry_sync"]["payload_mode"] == "full"
    assert payload["registry_sync"]["changed"] is True
    assert payload["registry_sync"]["cached"] is False
    assert payload["registry"]["provider_count"] == 4
    assert payload["registry"]["strategy_count"] == 8
    assert payload["registry"]["notifier_count"] == 2
    assert payload["registry"]["workflow_count"] == 3
    assert payload["registry"]["agent_count"] == 6
    assert payload["registry"]["meta"]["source"] == "core.registry"


def test_ops_center_registry_incremental_short_circuit(monkeypatch):
    from core.application import ops_service

    monkeypatch.setattr(ops_service, "get_system_snapshot", lambda refresh=False: {"ok": True})
    monkeypatch.setattr(ops_service, "get_recent_task_runs", lambda limit=20: [])
    monkeypatch.setattr(ops_service, "get_recent_system_events", lambda limit=20: [])
    monkeypatch.setattr(ops_service, "get_operation_log", lambda limit=20: [])
    monkeypatch.setattr(
        ops_service,
        "get_registry_overview",
        lambda: {
            "provider_count": 4,
            "strategy_count": 8,
            "notifier_count": 2,
            "workflow_count": 3,
            "agent_count": 6,
            "providers": [{"key": "llm"}],
            "strategies": [{"key": "sepa"}],
            "notifiers": [{"key": "serverchan"}],
            "workflows": [{"key": "scan_pipeline"}],
            "agents": [{"key": "coordinator"}],
            "meta": {
                "source": "core.registry",
                "refreshed_at": "2026-01-01T00:00:00+00:00",
                "change_token": "tok_abc123",
            },
        },
    )

    payload = ops_service.get_ops_center_payload(limit=5, registry_token="tok_abc123")
    assert payload["registry_changed"] is False
    assert payload["registry_sync"]["payload_mode"] == "compact"
    assert payload["registry_sync"]["changed"] is False
    assert payload["registry_sync"]["active_token"] == "tok_abc123"
    assert payload["registry"]["provider_count"] == 4
    assert payload["registry"]["strategy_count"] == 8
    assert payload["registry"]["notifier_count"] == 2
    assert payload["registry"]["workflow_count"] == 3
    assert payload["registry"]["agent_count"] == 6
    assert payload["registry"]["providers"] == []
    assert payload["registry"]["strategies"] == []
    assert payload["registry"]["notifiers"] == []
    assert payload["registry"]["workflows"] == []
    assert payload["registry"]["agents"] == []


def test_event_trend_report_from_ops_service(monkeypatch):
    from datetime import datetime, timezone

    from core.application import ops_service

    monkeypatch.setattr(
        ops_service,
        "get_recent_system_events",
        lambda limit=500: [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "approval",
                "category": "trade",
                "title": "交易审批拒绝 BUY 600519",
                "level": "warning",
            }
        ],
    )
    report = ops_service.get_event_trend_report(window_days=3, event_limit=100)
    assert report["window_days"] == 3
    assert report["totals"]["approval_total"] >= 1


def test_otel_collector_circuit_breaker_flow():
    from core.observability.otel_collector import (
        get_collector_state,
        push_otel_collector,
        reset_collector_state,
    )

    def always_fail_sender(endpoint, payload, timeout_seconds, headers):
        return False, "forced failure"

    reset_collector_state()
    first = push_otel_collector(
        endpoint="http://127.0.0.1:4318/v1/traces",
        metrics_snapshot={"counters": {"m": 1.0}, "histograms": {}},
        signals=("metrics",),
        dry_run=False,
        sender=always_fail_sender,
        retries=0,
        backoff_seconds=0.0,
        breaker_fail_threshold=1,
        breaker_cooldown_seconds=60,
    )
    assert first["status"] == "partial_failed"
    state = get_collector_state()
    assert state["circuit_open"] is True

    second = push_otel_collector(
        endpoint="http://127.0.0.1:4318/v1/traces",
        metrics_snapshot={"counters": {"m": 1.0}, "histograms": {}},
        signals=("metrics",),
        dry_run=False,
        sender=always_fail_sender,
        retries=0,
    )
    assert second["status"] == "blocked"


def test_otel_export_and_collector_support_trace_filter():
    from core.observability.otel_collector import build_traces_batches, push_otel_collector
    from core.observability.tracing import export_otel_traces, finish_span, parse_traceparent, start_span

    root = start_span("unit.filter.root")
    finish_span(root, status="ok")
    trace_hex = parse_traceparent(root.get("traceparent", "")).get("trace_id_hex", "")
    assert trace_hex

    exported = export_otel_traces(limit=20, trace_id=trace_hex)
    assert exported["trace_id"] == trace_hex
    assert exported["summary"]["span_count"] >= 1
    assert exported["graph"]["node_count"] >= 1

    batches = build_traces_batches(limit=20, batch_size=10, trace_id=trace_hex)
    assert len(batches) >= 1

    pushed = push_otel_collector(
        endpoint="",
        trace_limit=20,
        signals=("traces",),
        trace_id=trace_hex,
        dry_run=True,
    )
    assert pushed["status"] == "ok"
    assert pushed["trace_id"] == trace_hex


def test_trace_backend_presets_and_dashboard_template_models():
    from core.observability.dashboard_templates import build_trace_dashboard_template
    from core.observability.panel_input import build_observability_panel_input
    from core.observability.trace_backend_presets import build_trace_backend_preset, resolve_trace_route

    tempo = build_trace_backend_preset(
        backend="tempo",
        base_url="http://127.0.0.1:4318",
        tenant_id="demo-tenant",
    )
    jaeger = build_trace_backend_preset(
        backend="jaeger",
        base_url="http://127.0.0.1:4318",
    )
    route = resolve_trace_route(
        signal="traces",
        backend="tempo",
        base_url="http://127.0.0.1:4318",
        tenant_id="demo-tenant",
    )
    template = build_trace_dashboard_template()

    assert tempo["signal_routes"]["traces"].endswith("/v1/traces")
    assert jaeger["backend"] == "jaeger"
    assert route["headers"].get("X-Scope-OrgID", "") == "demo-tenant"
    assert template["template_name"] == "trace_default_v1"
    assert len(template.get("panels", [])) >= 1
    payload = build_observability_panel_input(
        active_trace_id="abc",
        trace_index=[],
        trace_items=[],
        trace_summary={},
        trace_graph={},
        trace_otel_export={},
        alerts_payload={},
        routing_state={},
        dispatch_receipts=[],
        collector_state={},
        backend_presets={"tempo": tempo},
        dashboard_template=template,
    )
    assert payload["trace"]["active_trace_id"] == "abc"


def test_grafana_provisioning_generator_for_container_path(tmp_path):
    from infra.setup_grafana_provisioning import setup_grafana_provisioning

    result = setup_grafana_provisioning(
        output_dir=tmp_path / "provisioning",
        api_base="http://127.0.0.1:9000",
        overwrite=True,
    )
    provider_path = tmp_path / "provisioning" / "dashboards" / "finquanta-dashboards.yaml"
    text = provider_path.read_text(encoding="utf-8")

    assert result["dashboards_count"] >= 1
    assert "/var/lib/grafana/dashboards/finquanta" in text
    assert result["provider_dashboards_path"] == "/var/lib/grafana/dashboards/finquanta"
    datasource_path = tmp_path / "provisioning" / "datasources" / "finquanta-infinity.yaml"
    ds_text = datasource_path.read_text(encoding="utf-8")
    assert "FinQuanta Tempo" in ds_text
    assert "FinQuanta Loki" in ds_text


def test_oneclick_stack_precheck_helpers():
    from infra.oneclick_observability_stack import command_exists, is_port_in_use

    assert isinstance(command_exists("python"), bool)
    assert isinstance(is_port_in_use(3000), bool)


def test_task_workflow_openclaw_traceparent_propagation(monkeypatch):
    from core.application import task_service
    from core.observability.tracing import parse_traceparent, start_span

    class FakeScheduler:
        def __init__(self):
            pass

        def _task_scan_stocks(self):
            return {"ok": True}

        def _task_risk_calc(self):
            return {"ok": True}

        def _task_auto_backtest(self):
            return {"ok": True}

        def _task_watchlist_scan(self):
            return {"ok": True}

        def _task_short_term(self):
            return {"ok": True}

    captured: dict[str, str] = {}

    def fake_run_openclaw_pipeline(boards=None, traceparent=""):
        captured["traceparent"] = traceparent
        return {"ok": True, "boards": boards or []}

    monkeypatch.setattr(task_service, "run_openclaw_pipeline", fake_run_openclaw_pipeline)
    monkeypatch.setattr("desktop.daemon_scheduler.DaemonScheduler", FakeScheduler)

    parent = start_span("unit.root")
    result = task_service.trigger_named_task("pipeline", boards=["AI"], traceparent=parent.get("traceparent", ""))
    incoming = parse_traceparent(parent.get("traceparent", ""))
    forwarded = parse_traceparent(captured.get("traceparent", ""))

    assert result.get("trace", {}).get("workflow", {}).get("name") == "workflow.openclaw_pipeline"
    assert forwarded.get("trace_id_hex", "") == incoming.get("trace_id_hex", "")
    assert bool(result.get("trace", {}).get("workflow", {}).get("traceparent", ""))


def test_openclaw_pipeline_disabled_carries_trace_context(monkeypatch):
    from core.application import openclaw_service
    from core.observability.tracing import parse_traceparent, start_span

    monkeypatch.setattr(openclaw_service, "is_feature_enabled", lambda key: False)
    parent = start_span("unit.parent")
    result = openclaw_service.run_openclaw_pipeline(boards=["AI"], traceparent=parent.get("traceparent", ""))
    child_ctx = parse_traceparent(result.get("trace", {}).get("traceparent", ""))
    parent_ctx = parse_traceparent(parent.get("traceparent", ""))

    assert result.get("disabled") is True
    assert child_ctx.get("trace_id_hex", "") == parent_ctx.get("trace_id_hex", "")


def test_openclaw_pipeline_prefers_gateway(monkeypatch):
    from core.application import openclaw_service

    monkeypatch.setattr(openclaw_service, "is_feature_enabled", lambda key: True)
    monkeypatch.setenv("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")

    def fake_gateway(action: str, payload: dict, traceparent: str = ""):
        return {
            "ok": True,
            "action": action,
            "payload": payload,
            "traceparent": traceparent,
        }

    monkeypatch.setattr(openclaw_service, "_call_openclaw_gateway", fake_gateway)
    monkeypatch.setattr(
        openclaw_service,
        "_run_local_openclaw_pipeline",
        lambda boards: (_ for _ in ()).throw(RuntimeError("local should not be called")),
    )

    result = openclaw_service.run_openclaw_pipeline(boards=["AI"], traceparent="00-abc-abc-01")
    assert result.get("ok") is True
    assert result.get("action") == "pipeline"
    assert result.get("payload", {}).get("boards") == ["AI"]
    assert result.get("gateway", {}).get("used") is True


def test_openclaw_learning_gateway_fallback_to_local(monkeypatch):
    from core.application import openclaw_service

    monkeypatch.setattr(openclaw_service, "is_feature_enabled", lambda key: True)
    monkeypatch.setenv("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")
    monkeypatch.setattr(
        openclaw_service,
        "_call_openclaw_gateway",
        lambda action, payload, traceparent="": (_ for _ in ()).throw(RuntimeError("gateway down")),
    )
    monkeypatch.setattr(openclaw_service, "_run_local_openclaw_learning", lambda: {"ok": True, "learnings": []})

    result = openclaw_service.run_openclaw_learning(traceparent="00-abc-abc-01")
    assert result.get("ok") is True
    assert result.get("gateway", {}).get("used") is False
    assert result.get("gateway", {}).get("mode") == "fallback_local"


def test_openclaw_service_coordinator_policy_roundtrip(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.agents as agents

    store = {}
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))

    updated = openclaw_service.update_coordinator_policy(
        {
            "sell_only_sentiment_ratio": 0.22,
            "limit_buy_sentiment_ratio": 0.44,
            "limit_buy_max_count": 3,
        },
        actor="ops-admin",
    )
    loaded = openclaw_service.get_coordinator_policy()
    reset = openclaw_service.reset_coordinator_policy()

    assert updated["sell_only_sentiment_ratio"] == 0.22
    assert loaded["limit_buy_max_count"] == 3
    assert reset["limit_buy_max_count"] == 1
    history = openclaw_service.get_openclaw_config_audit()["history"]
    assert history[1]["domain"] == "coordinator_policy"
    assert history[1]["actor"] == "ops-admin"
    assert store["openclaw_unattended_simulation_state"]["last_status"] == "reset"
    assert "Coordinator" in store["openclaw_unattended_simulation_state"]["reset_reason"]


def test_openclaw_service_config_audit_rollback_restores_previous_values(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.agents as agents

    store = {}
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))

    original = openclaw_service.get_coordinator_policy()
    updated = openclaw_service.update_coordinator_policy({"limit_buy_max_count": 4})
    rolled_back = openclaw_service.rollback_openclaw_config(audit_index=0)
    audit = openclaw_service.get_openclaw_config_audit()

    assert updated["limit_buy_max_count"] == 4
    assert rolled_back["rolled_back"] is True
    assert rolled_back["domain"] == "coordinator_policy"
    assert rolled_back["config"]["limit_buy_max_count"] == original["limit_buy_max_count"]
    assert audit["history"][0]["action"] == "rollback"
    assert audit["history"][0]["domain"] == "coordinator_policy"


def test_openclaw_service_unattended_trade_guard_roundtrip(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.agents as agents

    store = {}
    monkeypatch.setattr(agents, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(agents, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))

    updated = openclaw_service.update_unattended_trade_guard(
        {
            "unattended_buy_enabled": True,
            "max_daily_buy_amount": 88888,
            "simulation_min_success_runs": 5,
            "blacklist": "600519, 300750",
        }
    )
    loaded = openclaw_service.get_unattended_trade_guard()
    reset = openclaw_service.reset_unattended_trade_guard()

    assert updated["config"]["unattended_buy_enabled"] is True
    assert updated["config"]["blacklist"] == ["300750", "600519"]
    assert updated["config"]["simulation_min_success_runs"] == 5
    assert updated["simulation"]["last_status"] == "reset"
    assert loaded["config"]["max_daily_buy_amount"] == 88888
    assert reset["config"]["unattended_buy_enabled"] is False
    assert openclaw_service.get_openclaw_config_audit()["history"][0]["domain"] == "unattended_trade_guard"


def test_openclaw_service_daemon_alert_policy_roundtrip(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.daemon_scheduler as daemon_scheduler

    store = {}
    monkeypatch.setattr(daemon_scheduler, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr("desktop.data_access.get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: store.__setitem__(key, value))

    updated = openclaw_service.update_openclaw_daemon_alert_policy(
        {
            "enabled": False,
            "suppress_seconds": 120,
            "escalate_after": 2,
            "notify_on_success": True,
            "success_summary_interval_seconds": 600,
            "min_level": "info",
            "default_channels": "in_app_feed,wechat_personal",
            "escalation_channels": ["wechat_personal", "wecom_group_bot"],
        }
    )
    loaded = openclaw_service.get_openclaw_daemon_alert_policy()
    reset = openclaw_service.reset_openclaw_daemon_alert_policy()

    assert updated["enabled"] is False
    assert updated["suppress_seconds"] == 120
    assert updated["notify_on_success"] is True
    assert updated["success_summary_interval_seconds"] == 600
    assert updated["min_level"] == "info"
    assert updated["default_channels"] == ["in_app_feed", "wechat_personal"]
    assert loaded["escalate_after"] == 2
    assert reset["enabled"] is True
    assert reset["escalate_after"] == 3
    assert reset["notify_on_success"] is False
    assert openclaw_service.get_openclaw_config_audit()["history"][0]["domain"] == "daemon_alert_policy"


def test_openclaw_service_daemon_status_payload(monkeypatch):
    import core.application.openclaw_service as openclaw_service

    def fake_kv(key, default=None):
        values = {
            "sched_time_overrides": {"openclaw_pipeline": "10:25"},
            "openclaw_last_daemon_run": {"status": "success", "summary": "ok"},
            "openclaw_daemon_run_history": [{"status": "success", "summary": "ok"}],
            "openclaw_guard_replay_last": {"approved_count": 1},
            "openclaw_guard_replay_history": [{"approved_count": 1}],
        }
        return values.get(key, default)

    monkeypatch.setattr("desktop.data_access.get_kv_json", fake_kv)
    monkeypatch.setattr("desktop.daemon_scheduler.get_kv_json", fake_kv)
    monkeypatch.setattr(
        "desktop.daemon_scheduler.get_daemon_runtime_status",
        lambda: {"active": True, "disabled_tasks": [], "next_task": {"task_key": "openclaw_pipeline"}},
    )
    monkeypatch.setattr("desktop.daemon_scheduler._load_openclaw_daemon_boards", lambda: ["人工智能"])
    monkeypatch.setattr(
        openclaw_service,
        "get_unattended_trade_guard",
        lambda: {
            "config": {
                "enabled": True,
                "unattended_buy_enabled": False,
                "allow_sell_when_buy_disabled": True,
            },
            "usage": {"buy_count": 0},
            "simulation": {"passed": False},
            "replay": {"last": {}, "history": []},
        },
    )

    payload = openclaw_service.get_openclaw_daemon_status()

    assert payload["daemon"]["active"] is True
    assert payload["openclaw"]["config"]["enabled"] is True
    assert payload["openclaw"]["config"]["boards"] == ["人工智能"]
    assert payload["openclaw"]["alert_policy"]["enabled"] is True
    assert payload["openclaw"]["last_run"]["status"] == "success"
    assert payload["openclaw"]["history"][0]["status"] == "success"
    assert payload["openclaw"]["readiness"]["status"] == "ready"


def test_openclaw_daemon_readiness_grades_errors():
    from core.application.openclaw_service import _build_openclaw_daemon_readiness

    payload = _build_openclaw_daemon_readiness(
        runtime={"active": False},
        config={"enabled": True, "boards": ["人工智能"]},
        last_run={"status": "success"},
        alert_state={},
        alert_policy={"enabled": True},
        trade_guard={
            "config": {
                "enabled": True,
                "unattended_buy_enabled": True,
                "require_simulation_pass": True,
                "allow_sell_when_buy_disabled": True,
            },
            "simulation": {"passed": False},
            "replay": {"last": {}},
        },
    )

    assert payload["status"] == "error"
    assert any("daemon 未运行" in item for item in payload["errors"])
    assert any("仿真门禁未通过" in item for item in payload["errors"])


def test_daemon_scheduler_runs_headless_openclaw_pipeline(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.daemon_scheduler as daemon_scheduler

    calls = {}
    saved = {}
    events = []

    def fake_run_openclaw_pipeline(boards=None, **kwargs):
        calls["boards"] = boards
        return {
            "steps": [{"status": "ok"}],
            "decisions": [{"action": "buy", "code": "300750"}],
            "executed_decisions": [{"action": "buy", "code": "300750"}],
            "errors": [],
            "execution_plan": {"mode": "normal", "blocked_count": 0},
            "agent_trace_context": {"trace_id_hex": "abc123", "status": "ok"},
            "agent_trace": [
                {
                    "agent_key": "coordinator",
                    "stage": "s3",
                    "status": "ok",
                    "duration_ms": 12,
                    "span_id": "span-1",
                    "output_summary": {"decisions": {"count": 1}},
                }
            ],
            "coordinator": {
                "orchestration": [
                    {
                        "stage": "s3",
                        "ready": True,
                        "mode": "normal",
                        "actions_done": [{"type": "mark_degraded", "status": "skipped"}],
                    }
                ]
            },
        }

    monkeypatch.setattr(openclaw_service, "run_openclaw_pipeline", fake_run_openclaw_pipeline)
    monkeypatch.setattr(daemon_scheduler, "get_kv_json", lambda key, default=None: saved.get(key, default))
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: saved.__setitem__(key, value))
    monkeypatch.setattr(
        daemon_scheduler,
        "log_system_event",
        lambda source, category, title, detail="", level="info", **kwargs: events.append(
            {"source": source, "category": category, "title": title, "detail": detail, "level": level}
        ),
    )

    scheduler = daemon_scheduler.DaemonScheduler(boards=["人工智能", "芯片"])
    scheduler._task_openclaw_pipeline()

    assert any(task.get("key") == "openclaw_pipeline" for task in daemon_scheduler.SCHEDULE)
    assert calls["boards"] == ["人工智能", "芯片"]
    assert saved["openclaw_last_daemon_run"]["status"] == "success"
    assert saved["openclaw_last_daemon_run"]["execution_plan"]["mode"] == "normal"
    assert saved["openclaw_last_daemon_run"]["agent_trace"]["span_count"] == 1
    assert saved["openclaw_last_daemon_run"]["coordinator_orchestration"]["stage_count"] == 1
    assert "executed=1" in saved["openclaw_last_daemon_run"]["summary"]
    assert saved[daemon_scheduler._OPENCLAW_RUN_HISTORY_KEY][0]["status"] == "success"
    assert saved[daemon_scheduler._OPENCLAW_RUN_HISTORY_KEY][0]["mode"] == "normal"
    assert saved[daemon_scheduler._OPENCLAW_RUN_HISTORY_KEY][0]["trace_span_count"] == 1
    assert saved[daemon_scheduler._OPENCLAW_RUN_HISTORY_KEY][0]["orchestration_stage_count"] == 1
    assert events[-1]["level"] == "info"


def test_daemon_scheduler_alerts_on_headless_openclaw_failure(monkeypatch):
    import core.application.openclaw_service as openclaw_service
    import desktop.daemon_scheduler as daemon_scheduler

    saved = {}
    pushed = []
    events = []

    monkeypatch.setattr(
        openclaw_service,
        "run_openclaw_pipeline",
        lambda boards=None, **kwargs: (_ for _ in ()).throw(RuntimeError("gateway down")),
    )
    monkeypatch.setattr(daemon_scheduler, "get_kv_json", lambda key, default=None: saved.get(key, default))
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: saved.__setitem__(key, value))
    monkeypatch.setattr(
        daemon_scheduler,
        "log_system_event",
        lambda source, category, title, detail="", level="info", **kwargs: events.append(
            {"source": source, "category": category, "title": title, "detail": detail, "level": level}
        ),
    )

    scheduler = daemon_scheduler.DaemonScheduler(boards=["人工智能"])
    monkeypatch.setattr(scheduler, "_push", lambda title, content, channels=None: pushed.append((title, content, channels)))

    try:
        scheduler._task_openclaw_pipeline()
    except RuntimeError:
        pass

    assert saved["openclaw_last_daemon_run"]["status"] == "error"
    assert saved["openclaw_last_daemon_run"]["errors"]
    assert saved[daemon_scheduler._OPENCLAW_RUN_HISTORY_KEY][0]["status"] == "error"
    assert events[-1]["level"] == "error"
    assert pushed and "失败" in pushed[-1][0]


def test_daemon_scheduler_openclaw_alert_suppresses_and_escalates(monkeypatch):
    import desktop.daemon_scheduler as daemon_scheduler

    store = {}
    pushed = []
    monkeypatch.setenv("FINQUANTA_OPENCLAW_ALERT_SUPPRESS_SECONDS", "3600")
    monkeypatch.setenv("FINQUANTA_OPENCLAW_ALERT_ESCALATE_AFTER", "3")
    monkeypatch.setattr(daemon_scheduler, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: store.__setitem__(key, value))

    scheduler = daemon_scheduler.DaemonScheduler(boards=["人工智能"])
    monkeypatch.setattr(scheduler, "_push", lambda title, content, channels=None: pushed.append((title, content, channels)))

    scheduler._push_openclaw_alert("error", "⚠️ OpenClaw后台执行失败", "first")
    scheduler._push_openclaw_alert("error", "⚠️ OpenClaw后台执行失败", "second")
    scheduler._push_openclaw_alert("error", "⚠️ OpenClaw后台执行失败", "third")

    assert len(pushed) == 2
    assert pushed[0][0] == "⚠️ OpenClaw后台执行失败"
    assert "连续失败3次" in pushed[1][0]
    assert store[daemon_scheduler._OPENCLAW_ALERT_STATE_KEY]["suppressed_count"] == 1
    assert store[daemon_scheduler._OPENCLAW_ALERT_STATE_KEY]["consecutive_errors"] == 3


def test_daemon_scheduler_openclaw_alert_status_filters_and_success_interval(monkeypatch):
    import desktop.daemon_scheduler as daemon_scheduler

    store = {
        daemon_scheduler._OPENCLAW_ALERT_POLICY_KEY: {
            "enabled": True,
            "suppress_seconds": 0,
            "escalate_after": 2,
            "notify_on_success": True,
            "notify_on_warning": False,
            "notify_on_error": True,
            "success_summary_interval_seconds": 3600,
            "min_level": "success",
            "default_channels": ["in_app_feed"],
            "escalation_channels": ["wechat_personal", "wecom_group_bot"],
        }
    }
    pushed = []
    monkeypatch.setattr(daemon_scheduler, "get_kv_json", lambda key, default=None: store.get(key, default))
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: store.__setitem__(key, value))

    scheduler = daemon_scheduler.DaemonScheduler(boards=["人工智能"])
    monkeypatch.setattr(scheduler, "_push", lambda title, content, channels=None: pushed.append((title, content, channels)))

    scheduler._push_openclaw_alert("warning", "warn", "warning content")
    assert not pushed
    assert store[daemon_scheduler._OPENCLAW_ALERT_STATE_KEY]["last_result"] == "disabled_for_status"

    scheduler._push_openclaw_alert("success", "ok", "success content")
    scheduler._push_openclaw_alert("success", "ok again", "success content again")
    assert len(pushed) == 1
    assert store[daemon_scheduler._OPENCLAW_ALERT_STATE_KEY]["last_result"] == "success_suppressed"

    scheduler._push_openclaw_alert("error", "err1", "first")
    scheduler._push_openclaw_alert("error", "err2", "second")
    assert any("OpenClaw连续失败2次" in title for title, _content, _channels in pushed)
    routing = store[daemon_scheduler._OPENCLAW_ALERT_STATE_KEY]["routing"]
    assert routing["escalated"] is True
    assert routing["channels"] == ["wechat_personal", "wecom_group_bot"]


def test_daemon_scheduler_push_maps_notification_channels(monkeypatch):
    import desktop.daemon_scheduler as daemon_scheduler

    store = {}
    calls = []
    monkeypatch.setattr(daemon_scheduler, "set_kv_json", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(
        "signal_push.push_signal",
        lambda title, content, channels=None: calls.append(channels) or {"wecom": True},
    )

    scheduler = daemon_scheduler.DaemonScheduler(boards=["人工智能"])
    scheduler._last_run = {}
    scheduler._push("title", "content", channels=["in_app_feed", "wecom_group_bot"])

    assert calls == [["wecom"]]
    status = store[daemon_scheduler._DAEMON_PUSH_STATUS_KEY]
    assert status["requested_channels"] == ["in_app_feed", "wecom_group_bot"]
    assert status["push_channels"] == ["wecom"]
    assert status["last_result"] == "success"
