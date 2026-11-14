#!/usr/bin/env python3
"""Request an audit, optionally on a named model variant (F-13, DD-8).

    python scripts/request_audit.py com.spotify.music
    python scripts/request_audit.py com.spotify.music --variant improved --apply
    python scripts/request_audit.py com.spotify.music \
        --model classification=f11-improved-v1 \
        --model span_extraction=f12-span-extractor-v1 \
        --model alignment=f18-zeroshot-nli-v1 --apply

This is the command-line tooling DD-8 reserves the variant for. End users
never choose a variant: the API omits it, the active version set is used,
and no selector exists in the frontend. A Corpus Maintainer comparing the
baseline against the improved model runs the same application twice from
here, once per variant.

**There is no fallback.** If the requested variant is not registered and
active for all three tasks, no audit is created and the refusal says which
task was missing it. Running the other variant instead would produce a
report whose provenance names a model that never ran.

``--model task=version_label`` states the version set instead of asking the
registry to choose one. The variant axis belongs to the classifier: F-11 has
a baseline and an improved model, while F-12 and F-18 each have exactly one,
so `--variant improved` can never resolve span extraction or alignment. This
is how the improved classifier is run alongside them, and it is not a
fallback: every task must be named, nothing is substituted or relabelled, and
each recorded id is the model named. Mutually exclusive with ``--variant``.

Dry run by default; `--apply` is required to create the audit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.audit_service import AuditRequested, AuditService  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from analysis.vocabulary import MODEL_TASKS, MODEL_VARIANTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_name")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--variant",
        default=None,
        choices=sorted(MODEL_VARIANTS),
        help="internal; omit for the active version set",
    )
    selection.add_argument(
        "--model",
        action="append",
        default=None,
        metavar="TASK=VERSION_LABEL",
        help=(
            "state the version set explicitly; repeat once per task. "
            f"Tasks: {', '.join(MODEL_TASKS)}"
        ),
    )
    parser.add_argument("--database", default="privacy_auditor_pilot")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    if arguments.database_url:
        url = arguments.database_url
    else:
        from scripts.register_models import compose_url

        url = compose_url(arguments.database)
    version_labels: dict[str, str] | None = None
    if arguments.model:
        version_labels = {}
        for pair in arguments.model:
            task, _, label = pair.partition("=")
            task, label = task.strip(), label.strip()
            if not label:
                print(
                    f"--model expects TASK=VERSION_LABEL, got {pair!r}",
                    file=sys.stderr,
                )
                return 2
            if task not in MODEL_TASKS:
                print(
                    f"unknown task {task!r}; the tasks are "
                    f"{', '.join(MODEL_TASKS)}",
                    file=sys.stderr,
                )
                return 2
            if task in version_labels:
                print(f"task {task!r} named twice", file=sys.stderr)
                return 2
            version_labels[task] = label
        missing = [task for task in MODEL_TASKS if task not in version_labels]
        if missing:
            print(
                f"--model must name every task; missing {', '.join(missing)}. "
                "Nothing is defaulted, because an audit records the model "
                "that produced every judgement.",
                file=sys.stderr,
            )
            return 2

    print(f"database : {make_url(url).database}")
    print(f"package  : {arguments.package_name}")
    if version_labels:
        print("models   : stated explicitly")
        for task in MODEL_TASKS:
            print(f"  {task:16} {version_labels[task]}")
    else:
        print(f"variant  : {arguments.variant or 'active version set'}")

    engine = create_engine(url, future=True)
    with Session(engine) as session:
        result = AuditService(session).request_audit(
            arguments.package_name,
            variant=arguments.variant,
            version_labels=version_labels,
        )
        if not isinstance(result, AuditRequested):
            session.rollback()
            print(f"\nREFUSED ({result.reason}): {result.detail}", file=sys.stderr)
            return 1

        # `AuditRequested` carries no status: the row is created `queued`
        # and the apply/rollback line below says what became of it.
        print(f"\naudit {result.audit_id} for {result.package_name}")
        print(f"  snapshot          : {result.snapshot_id}")
        print(f"  mapping version   : {result.taxonomy_mapping_version_id}")
        print(f"  classification    : {result.classification_model_id}")
        print(f"  span extraction   : {result.span_model_id}")
        print(f"  alignment         : {result.alignment_model_id}")

        if arguments.apply:
            session.commit()
            print("\nCommitted. The worker will claim it.")
        else:
            session.rollback()
            print("\n--dry-run (default): rolled back, no audit was created.")
            print("Re-run with --apply to queue it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
