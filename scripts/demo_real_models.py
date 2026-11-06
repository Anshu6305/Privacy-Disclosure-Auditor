#!/usr/bin/env python3
"""Run the whole pipeline on real policy text with the real trained models.

    python scripts/demo_real_models.py

**This is a pipeline demonstration, not an audit**, and the output says so.
An audit compares two disclosures. There is no Google Play Data Safety
declaration here, because none has been collected for any application yet, so
the declaration side is genuinely empty and every category the policy
mentions comes out In-policy-not-declared. That is the correct reading of
"the policy says this and no declaration was collected", and it is not a
finding about any developer.

What it does establish, on real input and with real weights:

* F-08 extraction and F-09 segmentation over a genuine published privacy
  policy from the OPP-115 corpus;
* F-11 classification by the rebuilt M5 baseline;
* F-14's confidence gate and its abstention flag;
* F-12 data-type spans from the trained checkpoint, feeding
* F-15's authored mapping rules;
* ALG-8 verdicts and F-20/21/22 evidence records, each quote verified to be
  a slice of the stored document.

F-18 is the one component still stubbed, because no NLI checkpoint can be
downloaded in this environment. The audit records that as a fixture model and
the report declares it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import os  # noqa: E402

os.environ.setdefault("POSTGRES_PASSWORD", "")

from app.db.models import (  # noqa: E402
    Application,
    AuditRun,
    Base,
    DisclosureSnapshot,
    EvidenceRecord,
    TaxonomyMappingVersion,
    Verdict,
)
from app.services.audit_pipeline import AuditPipeline  # noqa: E402
from app.services.model_registry import (  # noqa: E402
    ModelsUnavailableError,
    load_baseline_classifier,
    load_span_extractor,
    register_fixture_models,
)
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from acquisition.policy_document import sha256_of_bytes  # noqa: E402
from analysis.mapping.rule_loader import load_mapping_file  # noqa: E402
from analysis.vocabulary import (  # noqa: E402
    RECORD_EVIDENCE,
    SNAPSHOT_POLICY_ONLY,
    STATUS_QUEUED,
)

CORPUS = ROOT / "data/raw/opp115/sanitized_policies"


class StubAligner:
    """Stands in for F-18, which has no downloadable checkpoint here.

    Labels a candidate SUPPORTS when the policy side carries a mapped
    practice. This is NOT semantic alignment and is recorded as a fixture
    model, so the report declares it rather than presenting it as inference.
    """

    def judge(self, candidates):
        from analysis.verdict.models import AlignmentJudgement
        from analysis.vocabulary import ALIGN_NO_MATCH, ALIGN_SUPPORTS

        out = []
        for candidate in candidates:
            mapped = candidate.mapped_practice
            out.append(
                AlignmentJudgement(
                    candidate=candidate,
                    label=ALIGN_SUPPORTS if mapped else ALIGN_NO_MATCH,
                    confidence=mapped.practice.confidence if mapped else 0.5,
                )
            )
        return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=None)
    arguments = parser.parse_args()

    policy_file = arguments.policy
    if policy_file is None:
        candidates = sorted(CORPUS.glob("*.html"))
        if not candidates:
            print(f"No policies at {CORPUS}", file=sys.stderr)
            return 2
        policy_file = candidates[0]

    raw = policy_file.read_bytes()
    digest = sha256_of_bytes(raw)
    print(f"policy source : {policy_file.name}  ({len(raw)} bytes)")
    print(f"sha256        : {digest}")

    try:
        classifier = load_baseline_classifier()
        print("F-11          : real, rebuilt M5 baseline")
    except ModelsUnavailableError as exc:
        print(f"F-11 unavailable: {exc}", file=sys.stderr)
        return 2

    try:
        span_extractor = load_span_extractor()
        print("F-12          : real, trained span-extractor-v1")
    except ModelsUnavailableError as exc:
        print(f"F-12 unavailable: {exc}", file=sys.stderr)
        return 2

    mapping = load_mapping_file()
    print(f"F-15          : real, {len(mapping.rules)} authored rules "
          f"({mapping.version_label})")
    print("F-18          : FIXTURE — no NLI checkpoint is downloadable here")

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        application = Application(
            package_name=f"opp115.{policy_file.stem}",
            app_name=policy_file.stem,
        )
        session.add(application)
        session.flush()

        snapshot = DisclosureSnapshot(
            app_id=application.app_id,
            collected_at=datetime.now(timezone.utc),
            source_url_listing="",
            source_url_policy=f"opp115://{policy_file.name}",
            retrieval_mode="manual_import",
            policy_doc_path=str(policy_file.relative_to(ROOT)),
            policy_doc_sha256=digest,
            # No Data Safety section was read. Not "declares nothing".
            status=SNAPSHOT_POLICY_ONLY,
            declares_no_data_collected=None,
        )
        session.add(snapshot)
        session.flush()

        version = TaxonomyMappingVersion(
            version_label=mapping.version_label, is_active=True
        )
        session.add(version)
        session.flush()
        models = register_fixture_models(session, "demo-f18-fixture")

        audit = AuditRun(
            app_id=application.app_id,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_mapping_version_id=version.taxonomy_mapping_version_id,
            classification_model_id=models["classification"],
            span_model_id=models["span_extraction"],
            alignment_model_id=models["alignment"],
            status=STATUS_QUEUED,
            threshold_config={"classifier": 0.5, "alignment": 0.5, "provisional": True},
        )
        session.add(audit)
        session.flush()

        outcome = AuditPipeline(
            session,
            classifier=classifier,
            aligner=StubAligner(),
            mapper=mapping.mapper(),
            repository_root=ROOT,
            span_extractor=span_extractor,
        ).run(audit.audit_id)
        session.commit()

        print("\n--- pipeline ---")
        print(f"segments   : {outcome.segment_count}")
        print(f"practices  : {outcome.practice_count}")
        print(f"judgements : {outcome.judgement_count}")
        print(f"verdicts   : {outcome.verdict_count}")
        print(f"evidence   : {outcome.evidence_count}")
        print(f"fixture models used: {outcome.uses_fixture_models}")

        print("\n--- verdicts ---")
        for verdict in session.scalars(
            select(Verdict).where(Verdict.audit_id == audit.audit_id)
        ):
            mark = " (abstention involved)" if verdict.abstention_involved else ""
            print(f"  {verdict.ds_category:26s} {verdict.verdict_value}{mark}")

        print("\n--- evidence quotes, verified against the stored document ---")
        from acquisition.models import PolicyDocument
        from analysis.text.extractor import extract_policy_text

        cleaned = extract_policy_text(
            PolicyDocument(
                package_name=application.package_name,
                source_url="",
                content=raw.decode("utf-8", errors="replace"),
                content_sha256=digest,
                storage_path=str(policy_file),
                media_type="text/html",
            )
        ).text

        records = session.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.record_type == RECORD_EVIDENCE
            )
        ).all()
        for record in records[:5]:
            exact = cleaned[record.char_start : record.char_end] == record.quoted_text
            quote = record.quoted_text[:110].replace("\n", " ")
            print(f"  [{record.char_start}:{record.char_end}] exact={exact} {quote!r}")
        all_exact = all(
            cleaned[r.char_start : r.char_end] == r.quoted_text for r in records
        )
        print(f"\n  {len(records)} evidence records; every quote an exact slice: {all_exact}")

    print(
        "\nThis was a PIPELINE DEMONSTRATION on real policy text, not an audit:\n"
        "no Data Safety declaration was collected, so the declaration side is\n"
        "empty by fact and not by finding. F-18 was a fixture."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
