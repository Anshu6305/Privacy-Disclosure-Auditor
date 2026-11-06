"""The authored F-15 mapping (ALG-5).

These test the *content* of `analysis/mapping/taxonomy/mapping_v1.json`, not
only the lookup mechanism, because the mechanism has been correct since M7
and the rules are the part that can be wrong in a way no type checker
catches: a plausible-looking line that asserts two unrelated categories are
the same thing.
"""

from __future__ import annotations

import json

import pytest

from analysis.mapping.rule_loader import (
    DEFAULT_MAPPING_FILE,
    MappingFileError,
    load_mapping_file,
)
from analysis.verdict.models import PolicyPractice, PolicySegmentRef
from analysis.vocabulary import DS_CATEGORIES, opp115_categories

FIRST_PARTY = "First Party Collection/Use"
THIRD_PARTY = "Third Party Sharing/Collection"


@pytest.fixture(scope="module")
def mapping():
    return load_mapping_file()


@pytest.fixture(scope="module")
def mapper(mapping):
    return mapping.mapper()


def practice(category: str = FIRST_PARTY) -> PolicyPractice:
    segment = PolicySegmentRef(
        segment_id=1, text="We collect data.", char_start=0, char_end=16
    )
    return PolicyPractice(
        practice_id=1, segment=segment, opp115_category=category, confidence=0.9
    )


# -- the table as a whole ---------------------------------------------------


def test_every_rule_names_real_categories_in_both_vocabularies(mapping):
    known_opp115 = set(opp115_categories())
    known_ds = set(DS_CATEGORIES)
    for rule in mapping.rules:
        assert rule.opp115_category in known_opp115
        assert rule.ds_category in known_ds


def test_every_rule_carries_a_rationale(mapping):
    """An unexplained mapping cannot be reviewed, and this table's only claim
    to legitimacy is that each line can be argued with."""
    for rule in mapping.rules:
        assert rule.rationale and len(rule.rationale) > 30, rule


def test_every_data_type_in_the_corpus_is_either_mapped_or_explained(mapping):
    """No value may be silently absent.

    A data type that is neither mapped nor listed as unmapped has simply been
    forgotten, and the symptom — a policy sentence that quietly contributes
    nothing — is indistinguishable from the system working.
    """
    corpus_values = {
        "Unspecified", "Generic personal information", "Cookies and tracking elements",
        "Contact", "User online activities", "IP address and device IDs", "Other",
        "Computer information", "Location", "Financial", "Demographic", "Health",
        "User profile", "Personal identifier", "User Profile", "Survey data",
        "Social media data",
    }
    mapped = {rule.opp115_data_type for rule in mapping.rules}
    explained = {entry["opp115_data_type"] for entry in mapping.unmapped_data_types}
    missing = corpus_values - mapped - explained
    assert not missing, f"neither mapped nor explained: {sorted(missing)}"


def test_the_two_collection_categories_are_the_only_ones_mapped(mapping):
    """A Data Safety category states what data is handled.

    'Data Security' describes protection, 'Data Retention' duration, 'User
    Choice/Control' governance. Mapping any of them to a data category would
    report 'we encrypt your data' as a declaration that the data is
    collected — a different claim, and in a consistency audit a damaging one.
    """
    assert {rule.opp115_category for rule in mapping.rules} == {FIRST_PARTY, THIRD_PARTY}

    explained = {entry["opp115_category"] for entry in mapping.unmapped_categories}
    assert explained == set(opp115_categories()) - {FIRST_PARTY, THIRD_PARTY}
    for entry in mapping.unmapped_categories:
        assert entry["reason"]


# -- individual mappings ----------------------------------------------------


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        ("Location", "Location"),
        ("Financial", "Financial info"),
        ("Health", "Health and fitness"),
        ("Demographic", "Personal info"),
        ("Personal identifier", "Personal info"),
        ("IP address and device IDs", "Device or other IDs"),
    ],
)
def test_the_unambiguous_mappings(mapper, data_type, expected):
    results = mapper.map_practice(practice(), data_type)
    assert [result.ds_category for result in results] == [expected]
    assert results[0].is_partial is False


def test_opp115_contact_maps_to_personal_info_not_to_contacts(mapper):
    """The single easiest error in this table, so it gets its own test.

    OPP-115 'Contact' is the user's own contact details. Data Safety
    'Contacts' is the user's address book — other people's details. The names
    are near-homographs for different things, and conflating them would make
    every policy that mentions an email address look like a declaration about
    the user's address book.
    """
    results = mapper.map_practice(practice(), "Contact")
    assert [result.ds_category for result in results] == ["Personal info"]
    assert "Contacts" not in {result.ds_category for result in results}


def test_an_ambiguous_data_type_maps_to_both_categories_and_flags_each(mapper):
    """'User online activities' spans two Data Safety categories.

    Emitting both and flagging each partial is more honest than choosing
    one: the source value genuinely does not distinguish in-app activity from
    browsing, and silently picking one would assert a precision the
    annotation does not have.
    """
    results = mapper.map_practice(practice(), "User online activities")
    assert {result.ds_category for result in results} == {"App activity", "Web browsing"}
    assert all(result.is_partial for result in results)


def test_a_broad_value_maps_partially(mapper):
    results = mapper.map_practice(practice(), "Generic personal information")
    assert [result.ds_category for result in results] == ["Personal info"]
    assert results[0].is_partial is True


def test_both_corpus_spellings_of_user_profile_map(mapper):
    """The corpus contains both capitalisations, 212 and 112 times.

    Normalising them in the table would hide a corpus fact from anyone
    reading the rules against the data.
    """
    for spelling in ("User profile", "User Profile"):
        assert mapper.map_practice(practice(), spelling), spelling


@pytest.mark.parametrize("data_type", ["Unspecified", "Other", "Survey data"])
def test_an_unsupported_data_type_maps_to_nothing(mapper, data_type):
    """Silence, not a guess.

    'Unspecified' is the corpus's own 'nothing to select' value and the
    commonest in the attribute: mapping it would manufacture a declaration
    out of an annotator's abstention 4,299 times.
    """
    assert mapper.map_practice(practice(), data_type) == ()


@pytest.mark.parametrize(
    "category",
    ["Data Security", "Data Retention", "User Choice/Control", "Policy Change"],
)
def test_a_non_collection_category_maps_to_nothing_even_with_a_data_type(
    mapper, category
):
    assert mapper.map_practice(practice(category), "Location") == ()


def test_third_party_sharing_maps_the_same_data_types_as_first_party(mapper):
    """The sharing dimension is carried by the declaration's is_shared flag,
    not by the data category, so the two categories map identically."""
    for data_type in ("Location", "Financial", "Health", "Contact"):
        first = {r.ds_category for r in mapper.map_practice(practice(FIRST_PARTY), data_type)}
        third = {r.ds_category for r in mapper.map_practice(practice(THIRD_PARTY), data_type)}
        assert first == third, data_type


def test_an_unknown_data_type_maps_to_nothing(mapper):
    assert mapper.map_practice(practice(), "Blood type") == ()


# -- what the table cannot do, stated as a test -----------------------------


def test_the_table_has_no_general_rules_so_nothing_maps_without_a_data_type(mapper):
    """Asserted, not merely documented.

    Every rule is keyed on a data type, so a caller with no data type gets an
    empty mapping from a table that is complete and correct. `AuditPipeline`
    refuses to run in that configuration rather than reporting every declared
    category as missing from the policy. If a general rule is ever added,
    this test fails and that guard must be revisited.
    """
    assert mapper.general_rule_count == 0
    assert mapper.rule_count == 30
    assert mapper.map_all([practice()]) == ()


# -- loader validation ------------------------------------------------------


def test_the_loader_rejects_an_unknown_data_safety_category(tmp_path):
    document = json.loads(DEFAULT_MAPPING_FILE.read_text(encoding="utf-8"))
    document["rules"][0]["ds_category"] = "Shoe size"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(MappingFileError, match="Shoe size"):
        load_mapping_file(path)


def test_the_loader_rejects_a_rule_with_no_rationale(tmp_path):
    document = json.loads(DEFAULT_MAPPING_FILE.read_text(encoding="utf-8"))
    document["rules"][0].pop("rationale")
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(MappingFileError, match="rationale"):
        load_mapping_file(path)


def test_the_loader_rejects_a_duplicate_rule(tmp_path):
    document = json.loads(DEFAULT_MAPPING_FILE.read_text(encoding="utf-8"))
    document["rules"].append(dict(document["rules"][0]))
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(MappingFileError, match="duplicates"):
        load_mapping_file(path)


def test_the_loader_rejects_an_empty_table(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"version_label": "v0", "rules": []}), encoding="utf-8")
    with pytest.raises(MappingFileError, match="no rules"):
        load_mapping_file(path)
