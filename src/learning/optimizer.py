"""Hiring optimizer using Thompson sampling for explore/exploit.

Uses AgentScorer reputation data to recommend agents for tasks.
Balances exploitation (hire proven agents) with exploration (try
new or undersampled agents to discover hidden talent).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from src.learning.feedback import FeedbackCollector
from src.learning.scorer import AgentScorer, AgentScore


@dataclass
class AgentRecommendation:
    """A hiring recommendation with confidence interval."""

    agent_id: str
    expected_score: float  # point estimate (0-1)
    confidence_lower: float  # lower bound of 95% CI
    confidence_upper: float  # upper bound of 95% CI
    reason: str  # why this agent was chosen
    is_exploration: bool = False  # True if picked for exploration


class HiringOptimizer:
    """Improves CEO hiring decisions using feedback-driven optimization."""

    def __init__(
        self,
        collector: FeedbackCollector,
        scorer: AgentScorer | None = None,
        exploration_rate: float = 0.15,
        rng_seed: int | None = None,
    ) -> None:
        self._collector = collector
        self._scorer = scorer or AgentScorer(collector)
        self._exploration_rate = exploration_rate
        self._rng = random.Random(rng_seed)

    @property
    def exploration_rate(self) -> float:
        return self._exploration_rate

    @exploration_rate.setter
    def exploration_rate(self, value: float) -> None:
        self._exploration_rate = max(0.0, min(1.0, value))

    def recommend_agent(
        self,
        candidates: list[str],
        skill: str | None = None,
        budget: float | None = None,
    ) -> AgentRecommendation | None:
        """Recommend the best agent from a list of candidates.

        Uses Thompson sampling: with probability ``exploration_rate``, picks
        a random sample from each agent's score distribution instead of
        always picking the highest scorer (exploitation).

        Args:
            candidates: List of agent_id strings to choose from.
            skill: Optional skill filter (not used for filtering here,
                   but included in the recommendation reason).
            budget: Optional budget constraint (USDC).

        Returns:
            AgentRecommendation or None if no candidates.
        """
        if not candidates:
            return None

        # Score all candidates
        scored: list[tuple[str, AgentScore]] = []
        for agent_id in candidates:
            score = self._scorer.compute_score(agent_id)
            scored.append((agent_id, score))

        # Thompson sampling: explore or exploit
        is_exploration = self._rng.random() < self._exploration_rate

        if is_exploration:
            # Explore: sample from Beta distributions for each agent
            sampled = self._thompson_sample(scored)
        else:
            # Exploit: pick the highest composite score
            sampled = sorted(
                scored, key=lambda x: x[1].composite_score, reverse=True
            )

        # Apply budget filter if provided
        if budget is not None:
            filtered = []
            for agent_id, score in sampled:
                feedback = self._collector.get_agent_feedback(agent_id)
                if feedback:
                    avg_cost = sum(f.cost_usdc for f in feedback) / len(feedback)
                    if avg_cost <= budget:
                        filtered.append((agent_id, score))
                else:
                    # Unknown cost — include with caution
                    filtered.append((agent_id, score))
            if filtered:
                sampled = filtered

        if not sampled:
            return None

        best_id, best_score = sampled[0]
        lower, upper = self._confidence_interval(best_score)

        reason_parts = []
        if is_exploration:
            reason_parts.append("exploration pick")
        else:
            reason_parts.append("highest rated")

        if best_score.task_count == 0:
            reason_parts.append("no prior history")
        else:
            reason_parts.append(f"{best_score.task_count} prior tasks")
            reason_parts.append(f"success rate {best_score.success_rate:.0%}")

        if skill:
            reason_parts.append(f"skill: {skill}")

        return AgentRecommendation(
            agent_id=best_id,
            expected_score=best_score.composite_score,
            confidence_lower=round(lower, 4),
            confidence_upper=round(upper, 4),
            reason=", ".join(reason_parts),
            is_exploration=is_exploration,
        )

    def explore_exploit(
        self, candidates: list[str]
    ) -> tuple[str, bool]:
        """Simple explore/exploit decision.

        Returns (agent_id, is_exploration).
        Thompson sampling — occasionally try lower-ranked agents.
        """
        if not candidates:
            raise ValueError("No candidates to choose from")

        scored = [(aid, self._scorer.compute_score(aid)) for aid in candidates]
        is_exploration = self._rng.random() < self._exploration_rate

        if is_exploration:
            sampled = self._thompson_sample(scored)
        else:
            sampled = sorted(
                scored, key=lambda x: x[1].composite_score, reverse=True
            )

        return sampled[0][0], is_exploration

    def _thompson_sample(
        self, scored: list[tuple[str, AgentScore]]
    ) -> list[tuple[str, AgentScore]]:
        """Sample from Beta distribution for each agent and sort by sample.

        Uses the agent's success_rate as the Beta distribution shape.
        Agents with less data have wider distributions, giving them a
        chance to be selected (natural exploration).
        """
        samples: list[tuple[str, AgentScore, float]] = []
        for agent_id, score in scored:
            # Beta distribution parameters from observed successes/failures
            # Use task_count and success_rate, with a weak prior (alpha=1, beta=1)
            alpha = 1.0 + score.success_rate * score.task_count
            beta_param = 1.0 + (1.0 - score.success_rate) * score.task_count
            sample = self._rng.betavariate(alpha, beta_param)
            samples.append((agent_id, score, sample))

        # Sort by Thompson sample (descending)
        samples.sort(key=lambda x: x[2], reverse=True)
        return [(aid, score) for aid, score, _ in samples]

    @staticmethod
    def _confidence_interval(score: AgentScore) -> tuple[float, float]:
        """Compute approximate 95% confidence interval for composite score.

        Uses normal approximation with width inversely proportional to
        sqrt(task_count). Unknown agents get very wide intervals.
        """
        if score.task_count == 0:
            return (0.0, 1.0)

        # Standard error shrinks with more data
        se = 0.5 / math.sqrt(score.task_count)

        lower = max(0.0, score.composite_score - 1.96 * se)
        upper = min(1.0, score.composite_score + 1.96 * se)
        return (round(lower, 4), round(upper, 4))

    def get_rankings(self) -> list[AgentScore]:
        """Get all agent rankings from the scorer."""
        return self._scorer.rank_agents()
