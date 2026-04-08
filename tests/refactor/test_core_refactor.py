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
