"""F-04 — load and normalise a Data Safety declaration.

The normaliser reads the project's own documented corpus format and produces a
:class:`DataSafetyDeclaration`. Mapping a particular scraper's output into that
format is the job of an adapter in :mod:`acquisition.adapters`, which is kept
separate because Phase 1 identified scraper maintenance as the project's
highest-probability risk: when a scraper breaks or is replaced, only the
adapter changes.

**What the fields are grounded in.** Google's documentation of the Data safety
section states that each entry carries a data type from a fixed category list,
whether the data is collected or shared (declared separately), a purpose from
a fixed list, and whether collection is optional; and that the section also
carries security practices and data deletion statements. Those are the fields
normalised here. Nothing beyond them is invented, and a field absent from the
input stays absent rather than being defaulted to a value that looks like a
declaration.

**What has not been verified.** No live Data Safety page has been inspected by
this project. ``play.google.com`` is not reachable from the development
environment, and the acquisition adapter has not been run against it. The
normalisation rules therefore rest on Google's published documentation, not on
a sample of real pages. Until a pilot runs, treat them as provisional; see
``docs/M3_ACQUISITION_REPORT.md``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acquisition.models import (
    DataSafetyDeclaration,
    DeclaredDataEntry,
    Provenance,
    SecurityPractices,
)
from analysis.vocabulary import DS_CATEGORIES


class DeclarationFormatError(ValueError):
    """The input does not match the documented corpus declaration format."""


class UnknownDeclarationCategoryError(DeclarationFormatError):
    """A declaration names a Data Safety category the system does not know.

    Raised rather than ignored. Google can revise its taxonomy; if it does,
    the import must stop with the category named so the vocabulary can be
    updated. Dropping the entry would produce a corpus record that looks
    complete while missing a category, and every audit of that application
    would then silently under-report.
    """

    def __init__(self, package_name: str, category: str) -> None:
        super().__init__(
            f"{package_name}: unrecognised Data Safety category {category!r}. "
            f"It is not in analysis.vocabulary.DS_CATEGORIES. If Google has "
            f"changed its taxonomy the vocabulary needs updating; this record "
            f"cannot be imported until then."
        )
        self.package_name = package_name
        self.category = category


def _as_bool(value: Any, field_name: str) -> bool | None:
    """Strictly interpret a tri-state flag.

    Absent means unknown and stays None. Anything that is neither a boolean
    nor absent is an error, because silently coercing a string such as "no"
    to True would invert a declaration.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise DeclarationFormatError(
        f"{field_name} must be true, false or absent; got {value!r}"
    )


def _normalise_entry(
    package_name: str, raw: Mapping[str, Any], index: int
) -> DeclaredDataEntry:
    where = f"{package_name}: entries[{index}]"

    category = raw.get("category")
    if not isinstance(category, str) or not category:
        raise DeclarationFormatError(f"{where}: 'category' is required")
    if category not in DS_CATEGORIES:
        raise UnknownDeclarationCategoryError(package_name, category)

    collected = _as_bool(raw.get("collected"), f"{where}.collected") or False
    shared = _as_bool(raw.get("shared"), f"{where}.shared") or False
    if not collected and not shared:
        raise DeclarationFormatError(
            f"{where}: an entry must set 'collected', 'shared' or both. The "
            f"published section lists only positive declarations, so an entry "
            f"asserting neither did not come from one."
        )

    purposes = raw.get("purposes", ())
    if isinstance(purposes, str):
        purposes = (purposes,)
    elif isinstance(purposes, Sequence):
        purposes = tuple(str(p) for p in purposes)
    else:
        raise DeclarationFormatError(f"{where}: 'purposes' must be a list of strings")

    data_type = raw.get("data_type")
    if data_type is not None and not isinstance(data_type, str):
        raise DeclarationFormatError(f"{where}: 'data_type' must be a string")

    return DeclaredDataEntry(
        ds_category=category,
        data_type=data_type,
        is_collected=collected,
        is_shared=shared,
        purposes=purposes,
        is_optional=_as_bool(raw.get("optional"), f"{where}.optional"),
        is_ephemeral=_as_bool(raw.get("ephemeral"), f"{where}.ephemeral"),
        raw_label=raw.get("raw_label"),
    )


def _normalise_security(raw: Mapping[str, Any] | None) -> SecurityPractices:
    if raw is None:
        return SecurityPractices()
    if not isinstance(raw, Mapping):
        raise DeclarationFormatError("'security' must be an object")
    return SecurityPractices(
        data_encrypted_in_transit=_as_bool(
            raw.get("encrypted_in_transit"), "security.encrypted_in_transit"
        ),
        data_deletion_available=_as_bool(
            raw.get("deletion_available"), "security.deletion_available"
        ),
        independent_security_review=_as_bool(
            raw.get("independent_security_review"),
            "security.independent_security_review",
        ),
        committed_to_play_families_policy=_as_bool(
            raw.get("play_families_policy"), "security.play_families_policy"
        ),
    )


def normalise_declaration(
    raw: Mapping[str, Any], provenance: Provenance | None = None
) -> DataSafetyDeclaration:
    """Normalise one declaration from the documented corpus format.

    Expected shape, all keys optional except ``package_name``::

        {
          "package_name": "com.example.app",
          "declares_no_data_collected": false,
          "entries": [
            {"category": "Personal info", "data_type": "Email address",
             "collected": true, "shared": false,
             "purposes": ["App functionality"], "optional": false,
             "ephemeral": null, "raw_label": "Email address"}
          ],
          "security": {"encrypted_in_transit": true, "deletion_available": true}
        }

    ``declares_no_data_collected`` is the app-level statement Google publishes
    when a developer declares the app collects and shares nothing. It is a
    distinct state from a declaration that merely omits a category.
    """
    if not isinstance(raw, Mapping):
        raise DeclarationFormatError("a declaration must be an object")

    package_name = raw.get("package_name")
    if not isinstance(package_name, str) or not package_name:
        raise DeclarationFormatError("'package_name' is required")

    declares_none = _as_bool(
        raw.get("declares_no_data_collected"), "declares_no_data_collected"
    ) or False

    raw_entries = raw.get("entries", ())
    if not isinstance(raw_entries, Sequence) or isinstance(raw_entries, str | bytes):
        raise DeclarationFormatError("'entries' must be a list")

    entries = tuple(
        _normalise_entry(package_name, entry, index)
        for index, entry in enumerate(raw_entries)
    )

    if declares_none and entries:
        raise DeclarationFormatError(
            f"{package_name}: 'declares_no_data_collected' is true but "
            f"{len(entries)} entries are present. The record contradicts itself "
            f"and must be corrected at source rather than resolved by guessing."
        )

    return DataSafetyDeclaration(
        package_name=package_name,
        entries=entries,
        security=_normalise_security(raw.get("security")),
        declares_no_data_collected=declares_none,
        provenance=provenance,
    )


def declaration_to_dict(declaration: DataSafetyDeclaration) -> dict[str, Any]:
    """Serialise back to the corpus format. Round-trips with the normaliser."""
    return {
        "package_name": declaration.package_name,
        "declares_no_data_collected": declaration.declares_no_data_collected,
        "entries": [
            {
                "category": e.ds_category,
                "data_type": e.data_type,
                "collected": e.is_collected,
                "shared": e.is_shared,
                "purposes": list(e.purposes),
                "optional": e.is_optional,
                "ephemeral": e.is_ephemeral,
                "raw_label": e.raw_label,
            }
            for e in declaration.entries
        ],
        "security": {
            "encrypted_in_transit": declaration.security.data_encrypted_in_transit,
            "deletion_available": declaration.security.data_deletion_available,
            "independent_security_review": declaration.security.independent_security_review,
            "play_families_policy": declaration.security.committed_to_play_families_policy,
        },
    }


def summarise(declaration: DataSafetyDeclaration) -> str:
    """One line for a collector's console output."""
    if declaration.declares_no_data_collected:
        return f"{declaration.package_name}: declares no data collected or shared"
    return (
        f"{declaration.package_name}: {len(declaration.entries)} entries, "
        f"collected={len(declaration.collected_categories)} "
        f"shared={len(declaration.shared_categories)}"
    )

