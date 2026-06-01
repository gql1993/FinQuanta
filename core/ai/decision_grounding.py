"""
Price grounding helpers for AI trading decisions.

Ensures buy decisions reference verified snapshot prices instead of LLM guesses.
"""

from __future__ import annotations

import os
from typing import Iterable


def grounded_price_tolerance() -> float:
    raw = os.environ.get("FINQUANTA_GROUNDED_PRICE_TOLERANCE", "0.01")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.01


def build_grounded_price_map(candidates: Iterable[dict] | None) -> dict[str, float]:
    """Extract code -> snapshot price from candidate payloads."""
    price_map: dict[str, float] = {}
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "") or "").strip()
        if not code:
            continue
        try:
            price = float(item.get("price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if price > 0:
            price_map[code] = round(price, 2)
    return price_map


def build_grounded_price_map_from_verification(verification: dict | None) -> dict[str, float]:
    """Build a price map from verification agent candidate buckets."""
    verification = verification or {}
    pooled: list[dict] = []
    for key in (
        "all_candidates",
        "verified_candidates",
        "questionable_candidates",
        "rejected_candidates",
    ):
        pooled.extend(item for item in (verification.get(key) or []) if isinstance(item, dict))
    return build_grounded_price_map(pooled)


def _recalculate_shares(shares: int, old_price: float, new_price: float) -> int:
    if shares < 100 or old_price <= 0 or new_price <= 0:
        return shares
    adjusted = int(shares * old_price / new_price / 100) * 100
    return max(100, adjusted)


def normalize_buy_decisions(
    decisions: list[dict] | None,
    price_map: dict[str, float],
    *,
    tolerance: float | None = None,
    recalculate_shares: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Align buy decision prices with grounded snapshot prices.

    Returns (normalized_decisions, adjustments).
    """
    tolerance = grounded_price_tolerance() if tolerance is None else tolerance
    normalized: list[dict] = []
    adjustments: list[dict] = []

    for decision in decisions or []:
        if not isinstance(decision, dict):
            continue
        item = dict(decision)
        action = str(item.get("action", "") or "").lower()
        code = str(item.get("code", "") or "").strip()
        if action != "buy" or not code:
            normalized.append(item)
            continue

        grounded_price = price_map.get(code)
        if grounded_price is None or grounded_price <= 0:
            normalized.append(item)
            continue

        try:
            old_price = float(item.get("price", 0) or 0)
        except (TypeError, ValueError):
            old_price = 0.0
        try:
            shares = int(item.get("shares", 0) or 0)
        except (TypeError, ValueError):
            shares = 0

        if old_price <= 0:
            item["price"] = grounded_price
            adjustments.append(
                {
                    "code": code,
                    "field": "price",
                    "from": old_price,
                    "to": grounded_price,
                    "reason": "missing_ai_price",
                }
            )
            normalized.append(item)
            continue

        drift = abs(grounded_price - old_price) / old_price
        if drift <= tolerance:
            normalized.append(item)
            continue

        item["price"] = grounded_price
        adjustment = {
            "code": code,
            "field": "price",
            "from": round(old_price, 2),
            "to": grounded_price,
            "drift_pct": round(drift * 100, 2),
            "reason": "price_grounded",
        }
        if recalculate_shares and shares >= 100:
            new_shares = _recalculate_shares(shares, old_price, grounded_price)
            if new_shares != shares:
                item["shares"] = new_shares
                adjustment["shares_from"] = shares
                adjustment["shares_to"] = new_shares
        adjustments.append(adjustment)
        normalized.append(item)

    return normalized, adjustments
