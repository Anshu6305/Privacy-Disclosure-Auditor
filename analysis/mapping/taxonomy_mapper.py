"""F-15 — map OPP-115 categories to Data Safety categories (ALG-5).

**This is a rule-based lookup, not a learned model.** The rules are authored by
the team, versioned, and stored in the database. Keeping it deterministic is
what lets a report explain itself: every mapping step can be pointed at a
specific rule in a specific mapping version. The learned component is F-18, and
the two are deliberately kept apart.

Abstention is carried through untouched. A lookup neither creates nor resolves
uncertainty, so an abstained practice stays abstained on the other side of the
mapping. Losing the flag here is the exact defect this module is written to
avoid.

Complexity: O(1) average per lookup via a dictionary, O(P) over P practices.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from analysis.verdict.models import MappedPolicyPractice, PolicyPractice


@dataclass(frozen=True)
class MappingRule:
    """One authored correspondence.

    ``opp115_data_type`` of None means the rule applies to the whole OPP-115
    category. A rule naming a data type is more specific and wins over one that
    does not.
    """

    opp115_category: str
    ds_category: str
    opp115_data_type: str | None = None
    is_partial: bool = False
    rationale: str | None = None


class TaxonomyMapper:
    """Applies a single version of the mapping rules.

    One mapper instance corresponds to one ``taxonomy_mapping_version`` row. An
    audit records which version it used, so a report produced today can still be
    explained after the rules change.
    """

    def __init__(self, rules: Iterable[MappingRule], version_label: str) -> None:
        self.version_label = version_label

        # Two indexes: specific rules keyed by (category, data type) and
        # general rules keyed by category. Lookup checks specific first.
        self._specific: dict[tuple[str, str], list[MappingRule]] = {}
        self._general: dict[str, list[MappingRule]] = {}

        for rule in rules:
            if rule.opp115_data_type is None:
                self._general.setdefault(rule.opp115_category, []).append(rule)
            else:
                key = (rule.opp115_category, rule.opp115_data_type)
                self._specific.setdefault(key, []).append(rule)

    def rules_for(
        self, opp115_category: str, data_type: str | None = None
    ) -> tuple[MappingRule, ...]:
        """Rules that apply, most specific first.

        A category may map to more than one Data Safety category; "First Party
        Collection/Use" of a phone number touches Personal info, and the design
        allows a practice to produce several mapped results rather than forcing
        a single winner.
        """
        if data_type is not None:
            specific = self._specific.get((opp115_category, data_type))
            if specific:
                return tuple(specific)
        return tuple(self._general.get(opp115_category, ()))

    def map_practice(
        self, practice: PolicyPractice, data_type: str | None = None
    ) -> tuple[MappedPolicyPractice, ...]:
        """Map one practice to zero or more Data Safety categories.

        An empty result means no rule covers this OPP-115 category. That is a
        normal outcome: several OPP-115 categories, such as Policy Change, have
        no Data Safety counterpart at all.

        The abstention flag is not an argument to this method and cannot be
        altered by it. ``MappedPolicyPractice.abstained`` reads through to the
        source practice.
        """
        return tuple(
            MappedPolicyPractice(
                practice=practice,
                ds_category=rule.ds_category,
                is_partial=rule.is_partial,
            )
            for rule in self.rules_for(practice.opp115_category, data_type)
        )

    def map_all(
        self, practices: Sequence[PolicyPractice]
    ) -> tuple[MappedPolicyPractice, ...]:
        """Map every practice, preserving abstained ones.

        Abstained practices are mapped exactly like confident ones. Filtering
        them here would hide uncertainty from the verdict engine, which is the
        one place able to turn it into an Undetermined verdict.
        """
        mapped: list[MappedPolicyPractice] = []
        for practice in practices:
            mapped.extend(self.map_practice(practice))
        return tuple(mapped)
