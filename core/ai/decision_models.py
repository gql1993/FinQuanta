"""
Normalized AI decision data models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TradingDecision:
    action: str
    code: str = ""
    name: str = ""
    price: float = 0.0
    shares: int = 0
    reason: str = ""
    score: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        extras = payload.pop("extras", {}) or {}
        payload.update(extras)
        return payload


@dataclass
class DecisionEngineResult:
    analysis: str = ""
    decisions: list[TradingDecision] = field(default_factory=list)
    error: str = ""
    raw_response: str = ""
    parse_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "error": self.error,
            "raw_response": self.raw_response,
            "parse_status": self.parse_status,
        }


def normalize_decision_payload(raw_decision: dict[str, Any]) -> TradingDecision:
    normalized_action = str(raw_decision.get("action", "")).strip().lower()
    extras = {
        key: value
        for key, value in raw_decision.items()
        if key not in {"action", "code", "name", "price", "shares", "reason", "score"}
    }
    return TradingDecision(
        action=normalized_action,
        code=str(raw_decision.get("code", "")).strip(),
        name=str(raw_decision.get("name", "")).strip(),
        price=float(raw_decision.get("price", 0) or 0),
        shares=int(raw_decision.get("shares", 0) or 0),
        reason=str(raw_decision.get("reason", "")).strip(),
        score=int(raw_decision.get("score", 0) or 0),
        extras=extras,
    )


def build_error_result(message: str) -> dict[str, Any]:
    return DecisionEngineResult(
        analysis=message,
        error=message,
        raw_response=message,
        parse_status="error",
    ).to_dict()


def build_decision_result(
    analysis: str,
    decisions: list[dict[str, Any]] | None = None,
    *,
    raw_response: str = "",
    parse_status: str = "ok",
    error: str = "",
) -> dict[str, Any]:
    normalized = [
        normalize_decision_payload(item)
        for item in (decisions or [])
        if isinstance(item, dict)
    ]
    return DecisionEngineResult(
        analysis=analysis,
        decisions=normalized,
        error=error,
        raw_response=raw_response,
        parse_status=parse_status,
    ).to_dict()
