"""F-20 — select the policy text that supports a verdict (ALG-9).

Evidence is **quoted, never generated**. Each record carries a slice of the
policy's own text together with the offsets it came from, and the quote is
taken by slicing the stored segment rather than by composing a sentence. A
reader can therefore check any finding against the document.

Selection orders the judgements by confidence, highest first, and keeps the top
few. A verdict usually rests on one clear sentence; showing twenty makes the
report unreadable and no more true.

Complexity: O(J log J) for the sort, O(1) for the slice per record.
"""

from __future__ import annotations

from collections.abc import Sequence

from analysis.verdict.models import AlignmentJudgement, EvidenceRecord
from analysis.vocabulary import RECORD_EVIDENCE


def select_evidence(
    judgements: Sequence[AlignmentJudgement], max_records: int = 3
) -> tuple[EvidenceRecord, ...]:
    """Build evidence records from decisive judgements, strongest first.

    Only decisive judgements are accepted. Passing an abstained judgement here
    is a programming error, not a data condition: evidence asserts that the
    policy says something, and an abstained judgement is precisely the case
    where the system does not know that.
    """
    if max_records < 1:
        raise ValueError("max_records must be at least 1")

    for judgement in judgements:
        if judgement.abstained:
            raise ValueError(
                "an abstained judgement cannot support an evidence record; it "
                "belongs in an inconclusive record (F-22)"
            )
        if judgement.candidate.mapped_practice is None:
            raise ValueError(
                "an evidence record needs a policy practice to quote from"
            )

    ranked = sorted(judgements, key=_ranking_key)

    records: list[EvidenceRecord] = []
    seen_segments: set[int] = set()

    for judgement in ranked:
        segment = judgement.candidate.segment
        assert segment is not None  # guarded above

        # The same segment can be reached through several declared lines in one
        # category. Quoting it repeatedly adds length, not information.
        if segment.segment_id in seen_segments:
            continue
        seen_segments.add(segment.segment_id)

        records.append(
            EvidenceRecord(
                record_type=RECORD_EVIDENCE,
                segment_id=segment.segment_id,
                quoted_text=segment.text,
                char_start=segment.char_start,
                char_end=segment.char_end,
                judgement_label=judgement.label,
                judgement_confidence=judgement.confidence,
                display_order=len(records),
            )
        )

        if len(records) == max_records:
            break

    return tuple(records)


def _ranking_key(judgement: AlignmentJudgement) -> tuple[float, int]:
    """Highest confidence first, then lowest segment id.

    The segment id breaks ties deterministically, so the same inputs always
    produce the same report. Without it two equally confident sentences could
    swap places between runs and make reports appear to differ when nothing
    changed.
    """
    segment = judgement.candidate.segment
    segment_id = segment.segment_id if segment is not None else 0
    return (-judgement.confidence, segment_id)
