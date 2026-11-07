"""F-22 — record that the system abstained.

An Undetermined verdict is the system declining to answer. The record says so
and says why, so that a reader can tell it apart from a finding. It is not a
weak inconsistency and must never be presented as one.

An inconclusive record may reference the segment that caused the abstention,
which helps a human reviewer look at the right paragraph. When it does, the
quoted text is still taken verbatim from that segment, because a reviewer
following up needs the policy's words and not a description of them.

Complexity: O(A) over the abstained judgements.
"""

from __future__ import annotations

from collections.abc import Sequence

from analysis.verdict.models import AlignmentJudgement, EvidenceRecord
from analysis.vocabulary import RECORD_INCONCLUSIVE


def record_inconclusive(
    abstentions: Sequence[AlignmentJudgement],
    declared: bool,
    max_records: int = 3,
) -> tuple[EvidenceRecord, ...]:
    """Build inconclusive records for an Undetermined verdict.

    ``declared`` changes only the wording, not the outcome: a reader needs to
    know which question went unanswered. Both cases remain Undetermined.
    """
    if not abstentions:
        raise ValueError(
            "an Undetermined verdict must be accompanied by at least one "
            "abstained judgement"
        )

    if declared:
        unanswered = (
            "whether the privacy policy describes the declared practice"
        )
    else:
        unanswered = (
            "whether the privacy policy describes a practice that the Data "
            "Safety declaration does not mention"
        )

    records: list[EvidenceRecord] = []
    seen_segments: set[int] = set()

    for judgement in abstentions:
        segment = judgement.candidate.segment

        if segment is not None:
            if segment.segment_id in seen_segments:
                continue
            seen_segments.add(segment.segment_id)

        if judgement.rests_on_partial_mapping and not judgement.model_abstained:
            # Checked before the threshold causes: this judgement may be
            # perfectly confident, and saying it fell below a threshold
            # would be untrue as well as unhelpful.
            cause = (
                "the policy passage reached this category through a partial "
                "taxonomy mapping, so it is not established that the passage "
                "and the declaration describe the same data practice"
            )
        elif judgement.candidate.abstained_upstream:
            cause = (
                "the data practice extracted from the policy text was below the "
                "confidence threshold"
            )
        else:
            cause = (
                "the cross-source comparison was below the confidence threshold"
            )

        reason = (
            f"The system could not determine {unanswered}, because {cause}. "
            "This is an abstention, not a finding of inconsistency."
        )

        records.append(
            EvidenceRecord(
                record_type=RECORD_INCONCLUSIVE,
                reason=reason,
                segment_id=None if segment is None else segment.segment_id,
                quoted_text=None if segment is None else segment.text,
                char_start=None if segment is None else segment.char_start,
                char_end=None if segment is None else segment.char_end,
                judgement_confidence=judgement.confidence,
                display_order=len(records),
            )
        )

        if len(records) == max_records:
            break

    return tuple(records)
