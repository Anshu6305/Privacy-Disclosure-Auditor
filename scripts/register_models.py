#!/usr/bin/env python3
"""Register the production models in PostgreSQL.

    python scripts/register_models.py --database privacy_auditor_pilot
    python scripts/register_models.py --database privacy_auditor_pilot --apply

Writes one `model_version` row per model that **actually loads**, plus an
`evaluation_run` and its `evaluation_metric` rows wherever a real metrics
file exists. Nothing else is touched: no audit is created, no verdict is
written, no application or snapshot is altered, and the taxonomy mapping is
left exactly as it is.

**A model is registered only if it loads.** Each loader is called before
anything is written, in this process, against the checkpoint on disk. A
model that raises is reported and skipped — never registered with a note
saying it might work. The alternative, registering from configuration alone,
would let an audit cite a `model_version` row for weights that are not
there.

**No `fixture:` identifiers.** `register_fixture_models()` exists for tests
and writes identifiers prefixed `fixture:` so a stub-backed report declares
itself. This script never calls it and refuses to write such an identifier.

**Idempotent.** `model_version` is unique on (task, version_label). A row
already present is reported and left alone, including its metrics: an audit
records the model version it used, so editing one after the fact would
silently change what earlier reports meant. To change a model, register a new
version label.

**Dry run by default.** `--apply` is required to write, and the dry run opens
a transaction only to read.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.db.models import EvaluationMetric, EvaluationRun, ModelVersion  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from analysis.vocabulary import (  # noqa: E402
    TASK_ALIGNMENT,
    TASK_CLASSIFICATION,
    TASK_SPAN_EXTRACTION,
    VARIANT_BASELINE,
)

FIXTURE_PREFIX = "fixture:"

#: Neither evaluation applied F-14's gate, so nothing was excluded from the
#: counts. 'counted_as_error' is the honest of the two permitted values:
#: every prediction was scored as it stood.
ABSTENTION_HANDLING = "counted_as_error"


@dataclass(frozen=True)
class Registration:
    """One model, and everything the registry records about it."""

    task: str
    variant: str
    version_label: str
    model_identifier: str
    checkpoint_path: str | None
    notes: str
    loader: Callable[[], object]
    metrics_path: Path | None = None
    training_config: dict = field(default_factory=dict)
    random_seed: int | None = None
    #: Items in the evaluated split, for `evaluation_run.item_count`.
    evaluated_items: int | None = None


def _load_classifier():
    from app.services.model_registry import load_baseline_classifier

    return load_baseline_classifier()


def _load_span_extractor():
    from app.services.model_registry import load_span_extractor

    return load_span_extractor()


def _load_aligner():
    from app.services.model_registry import load_aligner

    return load_aligner(0.50)


def registrations() -> list[Registration]:
    """The three models the approved design names, described truthfully."""
    return [
        Registration(
            task=TASK_CLASSIFICATION,
            variant=VARIANT_BASELINE,
            version_label="m5-baseline-v1",
            model_identifier="tfidf-logistic-regression/classifier-baseline-v1",
            checkpoint_path="ml/checkpoints/classifier-baseline-v1",
            notes=(
                "F-11 baseline (M5, ALG-2): TF-IDF with one-vs-rest logistic "
                "regression over the ten OPP-115 categories. Trained on the "
                "OPP-115 corpus, split by source policy with seed 20261105, "
                "labels by majority vote of at least 2 of 3 annotators. "
                "Held-out test macro-F1 0.7489, micro-F1 0.7690. Data "
                "Retention (n=7) and Do Not Track (n=4) have too few test "
                "examples to be measurable and their per-class scores are "
                "not measurements. Train macro-F1 0.94 against test 0.75 is "
                "an overfitting gap that has not been addressed."
            ),
            loader=_load_classifier,
            metrics_path=ROOT / "ml/runs/classifier-baseline-v1-metrics.json",
            training_config={
                "algorithm": "tfidf + one-vs-rest logistic regression",
                "split": "by source policy",
                "split_seed": 20261105,
                "label_rule": "majority vote, at least 2 of 3 annotators",
                "decision_threshold": 0.5,
            },
            random_seed=20261105,
            evaluated_items=541,
        ),
        Registration(
            task=TASK_SPAN_EXTRACTION,
            variant=VARIANT_BASELINE,
            version_label="f12-span-extractor-v1",
            model_identifier="distilbert-base-uncased/span-extractor-v1",
            checkpoint_path="ml/checkpoints/span-extractor-v1",
            notes=(
                "F-12 (ALG-3): token classification over 55 value-carrying "
                "BIO labels, producing data-type and purpose spans. "
                "Fine-tuned from distilbert-base-uncased for 4 epochs on a "
                "Tesla T4, on the OPP-115 spans with M5's policy split and "
                "seed 20261105. Held-out test: exact-match F1 0.1072 "
                "(precision 0.0919, recall 0.1287); overlapping-match F1 "
                "0.5658 (precision 0.4848, recall 0.6792); 0 unverifiable "
                "spans. LOW ACCURACY: span boundaries are right about one "
                "time in ten, and the model is not production-ready. It "
                "usually finds roughly the right region with the right "
                "value; F-14's abstention gate carries the uncertainty."
            ),
            loader=_load_span_extractor,
            metrics_path=ROOT / "ml/runs/span-extractor-v1-metrics.json",
            training_config={
                "base_model": "distilbert-base-uncased",
                "epochs": 4,
                "batch_size": 16,
                "learning_rate": 5e-05,
                "max_length": 512,
                "labels": 55,
                "hardware": "Tesla T4 (Google Colab)",
                "split": "by source policy",
                "split_seed": 20261105,
            },
            random_seed=20261105,
            evaluated_items=352,
        ),
        Registration(
            task=TASK_ALIGNMENT,
            variant=VARIANT_BASELINE,
            version_label="f18-zeroshot-nli-v1",
            model_identifier="cross-encoder/nli-distilroberta-base",
            checkpoint_path="ml/checkpoints/nli-mnli-v1",
            notes=(
                "F-18 (decision D-01 Option A): ZERO-SHOT natural language "
                "inference. NOT FINE-TUNED on this project's data, and NOT "
                "EVALUATED: the 300 to 500 labelled policy-statement / Data "
                "Safety-claim pairs and the application gold set both do not "
                "exist, so no metric can be reported for it. Entailment maps "
                "to SUPPORTS, contradiction to CONTRADICTS, neutral to "
                "NO_MATCH; the output index of each class is read from the "
                "checkpoint's own id2label, which for this model is "
                "contradiction 0, entailment 1, neutral 2. Observed "
                "zero-shot behaviour: reliable on denials (contradiction "
                "0.977 on a negated collection statement) and on irrelevance, "
                "but WEAK on plain entailment, scoring a matching statement "
                "neutral 0.637 against entailment 0.354."
            ),
            loader=_load_aligner,
            metrics_path=None,
            training_config={
                "mode": "zero-shot",
                "fine_tuned": False,
                "base_model": "cross-encoder/nli-distilroberta-base",
                "confidence_threshold": 0.50,
            },
        ),
    ]


def compose_url(database: str) -> str:
    """Build the URL from the project's own settings.

    The password is read from the configured settings and never printed or
    passed on a command line.
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.postgres_password:
        raise SystemExit(
            "No database password is configured. Set POSTGRES_PASSWORD in "
            ".env as the rest of the project does."
        )
    url = make_url(settings.database_url)
    return url.set(database=database).render_as_string(hide_password=False)


def probe(registration: Registration) -> tuple[bool, str]:
    """Load the model for real. Returns (loaded, detail)."""
    try:
        model = registration.loader()
    except Exception as exc:  # noqa: BLE001 - the reason is what we report
        return False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:140]}"
    return True, type(model).__name__


def metric_rows(registration: Registration) -> list[dict]:
    """Turn a real metrics file into `evaluation_metric` payloads.

    Only numbers the file actually contains. Nothing is derived, rounded up
    or filled in.
    """
    if registration.metrics_path is None or not registration.metrics_path.is_file():
        return []

    document = json.loads(registration.metrics_path.read_text(encoding="utf-8"))
    rows: list[dict] = []

    if registration.task == TASK_CLASSIFICATION:
        test = document.get("test", {})
        for name in (
            "macro_f1",
            "micro_f1",
            "micro_precision",
            "micro_recall",
            "hamming_loss",
            "subset_accuracy",
        ):
            if name in test:
                rows.append(
                    {
                        "scope": "overall",
                        "metric_name": name,
                        "class_label": None,
                        "metric_value": float(test[name]),
                        "support": test.get("total_support"),
                    }
                )
        for label, scores in (test.get("per_class") or {}).items():
            for name in ("precision", "recall", "f1"):
                if name in scores:
                    rows.append(
                        {
                            "scope": "per_category",
                            "metric_name": name,
                            "class_label": label[:64],
                            "metric_value": float(scores[name]),
                            "support": scores.get("support"),
                        }
                    )
    elif registration.task == TASK_SPAN_EXTRACTION:
        for match_kind in ("exact", "overlapping"):
            block = document.get(match_kind) or {}
            for name in ("precision", "recall", "f1"):
                if name in block:
                    rows.append(
                        {
                            "scope": "overall",
                            "metric_name": f"{match_kind}_{name}",
                            "class_label": None,
                            "metric_value": float(block[name]),
                            "support": document.get("gold_spans"),
                        }
                    )
        for span_type, counts in (document.get("per_type") or {}).items():
            for name in ("exact_tp", "overlap_tp", "predicted"):
                if name in counts:
                    rows.append(
                        {
                            "scope": "per_category",
                            "metric_name": name,
                            "class_label": span_type[:64],
                            "metric_value": float(counts[name]),
                            "support": counts.get("gold"),
                        }
                    )
    return rows


def register(
    session: Session, registration: Registration, *, activate: bool
) -> tuple[str, int]:
    """Write one model and its metrics. Returns (outcome, metric count)."""
    existing = session.execute(
        select(ModelVersion).where(
            ModelVersion.task == registration.task,
            ModelVersion.version_label == registration.version_label,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return "already registered", 0

    if registration.model_identifier.startswith(FIXTURE_PREFIX):
        raise SystemExit(
            f"refusing to register {registration.model_identifier!r}: the "
            "fixture prefix marks a controlled stub and must never reach a "
            "production registry."
        )

    if activate:
        # A flag change, not a deletion. The superseded row and every audit
        # that cited it are left intact.
        for row in session.execute(
            select(ModelVersion).where(
                ModelVersion.task == registration.task,
                ModelVersion.is_active.is_(True),
            )
        ).scalars():
            row.is_active = False

    model = ModelVersion(
        task=registration.task,
        variant=registration.variant,
        model_identifier=registration.model_identifier,
        version_label=registration.version_label,
        checkpoint_path=registration.checkpoint_path,
        trained_at=None,
        random_seed=registration.random_seed,
        training_config=registration.training_config or None,
        is_active=activate,
        notes=registration.notes,
    )
    session.add(model)
    session.flush()

    rows = metric_rows(registration)
    if rows:
        run = EvaluationRun(
            model_version_id=model.model_version_id,
            run_at=datetime.now(timezone.utc),
            split_name="test",
            gold_set_version=None,
            item_count=registration.evaluated_items or 0,
            abstention_count=0,
            config={"source": str(registration.metrics_path.relative_to(ROOT))},
            notes=(
                "Figures as measured by the project's own evaluation script. "
                "No abstention gate was applied during this evaluation, so "
                "nothing was excluded from the counts."
            ),
        )
        session.add(run)
        session.flush()
        for payload in rows:
            session.add(
                EvaluationMetric(
                    evaluation_run_id=run.evaluation_run_id,
                    abstention_handling=ABSTENTION_HANDLING,
                    **payload,
                )
            )
        session.flush()

    return "registered", len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        default="privacy_auditor_pilot",
        help="database name; the URL is composed from the project settings",
    )
    parser.add_argument("--database-url", default=None, help="override the full URL")
    parser.add_argument(
        "--apply", action="store_true", help="write. Without it, nothing is changed."
    )
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="register without marking the model active for its task",
    )
    arguments = parser.parse_args()

    print("Model registration\n")

    # 1. Load every model for real, before touching the database.
    plan: list[tuple[Registration, bool, str]] = []
    for registration in registrations():
        loaded, detail = probe(registration)
        plan.append((registration, loaded, detail))
        mark = "LOADS" if loaded else "CANNOT LOAD"
        print(f"  {registration.task:16s} {mark:12s} {registration.version_label}")
        print(f"  {'':16s} {'':12s} {detail}")
    loadable = [item for item in plan if item[1]]
    print(f"\n{len(loadable)} of {len(plan)} models load and will be registered.")
    for registration, loaded, _ in plan:
        if not loaded:
            print(f"  skipping {registration.task}: it does not load here.")

    if not loadable:
        print("\nNothing to register.", file=sys.stderr)
        return 2

    url = arguments.database_url or compose_url(arguments.database)
    database = make_url(url).database
    print(f"\ndatabase: {database}")

    engine = create_engine(url, future=True)
    activate = not arguments.no_activate

    with Session(engine) as session:
        for registration, loaded, _ in plan:
            if not loaded:
                continue
            outcome, metrics = register(session, registration, activate=activate)
            if outcome == "already registered":
                # Say nothing about its metrics: this run did not look at
                # them and did not change them. "no metrics" here would read
                # as a fact about the model rather than about this run.
                suffix = ", left unchanged"
            elif metrics:
                suffix = f", {metrics} metric rows"
            else:
                suffix = ", no metrics (none have been measured)"
            print(f"  {registration.version_label:26s} {outcome}{suffix}")

        if arguments.apply:
            session.commit()
            print("\nCommitted.")
        else:
            session.rollback()
            print("\n--dry-run (default): rolled back, nothing was written.")
            print("Re-run with --apply to write.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
