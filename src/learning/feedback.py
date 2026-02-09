"""Feedback collection and storage for agent learning.

Records task outcomes, quality scores, and cost data so the CEO agent
can learn from past hiring decisions and improve future ones.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass
class FeedbackRecord:
    """A single feedback entry for a completed task."""

    task_id: str
    agent_id: str
    outcome: str  # "success" | "partial" | "failure"
    quality_score: float  # 0.0 - 1.0
    latency_ms: float
    cost_usdc: float
    timestamp: float = field(default_factory=time.time)


_FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    quality_score REAL NOT NULL,
    latency_ms REAL NOT NULL,
    cost_usdc REAL NOT NULL,
    timestamp REAL NOT NULL,
    PRIMARY KEY (task_id, agent_id)
);

CREATE TABLE IF NOT EXISTS agent_scores (
    agent_id TEXT PRIMARY KEY,
    composite_score REAL NOT NULL DEFAULT 0.0,
    success_rate REAL NOT NULL DEFAULT 0.0,
    avg_quality REAL NOT NULL DEFAULT 0.0,
    reliability REAL NOT NULL DEFAULT 0.0,
    cost_efficiency REAL NOT NULL DEFAULT 0.0,
    updated_at REAL NOT NULL
);
"""


class FeedbackCollector:
    """Collects and persists agent feedback in SQLite (WAL mode)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        default = Path(
            os.environ.get("AGENTOS_DB_PATH", "")
            or str(Path(__file__).resolve().parent.parent.parent / "data" / "agentos.db")
        )
        self._db_path = str(db_path or default)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(_FEEDBACK_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Record feedback
    # ------------------------------------------------------------------

    def record_feedback(self, record: FeedbackRecord) -> None:
        """Store a feedback record."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO feedback
                   (task_id, agent_id, outcome, quality_score, latency_ms, cost_usdc, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.task_id,
                    record.agent_id,
                    record.outcome,
                    record.quality_score,
                    record.latency_ms,
                    record.cost_usdc,
                    record.timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Query feedback
    # ------------------------------------------------------------------

    def get_agent_feedback(self, agent_id: str) -> list[FeedbackRecord]:
        """Get all feedback for a specific agent, ordered by timestamp desc."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback WHERE agent_id = ? ORDER BY timestamp DESC",
                (agent_id,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_task_feedback(self, task_id: str) -> list[FeedbackRecord]:
        """Get all feedback for a specific task."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback WHERE task_id = ? ORDER BY timestamp DESC",
                (task_id,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_all_feedback(self) -> list[FeedbackRecord]:
        """Get all feedback records."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM feedback ORDER BY timestamp DESC"
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def count_feedback(self, agent_id: str | None = None) -> int:
        """Count feedback records, optionally filtered by agent."""
        conn = self._get_conn()
        try:
            if agent_id is not None:
                row = conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE agent_id = ?", (agent_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()
            return row[0]
        finally:
            conn.close()

    def clear_feedback(self) -> None:
        """Delete all feedback (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM feedback")
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Agent score persistence
    # ------------------------------------------------------------------

    def save_agent_score(
        self,
        agent_id: str,
        composite_score: float,
        success_rate: float,
        avg_quality: float,
        reliability: float,
        cost_efficiency: float,
    ) -> None:
        """Save or update an agent's computed score."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO agent_scores
                   (agent_id, composite_score, success_rate, avg_quality,
                    reliability, cost_efficiency, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    composite_score,
                    success_rate,
                    avg_quality,
                    reliability,
                    cost_efficiency,
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_agent_score(self, agent_id: str) -> dict[str, Any] | None:
        """Get a cached agent score."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM agent_scores WHERE agent_id = ?", (agent_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    def list_agent_scores(self) -> list[dict[str, Any]]:
        """List all agent scores ordered by composite score desc."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_scores ORDER BY composite_score DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def clear_agent_scores(self) -> None:
        """Delete all agent scores (for testing)."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM agent_scores")
            conn.commit()
        finally:
            conn.close()

    def clear_all(self) -> None:
        """Clear all learning data (for testing)."""
        self.clear_feedback()
        self.clear_agent_scores()

    # ------------------------------------------------------------------
    # Async wrappers
    # ------------------------------------------------------------------

    async def async_record_feedback(self, record: FeedbackRecord) -> None:
        """Async version of record_feedback."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """INSERT OR REPLACE INTO feedback
                   (task_id, agent_id, outcome, quality_score, latency_ms, cost_usdc, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.task_id,
                    record.agent_id,
                    record.outcome,
                    record.quality_score,
                    record.latency_ms,
                    record.cost_usdc,
                    record.timestamp,
                ),
            )
            await db.commit()

    async def async_get_agent_feedback(self, agent_id: str) -> list[FeedbackRecord]:
        """Async version of get_agent_feedback."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            cursor = await db.execute(
                "SELECT * FROM feedback WHERE agent_id = ? ORDER BY timestamp DESC",
                (agent_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row | aiosqlite.Row) -> FeedbackRecord:
        return FeedbackRecord(
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            outcome=row["outcome"],
            quality_score=row["quality_score"],
            latency_ms=row["latency_ms"],
            cost_usdc=row["cost_usdc"],
            timestamp=row["timestamp"],
        )


# Module-level singleton
_collector: FeedbackCollector | None = None


def get_feedback_collector(db_path: str | Path | None = None) -> FeedbackCollector:
    """Get or create the global FeedbackCollector instance."""
    global _collector
    if _collector is None:
        _collector = FeedbackCollector(db_path)
    return _collector


def reset_feedback_collector(db_path: str | Path | None = None) -> FeedbackCollector:
    """Reset the global FeedbackCollector (for testing)."""
    global _collector
    _collector = FeedbackCollector(db_path)
    return _collector
