"""Agent Marketplace — discovery, registration, and skill matching.

Provides a marketplace for agents to register their capabilities and pricing,
and for hiring agents to discover and select the best match for a task.

Key components:
- AgentListing: Describes an agent's capabilities and pricing
- MarketplaceRegistry: CRUD operations for agent listings
- SkillMatcher: Match agents to task requirements using skill tags
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AgentListing:
    """Describes an agent available in the marketplace."""

    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:12]}")
    name: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    pricing_model: str = "per-task"  # "per-task" or "per-token"
    price_per_unit: float = 0.0  # USDC per task or per 1K tokens
    rating: float = 0.0  # 0.0 - 5.0
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_earnings: float = 0.0
    availability: str = "available"  # "available", "busy", "offline"
    endpoint: str = ""
    protocol: str = "a2a"
    registered_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def price_display(self) -> str:
        unit = "task" if self.pricing_model == "per-task" else "1K tokens"
        return f"${self.price_per_unit:.4f}/{unit}"

    @property
    def completion_rate(self) -> float:
        """Task completion rate (0.0-1.0). Returns 0 if no jobs."""
        if self.total_jobs == 0:
            return 0.0
        return self.completed_jobs / self.total_jobs

    def matches_skill(self, skill: str) -> bool:
        skill_lower = skill.lower()
        return any(skill_lower in s.lower() for s in self.skills)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["completion_rate"] = self.completion_rate
        return d


class MarketplaceRegistry:
    """Registry of agent listings in the marketplace."""

    def __init__(self) -> None:
        self._listings: dict[str, AgentListing] = {}

    def register_agent(self, listing: AgentListing) -> AgentListing:
        """Register an agent in the marketplace. Returns the listing."""
        self._listings[listing.agent_id] = listing
        return listing

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent listing. Returns True if it existed."""
        return self._listings.pop(agent_id, None) is not None

    def get_agent(self, agent_id: str) -> AgentListing | None:
        """Get an agent listing by ID."""
        return self._listings.get(agent_id)

    def get_agent_by_name(self, name: str) -> AgentListing | None:
        """Get an agent listing by name."""
        for listing in self._listings.values():
            if listing.name == name:
                return listing
        return None

    def discover_agents(self, skill_query: str, max_price: float | None = None) -> list[AgentListing]:
        """Discover agents matching a skill query, optionally filtered by price."""
        query_lower = skill_query.lower()
        results = []
        for listing in self._listings.values():
            if (
                query_lower in listing.name.lower()
                or query_lower in listing.description.lower()
                or any(query_lower in s.lower() for s in listing.skills)
            ):
                if max_price is not None and listing.price_per_unit > max_price:
                    continue
                results.append(listing)
        return results

    def list_all(self) -> list[AgentListing]:
        """Return all listings."""
        return list(self._listings.values())

    def count(self) -> int:
        """Return total number of listings."""
        return len(self._listings)

    def update_rating(self, agent_id: str, new_rating: float) -> bool:
        """Update an agent's rating. Returns False if agent not found."""
        listing = self._listings.get(agent_id)
        if listing is None:
            return False
        listing.rating = max(0.0, min(5.0, new_rating))
        return True

    def increment_jobs(self, agent_id: str) -> bool:
        """Increment an agent's completed job count."""
        listing = self._listings.get(agent_id)
        if listing is None:
            return False
        listing.total_jobs += 1
        return True

    def record_job_completion(self, agent_id: str, success: bool, earnings: float = 0.0) -> bool:
        """Record a job outcome for an agent (updates reputation metrics)."""
        listing = self._listings.get(agent_id)
        if listing is None:
            return False
        listing.total_jobs += 1
        if success:
            listing.completed_jobs += 1
            listing.total_earnings += earnings
        else:
            listing.failed_jobs += 1
        return True

    def update_agent_rating(self, agent_id: str, new_rating: float) -> bool:
        """Update an agent's rating using rolling average."""
        listing = self._listings.get(agent_id)
        if listing is None:
            return False
        if listing.total_jobs <= 1:
            listing.rating = max(0.0, min(5.0, new_rating))
        else:
            # Rolling average weighted toward new rating
            listing.rating = max(0.0, min(5.0, (listing.rating * 0.7 + new_rating * 0.3)))
        return True

    def set_availability(self, agent_id: str, status: str) -> bool:
        """Set an agent's availability status."""
        if status not in ("available", "busy", "offline"):
            return False
        listing = self._listings.get(agent_id)
        if listing is None:
            return False
        listing.availability = status
        return True

    def list_available(self) -> list[AgentListing]:
        """Return only available agents."""
        return [a for a in self._listings.values() if a.availability == "available"]

    def sort_by_price(self, ascending: bool = True) -> list[AgentListing]:
        """Return all listings sorted by price."""
        return sorted(self._listings.values(), key=lambda a: a.price_per_unit, reverse=not ascending)

    def sort_by_rating(self) -> list[AgentListing]:
        """Return all listings sorted by rating (highest first)."""
        return sorted(self._listings.values(), key=lambda a: a.rating, reverse=True)

    def get_reputation(self, agent_id: str) -> dict[str, Any] | None:
        """Get full reputation profile for an agent."""
        listing = self._listings.get(agent_id)
        if listing is None:
            return None
        return {
            "agent_id": listing.agent_id,
            "name": listing.name,
            "rating": listing.rating,
            "total_jobs": listing.total_jobs,
            "completed_jobs": listing.completed_jobs,
            "failed_jobs": listing.failed_jobs,
            "completion_rate": listing.completion_rate,
            "total_earnings": listing.total_earnings,
            "availability": listing.availability,
        }

    def clear(self) -> None:
        """Remove all listings."""
        self._listings.clear()


class SkillMatcher:
    """Matches agents to task requirements using skill overlap scoring."""

    def __init__(self, registry: MarketplaceRegistry) -> None:
        self._registry = registry

    def match(
        self,
        required_skills: list[str],
        min_rating: float = 0.0,
        max_price: float | None = None,
        top_n: int = 5,
    ) -> list[tuple[AgentListing, float]]:
        """Find agents matching required skills, ranked by match score.

        Returns list of (listing, score) tuples sorted by score descending.
        Score is the fraction of required skills the agent has (0.0-1.0),
        with a small bonus for rating.
        """
        if not required_skills:
            # If no skills required, return all (sorted by rating)
            all_agents = self._registry.list_all()
            if max_price is not None:
                all_agents = [a for a in all_agents if a.price_per_unit <= max_price]
            all_agents = [a for a in all_agents if a.rating >= min_rating]
            scored = [(a, 1.0 + a.rating / 100) for a in all_agents]
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_n]

        required_lower = [s.lower() for s in required_skills]
        scored: list[tuple[AgentListing, float]] = []

        for listing in self._registry.list_all():
            if listing.rating < min_rating:
                continue
            if max_price is not None and listing.price_per_unit > max_price:
                continue

            agent_skills_lower = [s.lower() for s in listing.skills]
            overlap = sum(
                1 for req in required_lower
                if any(req in ask for ask in agent_skills_lower)
            )
            base_score = overlap / len(required_skills)
            # Small bonus for rating (max 0.05 boost)
            rating_bonus = listing.rating / 100.0
            score = base_score + rating_bonus

            if base_score > 0:
                scored.append((listing, round(score, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]

    def best_match(
        self,
        required_skills: list[str],
        min_rating: float = 0.0,
        max_price: float | None = None,
    ) -> tuple[AgentListing, float] | None:
        """Return the single best matching agent, or None."""
        matches = self.match(required_skills, min_rating, max_price, top_n=1)
        return matches[0] if matches else None


# Module-level singleton
marketplace = MarketplaceRegistry()

__all__ = [
    "AgentListing",
    "MarketplaceRegistry",
    "SkillMatcher",
    "marketplace",
]
