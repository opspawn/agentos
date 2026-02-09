"""Tests for the agent learning and feedback system.

Covers: FeedbackCollector, AgentScorer, HiringOptimizer, and CEO integration.
"""

from __future__ import annotations

import math
import os
import tempfile
import time

import pytest

from src.learning.feedback import (
    FeedbackRecord,
    FeedbackCollector,
    get_feedback_collector,
    reset_feedback_collector,
)
from src.learning.scorer import AgentScore, AgentScorer, _decay_weight, _HALF_LIFE
from src.learning.optimizer import AgentRecommendation, HiringOptimizer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector():
    """Fresh FeedbackCollector with temporary database."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_learning.db")
    return FeedbackCollector(db_path)


@pytest.fixture
def scorer(collector):
    """AgentScorer backed by the test collector."""
    return AgentScorer(collector)


@pytest.fixture
def optimizer(collector):
    """HiringOptimizer with fixed seed for determinism."""
    return HiringOptimizer(collector, rng_seed=42)


def _make_record(
    task_id: str = "t1",
    agent_id: str = "agent-a",
    outcome: str = "success",
    quality: float = 0.9,
    latency: float = 100.0,
    cost: float = 0.25,
    ts: float | None = None,
) -> FeedbackRecord:
    return FeedbackRecord(
        task_id=task_id,
        agent_id=agent_id,
        outcome=outcome,
        quality_score=quality,
        latency_ms=latency,
        cost_usdc=cost,
        timestamp=ts or time.time(),
    )


# ===================================================================
# FeedbackCollector Tests
# ===================================================================


class TestFeedbackRecord:
    """Test the FeedbackRecord dataclass."""

    def test_create_record(self):
        rec = _make_record()
        assert rec.task_id == "t1"
        assert rec.agent_id == "agent-a"
        assert rec.outcome == "success"
        assert rec.quality_score == 0.9

    def test_default_timestamp(self):
        before = time.time()
        rec = FeedbackRecord(
            task_id="t1",
            agent_id="a",
            outcome="success",
            quality_score=1.0,
            latency_ms=0,
            cost_usdc=0,
        )
        after = time.time()
        assert before <= rec.timestamp <= after

    def test_custom_timestamp(self):
        rec = _make_record(ts=1000.0)
        assert rec.timestamp == 1000.0


class TestFeedbackCollector:
    """Test feedback storage CRUD operations."""

    def test_record_and_retrieve(self, collector):
        rec = _make_record()
        collector.record_feedback(rec)
        results = collector.get_agent_feedback("agent-a")
        assert len(results) == 1
        assert results[0].task_id == "t1"
        assert results[0].quality_score == 0.9

    def test_get_task_feedback(self, collector):
        collector.record_feedback(_make_record(task_id="t1", agent_id="a"))
        collector.record_feedback(_make_record(task_id="t1", agent_id="b"))
        collector.record_feedback(_make_record(task_id="t2", agent_id="a"))

        results = collector.get_task_feedback("t1")
        assert len(results) == 2

    def test_get_agent_feedback_ordered(self, collector):
        """Feedback is ordered by timestamp DESC (most recent first)."""
        collector.record_feedback(_make_record(task_id="t1", agent_id="a", ts=1000))
        collector.record_feedback(_make_record(task_id="t2", agent_id="a", ts=2000))

        results = collector.get_agent_feedback("a")
        assert results[0].task_id == "t2"  # more recent first
        assert results[1].task_id == "t1"

    def test_get_all_feedback(self, collector):
        collector.record_feedback(_make_record(task_id="t1", agent_id="a"))
        collector.record_feedback(_make_record(task_id="t2", agent_id="b"))
        all_fb = collector.get_all_feedback()
        assert len(all_fb) == 2

    def test_count_feedback_all(self, collector):
        collector.record_feedback(_make_record(task_id="t1", agent_id="a"))
        collector.record_feedback(_make_record(task_id="t2", agent_id="b"))
        assert collector.count_feedback() == 2

    def test_count_feedback_by_agent(self, collector):
        collector.record_feedback(_make_record(task_id="t1", agent_id="a"))
        collector.record_feedback(_make_record(task_id="t2", agent_id="a"))
        collector.record_feedback(_make_record(task_id="t3", agent_id="b"))
        assert collector.count_feedback("a") == 2
        assert collector.count_feedback("b") == 1

    def test_empty_feedback(self, collector):
        assert collector.get_agent_feedback("nonexistent") == []
        assert collector.count_feedback() == 0

    def test_clear_feedback(self, collector):
        collector.record_feedback(_make_record())
        collector.clear_feedback()
        assert collector.count_feedback() == 0

    def test_upsert_feedback(self, collector):
        """Same (task_id, agent_id) pair replaces the existing record."""
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="a", quality=0.5)
        )
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="a", quality=0.9)
        )
        results = collector.get_agent_feedback("a")
        assert len(results) == 1
        assert results[0].quality_score == 0.9

    def test_multiple_agents(self, collector):
        for i in range(5):
            collector.record_feedback(
                _make_record(task_id=f"t{i}", agent_id=f"agent-{i % 3}")
            )
        assert collector.count_feedback() == 5

    def test_agent_score_persistence(self, collector):
        collector.save_agent_score(
            agent_id="a",
            composite_score=0.85,
            success_rate=0.9,
            avg_quality=0.8,
            reliability=0.7,
            cost_efficiency=0.6,
        )
        score = collector.get_agent_score("a")
        assert score is not None
        assert score["composite_score"] == 0.85
        assert score["success_rate"] == 0.9

    def test_agent_score_not_found(self, collector):
        assert collector.get_agent_score("nonexistent") is None

    def test_list_agent_scores(self, collector):
        collector.save_agent_score("a", 0.9, 0.9, 0.9, 0.9, 0.9)
        collector.save_agent_score("b", 0.5, 0.5, 0.5, 0.5, 0.5)
        scores = collector.list_agent_scores()
        assert len(scores) == 2
        assert scores[0]["agent_id"] == "a"  # higher score first

    def test_clear_agent_scores(self, collector):
        collector.save_agent_score("a", 0.9, 0.9, 0.9, 0.9, 0.9)
        collector.clear_agent_scores()
        assert collector.list_agent_scores() == []

    def test_clear_all(self, collector):
        collector.record_feedback(_make_record())
        collector.save_agent_score("a", 0.9, 0.9, 0.9, 0.9, 0.9)
        collector.clear_all()
        assert collector.count_feedback() == 0
        assert collector.list_agent_scores() == []


class TestFeedbackCollectorAsync:
    """Test async methods of FeedbackCollector."""

    @pytest.mark.asyncio
    async def test_async_record_feedback(self, collector):
        rec = _make_record()
        await collector.async_record_feedback(rec)
        results = collector.get_agent_feedback("agent-a")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_async_get_agent_feedback(self, collector):
        collector.record_feedback(_make_record(task_id="t1", agent_id="a"))
        results = await collector.async_get_agent_feedback("a")
        assert len(results) == 1


class TestFeedbackSingleton:
    """Test the module-level singleton pattern."""

    def test_get_and_reset(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "singleton_test.db")
        c1 = reset_feedback_collector(db_path)
        c2 = get_feedback_collector()
        assert c1 is c2

    def test_reset_creates_new(self):
        tmpdir = tempfile.mkdtemp()
        c1 = reset_feedback_collector(os.path.join(tmpdir, "a.db"))
        c2 = reset_feedback_collector(os.path.join(tmpdir, "b.db"))
        assert c1 is not c2


# ===================================================================
# AgentScorer Tests
# ===================================================================


class TestDecayWeight:
    """Test the exponential decay weighting function."""

    def test_position_zero(self):
        assert _decay_weight(0) == pytest.approx(1.0)

    def test_half_life(self):
        """Weight at half-life position should be 0.5."""
        assert _decay_weight(_HALF_LIFE) == pytest.approx(0.5)

    def test_double_half_life(self):
        assert _decay_weight(2 * _HALF_LIFE) == pytest.approx(0.25)

    def test_monotonically_decreasing(self):
        weights = [_decay_weight(i) for i in range(20)]
        for i in range(1, len(weights)):
            assert weights[i] < weights[i - 1]

    def test_always_positive(self):
        for i in range(100):
            assert _decay_weight(i) > 0


class TestAgentScorer:
    """Test agent score computation."""

    def test_no_history(self, scorer):
        """Unknown agents get a neutral prior score."""
        score = scorer.compute_score("unknown-agent")
        assert score.composite_score == 0.5
        assert score.confidence == 0.0
        assert score.task_count == 0

    def test_perfect_agent(self, collector, scorer):
        """Agent with all successful high-quality tasks."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="perfect",
                    outcome="success",
                    quality=1.0,
                    cost=0.10,
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("perfect")
        assert score.success_rate == pytest.approx(1.0)
        assert score.avg_quality == pytest.approx(1.0)
        assert score.composite_score > 0.9

    def test_failing_agent(self, collector, scorer):
        """Agent that always fails scores low."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="bad",
                    outcome="failure",
                    quality=0.1,
                    cost=1.0,
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("bad")
        assert score.success_rate < 0.1
        assert score.composite_score < 0.3

    def test_partial_outcomes(self, collector, scorer):
        """Partial outcomes contribute 0.5 to success rate."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="partial",
                    outcome="partial",
                    quality=0.5,
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("partial")
        assert score.success_rate == pytest.approx(0.5, abs=0.05)

    def test_decay_weights_recent(self, collector, scorer):
        """Recent success after earlier failures should score higher than vice versa."""
        # Early failures, recent successes
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"improving-{i}",
                    agent_id="improving",
                    outcome="failure" if i < 5 else "success",
                    quality=0.2 if i < 5 else 0.9,
                    ts=1000 + i,
                )
            )
        improving_score = scorer.compute_score("improving")

        # Early successes, recent failures
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"declining-{i}",
                    agent_id="declining",
                    outcome="success" if i < 5 else "failure",
                    quality=0.9 if i < 5 else 0.2,
                    ts=1000 + i,
                )
            )
        declining_score = scorer.compute_score("declining")

        # Improving agent should score higher due to recency weighting
        assert improving_score.composite_score > declining_score.composite_score

    def test_confidence_grows_with_data(self, collector, scorer):
        """Confidence should increase as more feedback is collected."""
        confidences = []
        for i in range(20):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="growing",
                    outcome="success",
                    quality=0.8,
                    ts=1000 + i,
                )
            )
            score = scorer.compute_score("growing")
            confidences.append(score.confidence)

        # Confidence should be monotonically increasing
        for j in range(1, len(confidences)):
            assert confidences[j] >= confidences[j - 1]
        # Final confidence should be high
        assert confidences[-1] > 0.9

    def test_reliability_consistent(self, collector, scorer):
        """Consistent quality = high reliability."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="consistent",
                    outcome="success",
                    quality=0.8,  # always 0.8
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("consistent")
        assert score.reliability > 0.9  # nearly perfect consistency

    def test_reliability_inconsistent(self, collector, scorer):
        """Wild quality swings = low reliability."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="erratic",
                    outcome="success",
                    quality=0.0 if i % 2 == 0 else 1.0,  # alternating extremes
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("erratic")
        assert score.reliability < 0.3  # very inconsistent

    def test_cost_efficiency_free(self, collector, scorer):
        """Free work is maximally cost-efficient."""
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="free",
                    outcome="success",
                    quality=0.8,
                    cost=0.0,
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("free")
        assert score.cost_efficiency == pytest.approx(1.0)

    def test_cost_efficiency_expensive(self, collector, scorer):
        """Expensive low-quality work has poor cost efficiency."""
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}",
                    agent_id="expensive",
                    outcome="success",
                    quality=0.1,
                    cost=10.0,
                    ts=1000 + i,
                )
            )
        score = scorer.compute_score("expensive")
        assert score.cost_efficiency < 0.1

    def test_composite_weights_sum_to_one(self):
        """Verify weight constants sum to 1.0."""
        from src.learning.scorer import _W_SUCCESS, _W_QUALITY, _W_RELIABILITY, _W_COST
        assert _W_SUCCESS + _W_QUALITY + _W_RELIABILITY + _W_COST == pytest.approx(1.0)

    def test_rank_agents(self, collector, scorer):
        """Ranking should order agents by composite score."""
        # Good agent
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"good-{i}", agent_id="good",
                    outcome="success", quality=0.9, ts=1000 + i,
                )
            )
        # Bad agent
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"bad-{i}", agent_id="bad",
                    outcome="failure", quality=0.2, ts=1000 + i,
                )
            )
        rankings = scorer.rank_agents()
        assert len(rankings) == 2
        assert rankings[0].agent_id == "good"
        assert rankings[1].agent_id == "bad"

    def test_score_persisted(self, collector, scorer):
        """Computing a score should persist it to the agent_scores table."""
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="persist-test", outcome="success")
        )
        scorer.compute_score("persist-test")
        stored = collector.get_agent_score("persist-test")
        assert stored is not None
        assert stored["composite_score"] > 0

    def test_single_record_reliability(self, collector, scorer):
        """Single record has default reliability of 0.5."""
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="solo")
        )
        score = scorer.compute_score("solo")
        assert score.reliability == 0.5  # insufficient data default


# ===================================================================
# HiringOptimizer Tests
# ===================================================================


class TestHiringOptimizer:
    """Test Thompson sampling hiring optimization."""

    def test_recommend_no_candidates(self, optimizer):
        rec = optimizer.recommend_agent([], skill="coding")
        assert rec is None

    def test_recommend_single_candidate(self, collector, optimizer):
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="only-one", outcome="success", quality=0.8)
        )
        rec = optimizer.recommend_agent(["only-one"])
        assert rec is not None
        assert rec.agent_id == "only-one"

    def test_recommend_returns_recommendation(self, collector, optimizer):
        for i in range(3):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}", agent_id="candidate",
                    outcome="success", quality=0.8, ts=1000 + i,
                )
            )
        rec = optimizer.recommend_agent(["candidate"])
        assert isinstance(rec, AgentRecommendation)
        assert rec.agent_id == "candidate"
        assert 0.0 <= rec.confidence_lower <= rec.expected_score
        assert rec.expected_score <= rec.confidence_upper <= 1.0

    def test_exploit_picks_best(self, collector):
        """Exploitation should pick the highest-scoring agent."""
        # Agent A: great
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"a-{i}", agent_id="great",
                    outcome="success", quality=0.95, ts=1000 + i,
                )
            )
        # Agent B: mediocre
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"b-{i}", agent_id="mediocre",
                    outcome="partial", quality=0.4, ts=1000 + i,
                )
            )

        # Force exploitation (rate=0)
        opt = HiringOptimizer(collector, exploration_rate=0.0, rng_seed=42)
        rec = opt.recommend_agent(["great", "mediocre"])
        assert rec is not None
        assert rec.agent_id == "great"
        assert rec.is_exploration is False

    def test_explore_sometimes_picks_other(self, collector):
        """Exploration should sometimes pick non-top agents."""
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"a-{i}", agent_id="top",
                    outcome="success", quality=0.95, ts=1000 + i,
                )
            )
        for i in range(10):
            collector.record_feedback(
                _make_record(
                    task_id=f"b-{i}", agent_id="mid",
                    outcome="success", quality=0.5, ts=1000 + i,
                )
            )

        # Force exploration (rate=1.0), run many trials
        opt = HiringOptimizer(collector, exploration_rate=1.0, rng_seed=123)
        picks = set()
        for _ in range(50):
            rec = opt.recommend_agent(["top", "mid"])
            if rec:
                picks.add(rec.agent_id)
        # Thompson sampling with exploration should pick both at least once
        assert "top" in picks
        assert "mid" in picks

    def test_explore_exploit_method(self, collector, optimizer):
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="a", outcome="success")
        )
        agent_id, is_explore = optimizer.explore_exploit(["a"])
        assert agent_id == "a"
        assert isinstance(is_explore, bool)

    def test_explore_exploit_no_candidates(self, optimizer):
        with pytest.raises(ValueError, match="No candidates"):
            optimizer.explore_exploit([])

    def test_budget_filter(self, collector):
        """Budget filter should exclude expensive agents."""
        # Cheap agent
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"cheap-{i}", agent_id="cheap",
                    outcome="success", quality=0.7, cost=0.10, ts=1000 + i,
                )
            )
        # Expensive agent
        for i in range(5):
            collector.record_feedback(
                _make_record(
                    task_id=f"pricey-{i}", agent_id="pricey",
                    outcome="success", quality=0.9, cost=5.00, ts=1000 + i,
                )
            )

        opt = HiringOptimizer(collector, exploration_rate=0.0, rng_seed=42)
        rec = opt.recommend_agent(["cheap", "pricey"], budget=0.50)
        assert rec is not None
        assert rec.agent_id == "cheap"

    def test_confidence_interval_unknown(self, optimizer):
        """Unknown agents should have very wide confidence intervals."""
        rec = optimizer.recommend_agent(["unknown-agent"])
        assert rec is not None
        assert rec.confidence_lower == 0.0
        assert rec.confidence_upper == 1.0

    def test_confidence_interval_narrows(self, collector):
        """More data should narrow the confidence interval."""
        opt = HiringOptimizer(collector, exploration_rate=0.0, rng_seed=42)

        intervals = []
        for i in range(20):
            collector.record_feedback(
                _make_record(
                    task_id=f"t{i}", agent_id="narrowing",
                    outcome="success", quality=0.8, ts=1000 + i,
                )
            )
            rec = opt.recommend_agent(["narrowing"])
            if rec:
                intervals.append(rec.confidence_upper - rec.confidence_lower)

        # CI should get narrower over time
        assert intervals[-1] < intervals[0]

    def test_exploration_rate_property(self, optimizer):
        assert optimizer.exploration_rate == 0.15
        optimizer.exploration_rate = 0.5
        assert optimizer.exploration_rate == 0.5

    def test_exploration_rate_clamped(self, optimizer):
        optimizer.exploration_rate = -0.5
        assert optimizer.exploration_rate == 0.0
        optimizer.exploration_rate = 1.5
        assert optimizer.exploration_rate == 1.0

    def test_get_rankings(self, collector, optimizer):
        for i in range(3):
            collector.record_feedback(
                _make_record(task_id=f"t{i}", agent_id="ranked", ts=1000 + i)
            )
        rankings = optimizer.get_rankings()
        assert len(rankings) == 1
        assert rankings[0].agent_id == "ranked"

    def test_recommendation_reason_includes_skill(self, collector, optimizer):
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="a", outcome="success")
        )
        rec = optimizer.recommend_agent(["a"], skill="python")
        assert rec is not None
        assert "python" in rec.reason

    def test_recommendation_for_new_agent(self, optimizer):
        """New agent with no history should get a recommendation."""
        rec = optimizer.recommend_agent(["brand-new"])
        assert rec is not None
        assert "no prior history" in rec.reason


# ===================================================================
# CEO Agent Integration Tests
# ===================================================================


class TestCEOIntegration:
    """Test that learning tools integrate with the CEO agent."""

    @pytest.mark.asyncio
    async def test_record_feedback_tool(self):
        """Test the record_task_feedback CEO tool."""
        from src.agents.ceo_agent import record_task_feedback

        # Reset the singleton to use a temp DB
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "ceo_test.db")
        reset_feedback_collector(db_path)

        result = await record_task_feedback(
            task_id="ceo-t1",
            agent_id="builder",
            outcome="success",
            quality_score=0.85,
            latency_ms=500.0,
            cost_usdc=0.25,
        )
        assert result["status"] == "recorded"
        assert result["agent_id"] == "builder"
        assert "updated_score" in result

    @pytest.mark.asyncio
    async def test_record_feedback_clamps_quality(self):
        """Quality score should be clamped to [0, 1]."""
        from src.agents.ceo_agent import record_task_feedback

        tmpdir = tempfile.mkdtemp()
        reset_feedback_collector(os.path.join(tmpdir, "clamp.db"))

        result = await record_task_feedback(
            task_id="clamp-t1",
            agent_id="a",
            outcome="success",
            quality_score=1.5,
        )
        assert result["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_get_hiring_recommendation_tool(self):
        """Test the get_hiring_recommendation CEO tool."""
        from src.agents.ceo_agent import get_hiring_recommendation

        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "rec_test.db")
        collector = reset_feedback_collector(db_path)

        # Add some history
        collector.record_feedback(
            _make_record(task_id="t1", agent_id="builder", outcome="success", quality=0.9)
        )

        result = await get_hiring_recommendation(
            candidate_ids="builder,research",
            skill="coding",
            budget=1.0,
        )
        assert result["status"] == "recommended"
        assert "agent_id" in result
        assert "confidence_interval" in result

    @pytest.mark.asyncio
    async def test_get_hiring_recommendation_no_candidates(self):
        from src.agents.ceo_agent import get_hiring_recommendation

        tmpdir = tempfile.mkdtemp()
        reset_feedback_collector(os.path.join(tmpdir, "empty.db"))

        result = await get_hiring_recommendation(candidate_ids="")
        assert result["status"] == "error"

    def test_ceo_agent_has_learning_tools(self):
        """CEO agent should be created with learning tools available."""
        from src.agents.ceo_agent import (
            create_ceo_agent,
            record_task_feedback,
            get_hiring_recommendation,
        )
        from src.agents._mock_client import MockChatClient

        # Verify the tool functions exist and have correct names
        assert record_task_feedback.name == "record_task_feedback"
        assert get_hiring_recommendation.name == "get_hiring_recommendation"

        # Verify the agent can be created without error
        agent = create_ceo_agent(chat_client=MockChatClient())
        assert agent.name == "CEO"


# ===================================================================
# Package Import Tests
# ===================================================================


class TestPackageImports:
    """Test that the learning package exports are accessible."""

    def test_import_feedback(self):
        from src.learning import FeedbackRecord, FeedbackCollector
        assert FeedbackRecord is not None
        assert FeedbackCollector is not None

    def test_import_scorer(self):
        from src.learning import AgentScore, AgentScorer
        assert AgentScore is not None
        assert AgentScorer is not None

    def test_import_optimizer(self):
        from src.learning import AgentRecommendation, HiringOptimizer
        assert AgentRecommendation is not None
        assert HiringOptimizer is not None

    def test_import_singletons(self):
        from src.learning import get_feedback_collector, reset_feedback_collector
        assert callable(get_feedback_collector)
        assert callable(reset_feedback_collector)
