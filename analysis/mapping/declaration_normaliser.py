"""F-16 — normalise a Data Safety declaration into per-category state.

A declaration arrives as a list of lines, several of which may concern the same
category ("Email address" and "Name" are both Personal info). The verdict
engine works one category at a time, so the lines are grouped here.

A category counts as declared only when at least one of its lines asserts
collection or sharing. A line that asserts neither says nothing, and treating
it as a declaration would manufacture a disclosure the developer never made.

Complexity: O(n) over declaration lines.
"""

from __future__ import annotations

from collections.abc import Iterable

from analysis.verdict.models import DeclarationState, DeclaredItem
from analysis.vocabulary import DS_CATEGORIES


def normalise_declaration(
    items: Iterable[DeclaredItem],
    categories: Iterable[str] = DS_CATEGORIES,
) -> dict[str, DeclarationState]:
    """Group declaration lines by Data Safety category.

    Every category in ``categories`` appears in the result, including those the
    declaration never mentions. A category with no lines has ``declared`` false,
    which is a finding in itself and must not be a missing key.
    """
    grouped: dict[str, list[DeclaredItem]] = {category: [] for category in categories}

    for item in items:
        if item.ds_category not in grouped:
            raise UnknownDataSafetyCategoryError(item.ds_category)
        grouped[item.ds_category].append(item)

    return {
        category: DeclarationState(ds_category=category, items=tuple(lines))
        for category, lines in grouped.items()
    }


class UnknownDataSafetyCategoryError(ValueError):
    """A declaration named a category the system does not recognise.

    Raised rather than ignored. Google can revise its taxonomy, and if that
    happens the audit must fail with this category named, so the team knows to
    update the vocabulary. Silently dropping the line would produce a report
    that looks complete while missing a whole category.
    """

    def __init__(self, category: str) -> None:
        super().__init__(
            f"Unrecognised Data Safety category {category!r}. The declaration "
            "uses a category that is not in analysis.vocabulary.DS_CATEGORIES. "
            "If Google has changed its taxonomy, the vocabulary needs updating; "
            "this audit cannot be completed until then."
        )
        self.category = category
