"""Load and validate the authored F-15 mapping (ALG-5).

The rules live in `analysis/mapping/taxonomy/mapping_v1.json` rather than in
Python, because they are a reviewable artefact the team must be able to cite
in the report and diff between versions. Loading validates every field
against the two real vocabularies, so a typo in a category name fails here
rather than silently producing a rule that can never match.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from analysis.mapping.taxonomy_mapper import MappingRule, TaxonomyMapper
from analysis.vocabulary import DS_CATEGORIES, opp115_categories

TAXONOMY_DIR = Path(__file__).resolve().parent / "taxonomy"
DEFAULT_MAPPING_FILE = TAXONOMY_DIR / "mapping_v1.json"


class MappingFileError(ValueError):
    """The mapping file disagrees with the vocabularies it claims to map."""


@dataclass(frozen=True)
class LoadedMapping:
    """The authored mapping, with the documented gaps kept alongside it.

    `unmapped_data_types` and `unmapped_categories` are carried rather than
    discarded: a reader of a report needs to be able to tell a data type that
    no rule covers from one that was never considered, and only the authored
    file knows the difference.
    """

    version_label: str
    rules: tuple[MappingRule, ...]
    unmapped_data_types: tuple[dict, ...]
    unmapped_categories: tuple[dict, ...]

    def mapper(self) -> TaxonomyMapper:
        return TaxonomyMapper(self.rules, version_label=self.version_label)


def load_mapping_file(path: Path | str = DEFAULT_MAPPING_FILE) -> LoadedMapping:
    path = Path(path)
    if not path.is_file():
        raise MappingFileError(f"no mapping file at {path}")

    document = json.loads(path.read_text(encoding="utf-8"))
    version_label = document.get("version_label")
    if not version_label:
        raise MappingFileError(f"{path} has no version_label")

    known_opp115 = set(opp115_categories())
    known_ds = set(DS_CATEGORIES)

    rules: list[MappingRule] = []
    seen: set[tuple[str, str | None, str]] = set()
    for index, entry in enumerate(document.get("rules", [])):
        opp115_category = entry.get("opp115_category")
        ds_category = entry.get("ds_category")
        data_type = entry.get("opp115_data_type")
        rationale = entry.get("rationale")

        if opp115_category not in known_opp115:
            raise MappingFileError(
                f"rule {index}: {opp115_category!r} is not one of the ten "
                "OPP-115 categories"
            )
        if ds_category not in known_ds:
            raise MappingFileError(
                f"rule {index}: {ds_category!r} is not one of the fourteen "
                "Data Safety categories"
            )
        if not rationale:
            # Every rule must say why. An unexplained mapping cannot be
            # reviewed, and this table's whole claim to legitimacy is that
            # each line can be argued with.
            raise MappingFileError(f"rule {index} has no rationale")

        key = (opp115_category, data_type, ds_category)
        if key in seen:
            raise MappingFileError(f"rule {index} duplicates an earlier rule: {key}")
        seen.add(key)

        rules.append(
            MappingRule(
                opp115_category=opp115_category,
                ds_category=ds_category,
                opp115_data_type=data_type,
                is_partial=bool(entry.get("is_partial", False)),
                rationale=rationale,
            )
        )

    if not rules:
        raise MappingFileError(f"{path} contains no rules")

    for entry in document.get("unmapped_categories", []):
        if entry.get("opp115_category") not in known_opp115:
            raise MappingFileError(
                f"unmapped_categories names {entry.get('opp115_category')!r}, "
                "which is not an OPP-115 category"
            )
        if not entry.get("reason"):
            raise MappingFileError("an unmapped category has no reason")

    for entry in document.get("unmapped_data_types", []):
        if not entry.get("reason"):
            raise MappingFileError("an unmapped data type has no reason")

    return LoadedMapping(
        version_label=version_label,
        rules=tuple(rules),
        unmapped_data_types=tuple(document.get("unmapped_data_types", [])),
        unmapped_categories=tuple(document.get("unmapped_categories", [])),
    )


__all__ = [
    "DEFAULT_MAPPING_FILE",
    "LoadedMapping",
    "MappingFileError",
    "load_mapping_file",
]
