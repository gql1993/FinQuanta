from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def check(name: str, fn):
    try:
        result = fn()
        print(f"[PASS] {name}: {result}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main():
    ok = True

    from core.runtime.mode import resolve_runtime_mode_context
    from core.config.feature_flags import is_feature_enabled
    from core.ai.decision_engine import parse_ai_decision_response
    from core.risk.approval_service import evaluate_trade_request

    ok &= check(
        "runtime_mode_sqlite",
        lambda: resolve_runtime_mode_context(
            runtime_mode=None,
            db_backend="sqlite",
            api_base="http://127.0.0.1:9000",
        ).runtime_mode,
    )
    ok &= check(
        "runtime_mode_postgres",
        lambda: resolve_runtime_mode_context(
            runtime_mode=None,
            db_backend="postgres",
            api_base="http://127.0.0.1:9000",
        ).runtime_mode,
    )

    original_flag = os.environ.get("FINQUANTA_FEATURE_OPENCLAW_PIPELINE")
    try:
        os.environ["FINQUANTA_FEATURE_OPENCLAW_PIPELINE"] = "0"
        ok &= check("feature_flag_override", lambda: is_feature_enabled("openclaw_pipeline"))
    finally:
        if original_flag is None:
            os.environ.pop("FINQUANTA_FEATURE_OPENCLAW_PIPELINE", None)
        else:
            os.environ["FINQUANTA_FEATURE_OPENCLAW_PIPELINE"] = original_flag

    ok &= check(
        "decision_parse",
        lambda: parse_ai_decision_response(
            '{"analysis":"ok","decisions":[{"action":"BUY","code":"600519","price":123.4,"shares":300,"reason":"test"}]}'
        ).get("parse_status"),
    )

    ok &= check(
        "trade_approval_skeleton",
        lambda: evaluate_trade_request(
            mode="auto",
            action="SELL",
            code="600519",
            name="贵州茅台",
            price=123.4,
            shares=0,
            reason="smoke",
        ).get("approved"),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
