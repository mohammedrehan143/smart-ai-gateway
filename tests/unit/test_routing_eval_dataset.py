"""Automated routing intelligence accuracy evaluation across labeled benchmark dataset."""

import json
from pathlib import Path
from app.domain.entities import ChatMessage, RoutingOptions
from app.domain.router import DeterministicRouter

DATASET_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation_dataset" / "routing_eval_dataset_v1.json"


def test_routing_benchmark_dataset_accuracy():
    """Evaluates router complexity classification and tier selection against labeled benchmark dataset."""
    assert DATASET_PATH.exists(), f"Routing dataset not found at {DATASET_PATH}"

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    samples = data["samples"]
    assert len(samples) >= 30

    router = DeterministicRouter()
    options = RoutingOptions(policy="adaptive", preference="balanced")

    correct_tier_count = 0
    correct_complexity_count = 0
    total = len(samples)

    failures = []

    for s in samples:
        prompt = s["prompt"]
        exp_tier = s["expected_tier"]
        exp_comp = s["expected_complexity"]

        messages = [ChatMessage(role="user", content=prompt)]
        decision = router.route(messages, options)

        tier_match = decision.tier == exp_tier
        comp_match = decision.complexity == exp_comp

        if tier_match:
            correct_tier_count += 1
        if comp_match:
            correct_complexity_count += 1

        if not tier_match or not comp_match:
            failures.append(
                f"Sample {s['id']}: '{prompt}' | Expected: tier={exp_tier}, comp={exp_comp} | Got: tier={decision.tier}, comp={decision.complexity}"
            )

    tier_accuracy = correct_tier_count / total
    comp_accuracy = correct_complexity_count / total

    print("\n--- ROUTING EVALUATION RESULTS ---")
    print(f"Total Samples: {total}")
    print(f"Tier Routing Accuracy: {tier_accuracy * 100:.1f}% ({correct_tier_count}/{total})")
    print(f"Complexity Classification Accuracy: {comp_accuracy * 100:.1f}% ({correct_complexity_count}/{total})")

    if failures:
        print("\nFailures:")
        for fail in failures:
            print("  *", fail)

    # Assert standard 9/10 threshold: at least 95% tier routing accuracy
    assert tier_accuracy >= 0.95, f"Tier routing accuracy {tier_accuracy:.2f} is below 0.95 threshold!"
    assert comp_accuracy >= 0.95, f"Complexity classification accuracy {comp_accuracy:.2f} is below 0.95 threshold!"
