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
    raw_decisions TEXT,
    analysis TEXT,
    intel_summary TEXT,
    candidates_count INTEGER,
    market_regime TEXT,
    verification_summary TEXT,
    guardrail_summary TEXT,
    execution_plan TEXT,
    actual_results TEXT,
    calibrated INTEGER DEFAULT 0
)
"""


class DecisionRepository:
    @staticmethod
    def _load_json(raw, default):
        if not raw:
            return default
        if isinstance(raw, (dict, list)):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except Exception:
                return default
        return default

    def ensure_table(self) -> None:
        if settings.db_backend != "postgres":
            repo = get_repo()
            repo.executescript(_DDL_SQLITE)
            patches = [
                "ALTER TABLE ai_decision_memory ADD COLUMN raw_decisions TEXT",
                "ALTER TABLE ai_decision_memory ADD COLUMN verification_summary TEXT",
                "ALTER TABLE ai_decision_memory ADD COLUMN guardrail_summary TEXT",
                "ALTER TABLE ai_decision_memory ADD COLUMN execution_plan TEXT",
            ]
            for sql in patches:
                try:
                    repo.execute(sql)
                except Exception:
                    pass

    def save_memory(
        self,
        *,
        timestamp: str | None,
        mode: str,
        decisions: list[dict],
        raw_decisions: list[dict] | None = None,
        analysis: str,
        intel_summary: str = "",
        candidates_count: int = 0,
        market_regime: str = "",
        verification_summary: dict | None = None,
        guardrail_summary: dict | None = None,
        execution_plan: dict | None = None,
    ) -> None:
        self.ensure_table()
        try:
            conn = RepoCompatConnection()
            conn.execute(
                "INSERT INTO ai_decision_memory "
                "(timestamp,mode,decisions,raw_decisions,analysis,intel_summary,candidates_count,market_regime,verification_summary,guardrail_summary,execution_plan) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    timestamp or datetime.now().isoformat(),
                    mode,
                    json.dumps(decisions, ensure_ascii=False),
                    json.dumps(raw_decisions or [], ensure_ascii=False),
                    analysis,
                    intel_summary,
                    candidates_count,
                    market_regime,
                    json.dumps(verification_summary or {}, ensure_ascii=False),
                    json.dumps(guardrail_summary or {}, ensure_ascii=False),
                    json.dumps(execution_plan or {}, ensure_ascii=False),
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
            "SELECT id, timestamp, decisions, raw_decisions, execution_plan FROM ai_decision_memory "
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

    def get_recent_calibrated_memories(self, limit: int = 50) -> list[tuple]:
        self.ensure_table()
        conn = RepoCompatConnection()
        rows = conn.execute(
            "SELECT timestamp, mode, actual_results, verification_summary, guardrail_summary, execution_plan "
            "FROM ai_decision_memory WHERE calibrated=1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return rows

    def get_latest_auto_memory(self) -> dict | None:
        self.ensure_table()
        row = get_repo().fetchone(
            "SELECT timestamp, decisions, raw_decisions, analysis, verification_summary, guardrail_summary, execution_plan FROM ai_decision_memory "
            "WHERE mode='auto' ORDER BY id DESC LIMIT 1"
        )
        if not row:
            return None
        decisions = self._load_json(row[1], [])
        raw_decisions = self._load_json(row[2], [])
        return {
            "timestamp": row[0] or "",
            "analysis": row[3] or "",
            "items": decisions if isinstance(decisions, list) else [],
            "raw_items": raw_decisions if isinstance(raw_decisions, list) else [],
            "verification_summary": self._load_json(row[4], {}),
            "guardrail_summary": self._load_json(row[5], {}),
            "execution_plan": self._load_json(row[6], {}),
        }
