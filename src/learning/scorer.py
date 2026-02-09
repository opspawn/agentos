"""Agent scoring system with exponential decay weighting.

Computes composite agent reputation scores from feedback history.
Recent tasks are weighted higher using exponential decay (half-life = 10 tasks).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from src.learning.feedback import FeedbackCollector, FeedbackRecord


@dataclass
class AgentScore:
    """Computed reputation score for an agent."""

    agent_id: str
    composite_score: float  # 0.0 - 1.0 weighted blend
    success_rate: float  # 0.0 - 1.0
    avg_quality: float  # 0.0 - 1.0
    reliability: float  # 0.0 - 1.0 (consistency)
    cost_efficiency: float  # 0.0 - 1.0
    task_count: int = 0
    confidence: float = 0.0  # 0.0 - 1.0 (how much data we have)


# Composite score weights
_W_SUCCESS = 0.40
_W_QUALITY = 0.30
_W_RELIABILITY = 0.20
_W_COST = 0.10

# Exponential decay half-life (in number of tasks)
_HALF_LIFE = 10


def _decay_weight(position: int) -> float:
    """Exponential decay weight for a task at the given position.

    Position 0 = most recent task (weight ~ 1.0).
    Weight halves every ``_HALF_LIFE`` positions.
    """
    return math.pow(0.5, position / _HALF_LIFE)


class AgentScorer:
    """Computes agent reputation from feedback history."""

    def __init__(self, collector: FeedbackCollector) -> None:
        self._collector = collector

    def compute_score(self, agent_id: str) -> AgentScore:
        """Compute composite score for an agent from feedback history.

        Feedback records are ordered by timestamp descending (most recent first).
        Each record gets an exponential decay weight based on position.
        """
        records = self._collector.get_agent_feedback(agent_id)

        if not records:
            return AgentScore(
                agent_id=agent_id,
                composite_score=0.5,  # prior for unknown agents
                success_rate=0.5,
                avg_quality=0.5,
                reliability=0.5,
                cost_efficiency=0.5,
                task_count=0,
                confidence=0.0,
            )

        # Compute weighted metrics with decay
        success_rate = self._weighted_success_rate(records)
        avg_quality = self._weighted_avg_quality(records)
        reliability = self._compute_reliability(records)
        cost_efficiency = self._compute_cost_efficiency(records)

        composite = (
            _W_SUCCESS * success_rate
            + _W_QUALITY * avg_quality
            + _W_RELIABILITY * reliability
            + _W_COST * cost_efficiency
        )

        # Confidence grows with number of tasks (asymptotic to 1.0)
        confidence = 1.0 - math.exp(-len(records) / 5.0)

        score = AgentScore(
            agent_id=agent_id,
            composite_score=round(composite, 4),
            success_rate=round(success_rate, 4),
            avg_quality=round(avg_quality, 4),
            reliability=round(reliability, 4),
            cost_efficiency=round(cost_efficiency, 4),
            task_count=len(records),
            confidence=round(confidence, 4),
        )

        # Persist the score
        self._collector.save_agent_score(
            agent_id=agent_id,
            composite_score=score.composite_score,
            success_rate=score.success_rate,
            avg_quality=score.avg_quality,
            reliability=score.reliability,
            cost_efficiency=score.cost_efficiency,
        )

        return score

    def rank_agents(self, skill: str | None = None) -> list[AgentScore]:
        """Rank all agents by composite score.

        If ``skill`` is provided, only agents matching that skill in their
        feedback history are included (matched via agent_id prefix or stored
        agent metadata). For now, ranks all agents with feedback.
        """
        # Gather unique agent IDs from feedback
        all_feedback = self._collector.get_all_feedback()
        agent_ids = sorted({r.agent_id for r in all_feedback})

        scores = [self.compute_score(aid) for aid in agent_ids]
        scores.sort(key=lambda s: s.composite_score, reverse=True)
        return scores

    # ------------------------------------------------------------------
    # Metric computations
    # ------------------------------------------------------------------

    @staticmethod
    def _weighted_success_rate(records: list[FeedbackRecord]) -> float:
        """Success rate weighted by recency decay."""
        total_weight = 0.0
        success_weight = 0.0
        for i, rec in enumerate(records):
            w = _decay_weight(i)
            total_weight += w
            if rec.outcome == "success":
                success_weight += w
            elif rec.outcome == "partial":
                success_weight += w * 0.5
            # failure = 0
        return success_weight / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def _weighted_avg_quality(records: list[FeedbackRecord]) -> float:
        """Quality score weighted by recency decay."""
        total_weight = 0.0
        quality_sum = 0.0
        for i, rec in enumerate(records):
            w = _decay_weight(i)
            total_weight += w
            quality_sum += w * rec.quality_score
        return quality_sum / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def _compute_reliability(records: list[FeedbackRecord]) -> float:
        """Reliability = 1 - stddev(quality_scores) normalized.

        A reliable agent has consistent quality. High variance = low reliability.
        """
        if len(records) < 2:
            return 0.5  # insufficient data

        qualities = [r.quality_score for r in records]
        mean = sum(qualities) / len(qualities)
        variance = sum((q - mean) ** 2 for q in qualities) / len(qualities)
        stddev = math.sqrt(variance)

        # Normalize: stddev of 0.5 (max for 0-1 range) maps to reliability 0
        # stddev of 0 maps to reliability 1
        reliability = max(0.0, 1.0 - 2.0 * stddev)
        return reliability

    @staticmethod
    def _compute_cost_efficiency(records: list[FeedbackRecord]) -> float:
        """Cost efficiency: quality per dollar, normalized to 0-1.

        Higher quality per dollar = better efficiency.
        Uses exponential decay weighting for recency.
        """
        total_weight = 0.0
        efficiency_sum = 0.0
        for i, rec in enumerate(records):
            w = _decay_weight(i)
            total_weight += w
            if rec.cost_usdc > 0:
                # Quality per dollar, capped at 10 (for $0.10 tasks with quality 1.0)
                qpd = min(rec.quality_score / rec.cost_usdc, 10.0)
                # Normalize to 0-1 range (10 qpd = 1.0 efficiency)
                efficiency_sum += w * (qpd / 10.0)
            else:
                # Free work is maximally efficient
                efficiency_sum += w * 1.0
        return efficiency_sum / total_weight if total_weight > 0 else 0.5
