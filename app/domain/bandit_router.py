"""Contextual Bandit Adaptive Routing Engine with reinforcement feedback from historical telemetry."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from app.core.logging import get_logger
from app.domain.registry import ModelMetadata

logger = get_logger("bandit_router")


@dataclass
class ArmStatistics:
    category: str
    model_alias: str
    trials: int = 0
    successes: int = 0
    total_reward: float = 0.0
    avg_reward: float = 0.50
    avg_latency_ms: float = 100.0
    avg_cost: float = 0.0005
    last_updated: float = field(default_factory=time.time)

    def ucb_score(self, total_category_trials: int, exploration_weight: float = 1.0) -> float:
        """Calculates Upper Confidence Bound (UCB1) for exploration/exploitation balance."""
        if self.trials == 0:
            return float("inf")  # Unexplored arms have infinite priority
        exploitation = self.avg_reward
        exploration = exploration_weight * math.sqrt((2.0 * math.log(max(1, total_category_trials))) / self.trials)
        return exploitation + exploration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "model_alias": self.model_alias,
            "trials": self.trials,
            "successes": self.successes,
            "success_rate": round(self.successes / max(1, self.trials), 4),
            "avg_reward": round(self.avg_reward, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "avg_cost": round(self.avg_cost, 6),
            "last_updated": self.last_updated,
        }


class ContextualBanditRouter:
    """Adaptive model selector that learns reward distributions per task category."""

    def __init__(
        self,
        epsilon: float = 0.10,
        min_sample_threshold: int = 3,
        exploration_weight: float = 0.75,
        decay_factor: float = 0.99,
        enabled: bool = True,
    ):
        self.epsilon = epsilon
        self.min_sample_threshold = min_sample_threshold
        self.exploration_weight = exploration_weight
        self.decay_factor = decay_factor
        self.enabled = enabled
        self._arms: Dict[Tuple[str, str], ArmStatistics] = {}

    def get_arm(self, category: str, model_alias: str) -> ArmStatistics:
        key = (category, model_alias)
        if key not in self._arms:
            self._arms[key] = ArmStatistics(category=category, model_alias=model_alias)
        return self._arms[key]

    def select_model(
        self,
        category: str,
        eligible_models: List[ModelMetadata],
        deterministic_fallback_alias: str,
    ) -> Tuple[ModelMetadata, str, float]:
        """Selects optimal model among eligible candidates using UCB1 / Epsilon-Greedy bandit.

        Returns (Selected Model, Selection Reason, Expected Reward / Confidence).
        """
        if not self.enabled or not eligible_models:
            fallback = next((m for m in eligible_models if m.alias == deterministic_fallback_alias), eligible_models[0])
            return fallback, "DETERMINISTIC_BASELINE", 0.70

        total_cat_trials = sum(
            self.get_arm(category, m.alias).trials for m in eligible_models
        )

        # 1. Minimum Sample Guarantee: Explore any eligible model with trials < min_sample_threshold
        unexplored = [
            m for m in eligible_models
            if self.get_arm(category, m.alias).trials < self.min_sample_threshold
        ]
        if unexplored:
            chosen = random.choice(unexplored)
            arm = self.get_arm(category, chosen.alias)
            return chosen, f"BANDIT_COLD_START_EXPLORE ({arm.trials}/{self.min_sample_threshold} trials)", 0.60

        # 2. Epsilon Exploration: With probability epsilon, explore random eligible model
        if random.random() < self.epsilon:
            chosen = random.choice(eligible_models)
            arm = self.get_arm(category, chosen.alias)
            return chosen, "BANDIT_EPSILON_EXPLORATION", arm.avg_reward

        # 3. Exploitation via UCB1 Upper Confidence Bound
        best_model = None
        highest_score = -float("inf")

        for m in eligible_models:
            arm = self.get_arm(category, m.alias)
            score = arm.ucb_score(total_cat_trials, self.exploration_weight)
            if score > highest_score:
                highest_score = score
                best_model = m

        selected = best_model or eligible_models[0]
        arm = self.get_arm(category, selected.alias)
        return selected, f"BANDIT_UCB_EXPLOITATION (avg_reward={arm.avg_reward:.3f}, trials={arm.trials})", arm.avg_reward

    def compute_reward(
        self,
        quality_score: float,
        latency_ms: float,
        cost: float,
        success: bool,
        fallback_used: bool,
    ) -> float:
        """Computes standardized scalar reward in [0.0, 1.0] from multidimensional execution metrics."""
        if not success:
            return 0.0

        # Quality contribution (0.0 to 0.50)
        norm_quality = min(1.0, max(0.0, quality_score)) * 0.50

        # Latency contribution (0.0 to 0.25): full score at <= 200ms, decays to 0 at 3000ms
        norm_latency = max(0.0, 1.0 - (min(3000.0, latency_ms) / 3000.0)) * 0.25

        # Cost efficiency contribution (0.0 to 0.25): cheaper is higher reward
        norm_cost = max(0.0, 1.0 - (min(0.01, cost) / 0.01)) * 0.25

        reward = norm_quality + norm_latency + norm_cost

        # Fallback penalty
        if fallback_used:
            reward *= 0.70

        return max(0.0, min(1.0, round(reward, 4)))

    def record_feedback(
        self,
        category: str,
        model_alias: str,
        quality_score: float,
        latency_ms: float,
        cost: float,
        success: bool,
        fallback_used: bool = False,
    ) -> float:
        """Applies measured execution feedback to adapt future model selection distributions."""
        reward = self.compute_reward(
            quality_score=quality_score,
            latency_ms=latency_ms,
            cost=cost,
            success=success,
            fallback_used=fallback_used,
        )

        arm = self.get_arm(category, model_alias)
        # Apply exponential decay to past observations for model version adaptability
        decayed_trials = arm.trials * self.decay_factor
        decayed_reward = arm.total_reward * self.decay_factor

        arm.trials = round(decayed_trials) + 1
        arm.successes = (round(arm.successes * self.decay_factor) + 1) if success else round(arm.successes * self.decay_factor)
        arm.total_reward = decayed_reward + reward
        arm.avg_reward = arm.total_reward / arm.trials

        # Running average for latency and cost
        arm.avg_latency_ms = (arm.avg_latency_ms * 0.9) + (latency_ms * 0.1)
        arm.avg_cost = (arm.avg_cost * 0.9) + (cost * 0.1)
        arm.last_updated = time.time()

        logger.debug(
            f"Bandit updated [{category}|{model_alias}]: reward={reward:.3f}, new_avg={arm.avg_reward:.3f}, trials={arm.trials}"
        )
        return reward

    def get_statistics(self) -> List[Dict[str, Any]]:
        return [arm.to_dict() for arm in self._arms.values()]

    def reset(self) -> None:
        self._arms.clear()


default_bandit_router = ContextualBanditRouter()
