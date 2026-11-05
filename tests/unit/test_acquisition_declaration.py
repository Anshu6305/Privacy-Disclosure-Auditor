"""F-04 — Data Safety declaration normalisation.

All inputs are controlled fixtures. No declaration in this suite came from
Google Play; the project has never retrieved one.
"""

from __future__ import annotations

import pytest

from acquisition.declaration import (
    DeclarationFormatError,
    UnknownDeclarationCategoryError,
    declaration_to_dict,
    normalise_declaration,
    summarise,
)

MINIMAL = {
    "package_name": "com.example.app",
    "entries": [
        {"category": "Personal info", "data_type": "Email address", "collected": True}
    ],
}


def test_normalises_a_minimal_declaration():
    d = normalise_declaration(MINIMAL)
    assert d.package_name == "com.example.app"
    assert d.collected_categories == ("Personal info",)
    assert d.shared_categories == ()
    assert d.asserts("Personal info") is True
    assert d.asserts("Location") is False


def test_preserves_collected_and_shared_separately():
    """Google declares collection and sharing separately; conflating them
    would turn a collection-only app into one that shares data."""
    d = normalise_declaration({
        "package_name": "com.example.app",
        "entries": [
            {"category": "Contacts", "collected": True, "shared": True},
            {"category": "Location", "collected": True, "shared": False},
        ],
    })
    assert d.collected_categories == ("Contacts", "Location")
    assert d.shared_categories == ("Contacts",)


def test_preserves_purposes_and_optional_flag():
    d = normalise_declaration({
        "package_name": "com.example.app",
        "entries": [{
            "category": "Personal info", "collected": True,
            "purposes": ["Analytics", "App functionality"], "optional": True,
        }],
    })
    entry = d.entries[0]
    assert entry.purposes == ("Analytics", "App functionality")
    assert entry.is_optional is True


def test_preserves_security_practices():
    d = normalise_declaration({
        "package_name": "com.example.app",
        "entries": [{"category": "Personal info", "collected": True}],
        "security": {"encrypted_in_transit": True, "deletion_available": False},
    })
    assert d.security.data_encrypted_in_transit is True
    assert d.security.data_deletion_available is False
    assert d.security.independent_security_review is None, (
        "a practice the listing does not state must stay unknown, not become "
        "a denial"
    )


def test_app_level_no_data_collected_is_a_distinct_state():
    """Different from a declaration that merely omits a category."""
    d = normalise_declaration({
        "package_name": "com.example.app", "declares_no_data_collected": True,
    })
    assert d.declares_no_data_collected is True
    assert d.entries == ()
    assert "declares no data collected" in summarise(d)


def test_no_data_collected_contradicting_entries_is_rejected():
    with pytest.raises(DeclarationFormatError, match="contradicts itself"):
        normalise_declaration({
            "package_name": "com.example.app",
            "declares_no_data_collected": True,
            "entries": [{"category": "Location", "collected": True}],
        })


def test_entry_asserting_neither_collection_nor_sharing_is_rejected():
    """The published section lists only positive declarations, so such an
    entry did not come from one."""
    with pytest.raises(DeclarationFormatError, match="must set 'collected'"):
        normalise_declaration({
            "package_name": "com.example.app",
            "entries": [{"category": "Location", "collected": False, "shared": False}],
        })


def test_unknown_category_stops_the_import():
    """Dropping it would produce a record that looks complete while missing a
    whole category."""
    with pytest.raises(UnknownDeclarationCategoryError) as caught:
        normalise_declaration({
            "package_name": "com.example.app",
            "entries": [{"category": "Brain Activity", "collected": True}],
        })
    assert caught.value.category == "Brain Activity"


def test_package_name_is_required():
    with pytest.raises(DeclarationFormatError, match="package_name"):
        normalise_declaration({"entries": []})


@pytest.mark.parametrize("bad", ["yes", "no", 1, 0])
def test_non_boolean_flags_are_rejected_rather_than_coerced(bad):
    """Coercing "no" to True would invert a declaration."""
    with pytest.raises(DeclarationFormatError, match="true, false or absent"):
        normalise_declaration({
            "package_name": "com.example.app",
            "entries": [{"category": "Location", "collected": True, "optional": bad}],
        })


def test_absent_optional_flag_stays_unknown():
    d = normalise_declaration(MINIMAL)
    assert d.entries[0].is_optional is None
    assert d.entries[0].is_ephemeral is None


def test_raw_label_is_preserved_for_auditing():
    d = normalise_declaration({
        "package_name": "com.example.app",
        "entries": [{
            "category": "Personal info", "collected": True,
            "raw_label": "Email address (required)",
        }],
    })
    assert d.entries[0].raw_label == "Email address (required)"


def test_declaration_round_trips():
    d = normalise_declaration({
        "package_name": "com.example.app",
        "entries": [
            {"category": "Contacts", "data_type": "Contacts", "collected": True,
             "shared": True, "purposes": ["Advertising or marketing"],
             "optional": True, "raw_label": "Contacts"},
        ],
        "security": {"encrypted_in_transit": True},
    })
    assert normalise_declaration(declaration_to_dict(d)) == d


def test_entries_must_be_a_list():
    with pytest.raises(DeclarationFormatError, match="must be a list"):
        normalise_declaration({"package_name": "com.example.app", "entries": "none"})
