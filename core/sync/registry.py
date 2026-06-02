"""Which runtime keys participate in desktop ↔ server sync."""

from __future__ import annotations

# Always included even if prefix rules change
SYNC_KEY_ALLOWLIST = frozenset(
    {
        "manual_portfolio",
        "portfolio_risk",
        "system_snapshot",
        "ai_config",
        "push_config",
        "last_scan_results",
        "last_scan_results_meta",
        "news_sentiment_snapshot",
        "arena_leaderboard_latest",
        "arena_run_latest",
        "active_strategy_selection",
        "openclaw_strategy_weights",
        "coordinator_policy",
        "unattended_trade_guard",
    }
)

SYNC_KEY_PREFIXES = (
    "ai_auto_cash",
    "ai_manual_cash",
    "ai_full_auto_cash",
    "ai_custom_cash",
    "ai_quantum_cash",
    "ai_",
    "arena_",
    "last_scan",
    "openclaw_",
    "portfolio_",
)

SYNC_KEY_BLOCKLIST_PREFIXES = (
    "_finquanta_sync",
    "finquanta_api_",
    "finquanta_sync_",
)


def is_syncable_key(key: str) -> bool:
    k = str(key or "").strip()
    if not k:
        return False
    if k in SYNC_KEY_ALLOWLIST:
        return True
    for prefix in SYNC_KEY_BLOCKLIST_PREFIXES:
        if k.startswith(prefix):
            return False
    for prefix in SYNC_KEY_PREFIXES:
        if k.startswith(prefix):
            return True
    return False
