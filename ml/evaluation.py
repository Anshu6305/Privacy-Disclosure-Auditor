"""Multi-label evaluation for F-11 (and later F-12, F-18).

Reports per class first and aggregates second, deliberately. A macro-F1 of
0.55 can hide a category the model never predicts correctly, and the whole
point of reporting Do Not Track separately is that it has 31 positive segments
in the entire corpus.

Every number here comes from held-out data the model has not seen. Nothing in
this module can produce a figure from the training set by accident, because it
is given predictions and gold labels and does not know which split they came
from — the caller's job is to pass the right ones, and the training script
labels each result with its split.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ml.data.splits import MINIMUM_RELIABLE_TEST_SUPPORT


@dataclass(frozen=True)
class ClassMetrics:
    category: str
    precision: float
    recall: float
    f1: float
    support: int
    true_positives: int
    false_positives: int
    false_negatives: int
    predicted: int

    @property
    def reliable(self) -> bool:
        """Whether this score rests on enough examples to mean anything."""
        return self.support >= MINIMUM_RELIABLE_TEST_SUPPORT


@dataclass
class EvaluationReport:
    split_name: str
    per_class: list[ClassMetrics] = field(default_factory=list)
    macro_f1: float = 0.0
    micro_f1: float = 0.0
    micro_precision: float = 0.0
    micro_recall: float = 0.0
    hamming_loss: float = 0.0
    subset_accuracy: float = 0.0
    total_support: int = 0
    examples: int = 0
    threshold: float = 0.5

    @property
    def unreliable(self) -> list[str]:
        return [m.category for m in self.per_class if not m.reliable]

    @property
    def never_predicted(self) -> list[str]:
        return [m.category for m in self.per_class if m.predicted == 0]


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate(
    gold: list[tuple[str, ...]],
    scores: list[dict[str, float]],
    categories: list[str],
    split_name: str,
    threshold: float = 0.5,
) -> EvaluationReport:
    """Compute per-class and aggregate metrics at one decision threshold.

    ``threshold`` turns scores into predictions. It is a reporting choice, not
    a trained parameter, and the threshold actually used in the pipeline is
    F-14's and is configured separately.
    """
    if len(gold) != len(scores):
        raise ValueError(f"{len(gold)} gold rows but {len(scores)} score rows")
    if not gold:
        raise ValueError("cannot evaluate an empty set")

    report = EvaluationReport(
        split_name=split_name, examples=len(gold), threshold=threshold
    )

    predicted_sets = [
        {c for c in categories if row.get(c, 0.0) >= threshold} for row in scores
    ]
    gold_sets = [set(labels) for labels in gold]

    total_tp = total_fp = total_fn = 0
    f1_scores = []

    for category in categories:
        tp = sum(
            1 for g, p in zip(gold_sets, predicted_sets, strict=True)
            if category in g and category in p
        )
        fp = sum(
            1 for g, p in zip(gold_sets, predicted_sets, strict=True)
            if category not in g and category in p
        )
        fn = sum(
            1 for g, p in zip(gold_sets, predicted_sets, strict=True)
            if category in g and category not in p
        )

        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        f1 = _safe_divide(2 * precision * recall, precision + recall)

        report.per_class.append(
            ClassMetrics(
                category=category,
                precision=precision,
                recall=recall,
                f1=f1,
                support=tp + fn,
                true_positives=tp,
                false_positives=fp,
                false_negatives=fn,
                predicted=tp + fp,
            )
        )
        total_tp += tp
        total_fp += fp
        total_fn += fn
        f1_scores.append(f1)

    report.macro_f1 = _safe_divide(sum(f1_scores), len(f1_scores))
    report.micro_precision = _safe_divide(total_tp, total_tp + total_fp)
    report.micro_recall = _safe_divide(total_tp, total_tp + total_fn)
    report.micro_f1 = _safe_divide(
        2 * report.micro_precision * report.micro_recall,
        report.micro_precision + report.micro_recall,
    )

    # Hamming loss: the share of (example, category) cells that are wrong.
    cells = len(gold) * len(categories)
    wrong = sum(
        len(g.symmetric_difference(p))
        for g, p in zip(gold_sets, predicted_sets, strict=True)
    )
    report.hamming_loss = _safe_divide(wrong, cells)

    report.subset_accuracy = _safe_divide(
        sum(1 for g, p in zip(gold_sets, predicted_sets, strict=True) if g == p),
        len(gold),
    )
    report.total_support = sum(m.support for m in report.per_class)
    return report


def format_evaluation(report: EvaluationReport) -> str:
    lines = [
        "-" * 86,
        f"Evaluation — {report.split_name} split   "
        f"({report.examples} segments, decision threshold {report.threshold})",
        "-" * 86,
        f"{'category':<38}{'prec':>7}{'recall':>8}{'F1':>7}{'supp':>7}"
        f"{'pred':>7}{'':>4}",
    ]
    for m in report.per_class:
        flag = ""
        if m.support == 0:
            flag = "  no test examples"
        elif not m.reliable:
            flag = f"  unreliable (n={m.support})"
        elif m.predicted == 0:
            flag = "  never predicted"
        lines.append(
            f"{m.category:<38}{m.precision:>7.3f}{m.recall:>8.3f}{m.f1:>7.3f}"
            f"{m.support:>7}{m.predicted:>7}{flag}"
        )

    lines += [
        "",
        f"Macro-F1        : {report.macro_f1:.4f}   "
        f"(unweighted mean over {len(report.per_class)} categories)",
        f"Micro-F1        : {report.micro_f1:.4f}   "
        f"(precision {report.micro_precision:.4f}, recall {report.micro_recall:.4f})",
        f"Hamming loss    : {report.hamming_loss:.4f}   "
        f"(share of example-by-category cells that are wrong; lower is better)",
        f"Subset accuracy : {report.subset_accuracy:.4f}   "
        f"(exact label-set match; strict for multi-label)",
        f"Total support   : {report.total_support} positive labels",
    ]

    if report.unreliable:
        lines.append(
            f"\nNOT A RELIABLE MEASUREMENT (fewer than "
            f"{MINIMUM_RELIABLE_TEST_SUPPORT} positive examples): "
            f"{report.unreliable}"
        )
    if report.never_predicted:
        lines.append(f"NEVER PREDICTED by the model: {report.never_predicted}")

    lines.append("-" * 86)
    return "\n".join(lines)


def metrics_to_dict(report: EvaluationReport) -> dict:
    return {
        "split": report.split_name,
        "examples": report.examples,
        "threshold": report.threshold,
        "macro_f1": round(report.macro_f1, 4),
        "micro_f1": round(report.micro_f1, 4),
        "micro_precision": round(report.micro_precision, 4),
        "micro_recall": round(report.micro_recall, 4),
        "hamming_loss": round(report.hamming_loss, 4),
        "subset_accuracy": round(report.subset_accuracy, 4),
        "total_support": report.total_support,
        "per_class": {
            m.category: {
                "precision": round(m.precision, 4),
                "recall": round(m.recall, 4),
                "f1": round(m.f1, 4),
                "support": m.support,
                "predicted": m.predicted,
                "true_positives": m.true_positives,
                "false_positives": m.false_positives,
                "false_negatives": m.false_negatives,
                "reliable": m.reliable,
            }
            for m in report.per_class
        },
        "unreliable_categories": report.unreliable,
        "never_predicted": report.never_predicted,
    }
