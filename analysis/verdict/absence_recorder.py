"""F-21 — record that the policy does not mention a declared category.

Declared-not-in-policy is an **absence**. There is no sentence to quote,
because the finding is that no such sentence exists. An absence record
therefore carries a reason and no quoted text, and the
``ck_record_absence_has_no_quote`` constraint rejects any attempt to attach
one.

This is the correction recorded during Phase 2: an earlier draft required a
supporting sentence for every inconsistency, which is impossible for a finding
whose whole content is that nothing was found.

Complexity: O(k) over the declared lines named in the reason.
"""

from __future__ import annotations

from analysis.verdict.models import DeclarationState, EvidenceRecord
from analysis.vocabulary import RECORD_ABSENCE


def record_absence(
    ds_category: str, declaration: DeclarationState
) -> tuple[EvidenceRecord, ...]:
    """Build the single absence record for a Declared-not-in-policy verdict.

    The reason names what was declared and states plainly what the system did
    and did not establish. It is written for a reader of the report, so it says
    that no matching statement was found, not that the policy fails to disclose
    the practice: the system searched this policy text with these models, and
    that is the extent of what it can report.
    """
    declared_items = [item for item in declaration.items if item.asserts_practice]

    data_types = sorted(
        {item.data_type for item in declared_items if item.data_type is not None}
    )
    declared_as = (
        f"{ds_category} ({', '.join(data_types)})" if data_types else ds_category
    )

    actions = []
    if any(item.is_collected for item in declared_items):
        actions.append("collection")
    if any(item.is_shared for item in declared_items):
        actions.append("sharing")
    action_text = " and ".join(actions) if actions else "a data practice"

    reason = (
        f"The Data Safety declaration states {action_text} for {declared_as}. "
        "No statement matching this category was found in the privacy policy "
        "text that was analysed. This records an absence of a matching "
        "statement, not a conclusion about the policy's adequacy or the "
        "developer's conduct."
    )

    return (
        EvidenceRecord(
            record_type=RECORD_ABSENCE,
            reason=reason,
            display_order=0,
        ),
    )
