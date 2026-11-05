"""Policy-grouped train / validation / test splits.

**Segments from one policy never cross a split boundary.** A privacy policy
reuses its own phrasing throughout — the same defined terms, the same
sentence shapes, often the same clause repeated in two sections — so a random
split by segment would put near-duplicates of a test segment into training and
report a score that measures memorisation rather than generalisation.

Splitting by source policy is the methodological requirement, and it is the
difference between a result the team can defend in a viva and one that falls
apart under the first question about it.

The split is deterministic: policies are sorted, then shuffled with a seeded
generator, so the same seed always produces the same assignment.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ml.data.opp115_dataset import LabelledSegment
from ml.data.opp115_schema import CATEGORIES

#: Recorded in the model metadata so a run can be reproduced exactly.
DEFAULT_SEED = 20261105

#: Provisional. Chosen to leave enough held-out policies for per-class support
#: to mean something, while keeping most of a 115-policy corpus for training.
DEFAULT_PROPORTIONS = (0.70, 0.15, 0.15)

#: Below this many positive examples in the test split, a per-class score is
#: too unstable to report as a measurement. Not a rule from the design; a
#: threshold for honest reporting, documented in the M5 report.
MINIMUM_RELIABLE_TEST_SUPPORT = 10


@dataclass
class SplitReport:
    """Everything needed to judge whether the split is sound."""

    seed: int
    proportions: tuple[float, float, float]
    policies: dict[str, int] = field(default_factory=dict)
    segments: dict[str, int] = field(default_factory=dict)
    support: dict[str, Counter] = field(default_factory=dict)
    unreliable_categories: list[str] = field(default_factory=list)
    absent_from_test: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatasetSplit:
    train: list[LabelledSegment]
    validation: list[LabelledSegment]
    test: list[LabelledSegment]
    report: SplitReport

    def policies_in(self, name: str) -> set[str]:
        return {e.policy_id for e in getattr(self, name)}


def split_by_policy(
    examples: list[LabelledSegment],
    proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
    seed: int = DEFAULT_SEED,
) -> DatasetSplit:
    """Assign whole policies to train, validation and test.

    Proportions apply to the **policy** count, not the segment count, because
    policies are the unit being assigned. Segment counts therefore come out
    close to but not exactly at the requested proportions, and the report
    states both.
    """
    if len(proportions) != 3:
        raise ValueError("proportions must be (train, validation, test)")
    if abs(sum(proportions) - 1.0) > 1e-9:
        raise ValueError(f"proportions must sum to 1.0, got {sum(proportions)}")
    if any(p <= 0 for p in proportions):
        raise ValueError("every split must receive a positive share")

    by_policy: dict[str, list[LabelledSegment]] = defaultdict(list)
    for example in examples:
        by_policy[example.policy_id].append(example)

    # Sort before shuffling so the result depends only on the seed, never on
    # the order the examples happened to arrive in.
    policies = sorted(by_policy)
    if len(policies) < 3:
        raise ValueError(
            f"need at least 3 policies to make 3 splits, got {len(policies)}"
        )

    rng = random.Random(seed)
    rng.shuffle(policies)

    n_train = int(round(len(policies) * proportions[0]))
    n_validation = int(round(len(policies) * proportions[1]))
    # Whatever remains goes to test, so no policy is dropped by rounding.
    n_train = min(n_train, len(policies) - 2)
    n_validation = min(n_validation, len(policies) - n_train - 1)

    assignment = {
        "train": policies[:n_train],
        "validation": policies[n_train : n_train + n_validation],
        "test": policies[n_train + n_validation :],
    }

    report = SplitReport(seed=seed, proportions=proportions)
    buckets: dict[str, list[LabelledSegment]] = {}

    for name, names in assignment.items():
        bucket = [e for policy in sorted(names) for e in by_policy[policy]]
        bucket.sort(key=lambda e: (e.policy_id, e.segment_index))
        buckets[name] = bucket

        report.policies[name] = len(names)
        report.segments[name] = len(bucket)
        support = Counter()
        for example in bucket:
            for label in example.labels:
                support[label] += 1
        report.support[name] = support

    test_support = report.support["test"]
    for category in CATEGORIES:
        count = test_support.get(category, 0)
        if count == 0:
            report.absent_from_test.append(category)
        elif count < MINIMUM_RELIABLE_TEST_SUPPORT:
            report.unreliable_categories.append(category)

    if report.absent_from_test:
        report.warnings.append(
            f"{len(report.absent_from_test)} categories have no positive "
            f"example in the test split and cannot be evaluated at all: "
            f"{report.absent_from_test}"
        )
    if report.unreliable_categories:
        report.warnings.append(
            f"{len(report.unreliable_categories)} categories have fewer than "
            f"{MINIMUM_RELIABLE_TEST_SUPPORT} positive test examples; their "
            f"per-class scores are not stable measurements: "
            f"{report.unreliable_categories}"
        )

    # A policy appearing in two splits would invalidate the whole experiment,
    # so it is checked rather than assumed.
    for first in ("train", "validation"):
        for second in ("validation", "test"):
            if first == second:
                continue
            overlap = {e.policy_id for e in buckets[first]} & {
                e.policy_id for e in buckets[second]
            }
            if overlap:
                raise AssertionError(
                    f"policy leakage between {first} and {second}: {sorted(overlap)}"
                )

    return DatasetSplit(
        train=buckets["train"],
        validation=buckets["validation"],
        test=buckets["test"],
        report=report,
    )


def format_split_report(report: SplitReport) -> str:
    lines = [
        "-" * 74,
        "Policy-grouped split",
        "-" * 74,
        f"Seed        : {report.seed}",
        f"Proportions : train {report.proportions[0]:.0%} / "
        f"validation {report.proportions[1]:.0%} / test {report.proportions[2]:.0%} "
        f"(of policies)",
        "",
        f"{'split':<12}{'policies':>10}{'segments':>10}",
    ]
    for name in ("train", "validation", "test"):
        lines.append(
            f"{name:<12}{report.policies.get(name, 0):>10}"
            f"{report.segments.get(name, 0):>10}"
        )

    lines += ["", "Per-class positive support", ""]
    lines.append(f"{'category':<38}{'train':>8}{'val':>8}{'test':>8}")
    for category in CATEGORIES:
        train = report.support["train"].get(category, 0)
        val = report.support["validation"].get(category, 0)
        test = report.support["test"].get(category, 0)
        flag = ""
        if test == 0:
            flag = "  NOT EVALUABLE"
        elif test < MINIMUM_RELIABLE_TEST_SUPPORT:
            flag = "  unreliable"
        lines.append(f"{category:<38}{train:>8}{val:>8}{test:>8}{flag}")

    for warning in report.warnings:
        lines.append(f"\nWARNING: {warning}")

    lines.append("-" * 74)
    return "\n".join(lines)
