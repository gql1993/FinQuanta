"""
Decision memory repository.
"""

from __future__ import annotations

import json
from datetime import datetime

from api_server.config import settings
from desktop.data_access import RepoCompatConnection, get_repo

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS ai_decision_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    mode TEXT,
    decisions TEXT,
    analysis TEXT,
    intel_summary TEXT,
    candidates_count INTEGER,
    market_regime TEXT,
    actual_results TEXT,
    calibrated INTEGER DEFAULT 0
)
"""


class DecisionRepository:
    def ensure_table(self) -> None:
        if settings.db_backend != "postgres":
            repo = get_repo()
            repo.executescript(_DDL_SQLITE)

    def save_memory(
        self,
        *,
        timestamp: str | None,
        mode: str,
        decisions: list[dict],
        analysis: str,
        intel_summary: str = "",
        candidates_count: int = 0,
        market_regime: str = "",
    ) -> None:
        self.ensure_table()
        try:
            conn = RepoCompatConnection()
            conn.execute(
                "INSERT INTO ai_decision_memory "
                "(timestamp,mode,decisions,analysis,intel_summary,candidates_count,market_regime) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    timestamp or datetime.now().isoformat(),
                    mode,
                    json.dumps(decisions, ensure_ascii=False),
                    analysis,
                    intel_summary,
                    candidates_count,
                    market_regime,
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_uncalibrated_before(self, cutoff_timestamp: str) -> list[tuple]:
        self.ensure_table()
        conn = RepoCompatConnection()
        rows = conn.execute(
            "SELECT id, timestamp, decisions FROM ai_decision_memory "
            "WHERE calibrated=0 AND timestamp<? ORDER BY id",
            (cutoff_timestamp,),
        ).fetchall()
        conn.close()
        return rows

    def mark_calibrated(self, row_id: int, actual_results: list[dict]) -> None:
        self.ensure_table()
        conn = RepoCompatConnection()
        conn.execute(
            "UPDATE ai_decision_memory SET actual_results=?, calibrated=1 WHERE id=?",
            (json.dumps(actual_results, ensure_ascii=False), row_id),
        )
        conn.commit()
        conn.close()

    def get_recent_calibrated_results(self, limit: int = 50) -> list[str]:
        self.ensure_table()
        conn = RepoCompatConnection()
        rows = conn.execute(
            "SELECT actual_results FROM ai_decision_memory WHERE calibrated=1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [row[0] for row in rows]

    def get_latest_auto_memory(self) -> dict | None:
        self.ensure_table()
        row = get_repo().fetchone(
            "SELECT timestamp, decisions, analysis FROM ai_decision_memory "
            "WHERE mode='auto' ORDER BY id DESC LIMIT 1"
        )
        if not row:
            return None
        decisions = row[1]
        if isinstance(decisions, str):
            try:
                decisions = json.loads(decisions)
            except Exception:
                decisions = []
        return {
            "timestamp": row[0] or "",
            "analysis": row[2] or "",
            "items": decisions if isinstance(decisions, list) else [],
        }
