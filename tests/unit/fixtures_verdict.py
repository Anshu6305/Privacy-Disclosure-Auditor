"""Controlled fixtures for the verdict engine tests.

Every judgement here is written by hand with an explicit label and confidence.
Nothing in this file runs a model, approximates one, or stands in for F-18,
which does not exist yet. These are stated inputs chosen to exercise specific
branches of ALG-8.

The policy sentences are invented for testing. They are not quotations from any
real application's privacy policy.
"""

from __future__ import annotations

from analysis.verdict.models import (
    AlignmentCandidate,
    AlignmentJudgement,
    DeclarationState,
    DeclaredItem,
    MappedPolicyPractice,
    PolicyPractice,
    PolicySegmentRef,
)

# Invented policy sentences, with offsets that describe them exactly.
COLLECTS_EMAIL = "We collect your email address so that we can send you updates."
NEVER_LOCATION = "We never collect or store your location."
SHARES_CONTACTS = "We share your contacts with our partners."
VAGUE = "We take your privacy seriously."


def segment(text: str, segment_id: int = 1, char_start: int = 0) -> PolicySegmentRef:
    """A segment whose offsets match its text, as F-09 will produce."""
    return PolicySegmentRef(
        segment_id=segment_id,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def practice(
    text: str,
    *,
    practice_id: int = 1,
    segment_id: int = 1,
    opp115_category: str = "First Party Collection/Use",
    confidence: float = 0.9,
    abstained: bool = False,
) -> PolicyPractice:
    return PolicyPractice(
        practice_id=practice_id,
        segment=segment(text, segment_id=segment_id),
        opp115_category=opp115_category,
        confidence=confidence,
        abstained=abstained,
    )


def mapped(
    text: str,
    ds_category: str = "Personal info",
    **kwargs,
) -> MappedPolicyPractice:
    return MappedPolicyPractice(
        practice=practice(text, **kwargs), ds_category=ds_category
    )


def declared(
    ds_category: str = "Personal info",
    *,
    data_type: str | None = "Email address",
    is_collected: bool = True,
    is_shared: bool = False,
    declared_practice_id: int = 1,
) -> DeclarationState:
    """A declaration state asserting one practice for one category."""
    return DeclarationState(
        ds_category=ds_category,
        items=(
            DeclaredItem(
                declared_practice_id=declared_practice_id,
                ds_category=ds_category,
                data_type=data_type,
                is_collected=is_collected,
                is_shared=is_shared,
            ),
        ),
    )


def not_declared(ds_category: str = "Personal info") -> DeclarationState:
    """A category the declaration says nothing about."""
    return DeclarationState(ds_category=ds_category, items=())


def judgement(
    label: str,
    text: str = COLLECTS_EMAIL,
    *,
    ds_category: str = "Personal info",
    confidence: float = 0.9,
    model_abstained: bool = False,
    practice_abstained: bool = False,
    segment_id: int = 1,
    with_declaration: bool = True,
) -> AlignmentJudgement:
    """One hand-written judgement.

    ``practice_abstained`` marks the upstream policy practice as uncertain,
    which is how the abstention-propagation tests set up their input.
    """
    candidate = AlignmentCandidate(
        ds_category=ds_category,
        declared_item=(
            declared(ds_category).items[0] if with_declaration else None
        ),
        mapped_practice=mapped(
            text,
            ds_category=ds_category,
            segment_id=segment_id,
            abstained=practice_abstained,
        ),
    )
    return AlignmentJudgement(
        candidate=candidate,
        label=label,
        confidence=confidence,
        model_abstained=model_abstained,
    )


def declaration_only_judgement(
    ds_category: str = "Personal info",
) -> AlignmentJudgement:
    """A judgement on a declared line with no policy practice to compare."""
    candidate = AlignmentCandidate(
        ds_category=ds_category, declared_item=declared(ds_category).items[0]
    )
    return AlignmentJudgement(
        candidate=candidate, label="NO_MATCH", confidence=0.95
    )
