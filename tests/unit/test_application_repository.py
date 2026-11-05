"""F-01 and F-03 — application search and unknown-application handling.

These run on in-memory SQLite with the same metadata PostgreSQL builds from.
What SQLite cannot tell us is whether the two functional ``lower()`` indexes
are actually usable for the prefix predicate; that is checked in
``tests/integration/test_application_search_postgresql.py``.

The fixture applications are **invented**. They are controlled test data, not
collected records, and no claim about the operational corpus follows from
them.
"""

from __future__ import annotations

import pytest
from app.config import get_settings
from app.db.models import Application, Base
from app.db.repositories import (
    ApplicationDetail,
    ApplicationRepository,
    UnknownApplicationReport,
    handle_unknown_application,
)
from app.db.repositories.application_repo import escape_like
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

#: Invented fixtures. Chosen to separate the cases that matter: a shared name
#: prefix, a shared package prefix, differing case, a null developer, and a
#: name containing a LIKE metacharacter.
FIXTURES: tuple[tuple[str, str, str | None], ...] = (
    ("com.whatsapp", "WhatsApp Messenger", "WhatsApp LLC"),
    ("com.whatsapp.w4b", "WhatsApp Business", "WhatsApp LLC"),
    ("com.example.weather", "Weather Now", "Example Labs"),
    ("com.example.notes", "NOTES PRO", "Example Labs"),
    ("com.example.nodev", "No Developer App", None),
    ("com.example.percent", "100% Battery", "Example Labs"),
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            Application(
                package_name=package, app_name=name, developer_name=developer
            )
            for package, name, developer in FIXTURES
        )
        session.commit()
        yield session


@pytest.fixture
def repo(session: Session) -> ApplicationRepository:
    return ApplicationRepository(session)


def packages(results) -> list[str]:
    return [r.package_name for r in results]


# ---------------------------------------------------------------------------
# F-01 — search
# ---------------------------------------------------------------------------


def test_exact_application_name_matches():
    """A full name is a prefix of itself."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Application(
                package_name="com.whatsapp",
                app_name="WhatsApp Messenger",
                developer_name="WhatsApp LLC",
            )
        )
        session.commit()
        results = ApplicationRepository(session).search("WhatsApp Messenger")

    assert packages(results) == ["com.whatsapp"]
    assert results[0].app_name == "WhatsApp Messenger"
    assert results[0].developer_name == "WhatsApp LLC"


def test_exact_package_name_matches(repo: ApplicationRepository):
    assert packages(repo.search("com.example.weather")) == ["com.example.weather"]


@pytest.mark.parametrize("term", ["whatsapp", "WHATSAPP", "WhAtSaPp"])
def test_search_is_case_insensitive(repo: ApplicationRepository, term: str):
    """ALG-11 compares through lower() on both sides."""
    assert set(packages(repo.search(term))) == {"com.whatsapp", "com.whatsapp.w4b"}


def test_stored_name_case_does_not_affect_matching(repo: ApplicationRepository):
    """'NOTES PRO' is stored upper-case and must match a lower-case query."""
    assert packages(repo.search("notes")) == ["com.example.notes"]


def test_partial_prefix_matches(repo: ApplicationRepository):
    assert packages(repo.search("weath")) == ["com.example.weather"]


def test_package_prefix_matches_several(repo: ApplicationRepository):
    """A package prefix shared by four fixtures returns all four."""
    found = set(packages(repo.search("com.example")))
    assert found == {
        "com.example.weather",
        "com.example.notes",
        "com.example.nodev",
        "com.example.percent",
    }


def test_name_and_package_are_both_searched(repo: ApplicationRepository):
    """'no' is a prefix of the name 'No Developer App' and of no package.

    'notes' matches by name too, so the point of the test is that a hit found
    only through app_name is returned.
    """
    assert "com.example.nodev" in packages(repo.search("no "))


def test_search_is_a_prefix_search_not_a_substring_search(repo: ApplicationRepository):
    """'app' appears inside 'WhatsApp' but is not a prefix of it.

    ALG-11 is a prefix search precisely so the functional B-tree indexes can
    serve it; a leading-wildcard substring query cannot use them. Recording
    the consequence here so the limitation is explicit rather than discovered.
    """
    assert packages(repo.search("app")) == []


def test_no_match_returns_empty_list(repo: ApplicationRepository):
    assert repo.search("zzzznothing") == []


@pytest.mark.parametrize("term", ["", "   ", None, "a", " b "])
def test_short_or_empty_query_returns_empty_without_raising(
    repo: ApplicationRepository, term
):
    """FR-01 describes an as-you-type box. One keystroke is not a query."""
    assert repo.search(term) == []


def test_minimum_query_length_comes_from_configuration():
    assert get_settings().application_search_min_query_length == 2


def test_result_limit_is_applied(repo: ApplicationRepository):
    assert len(repo.search("com.example", limit=2)) == 2


def test_default_limit_comes_from_configuration(repo: ApplicationRepository):
    """All six fixtures share the 'com.' prefix, and 6 < 20, so none is cut."""
    settings = get_settings()
    assert settings.application_search_limit == 20
    assert len(repo.search("com.")) == len(FIXTURES) == 6


def test_zero_or_negative_limit_returns_empty(repo: ApplicationRepository):
    assert repo.search("com.example", limit=0) == []
    assert repo.search("com.example", limit=-1) == []


def test_results_are_ordered_deterministically(repo: ApplicationRepository):
    """Two identical queries must agree, including across plans."""
    assert packages(repo.search("com.example")) == packages(repo.search("com.example"))
    assert packages(repo.search("com.example")) == [
        "com.example.percent",
        "com.example.nodev",
        "com.example.notes",
        "com.example.weather",
    ]


def test_null_developer_name_is_returned_as_none(repo: ApplicationRepository):
    (result,) = repo.search("no develop")
    assert result.developer_name is None


def test_summary_does_not_expose_the_surrogate_key(repo: ApplicationRepository):
    (result,) = repo.search("weather")
    assert not hasattr(result, "app_id")


# ---------------------------------------------------------------------------
# LIKE metacharacters
# ---------------------------------------------------------------------------


def test_percent_in_a_query_is_matched_literally(repo: ApplicationRepository):
    """Unescaped, '100%' would match every row beginning '100'.

    More importantly a query of '%' alone would match the whole corpus.
    """
    assert packages(repo.search("100%")) == ["com.example.percent"]


def test_a_bare_wildcard_query_matches_nothing(repo: ApplicationRepository):
    assert repo.search("%%") == []
    assert repo.search("__") == []


def test_escape_like_escapes_all_three_metacharacters():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("c\\d") == "c\\\\d"


# ---------------------------------------------------------------------------
# Retrieval by package identifier
# ---------------------------------------------------------------------------


def test_get_by_package_returns_detail(repo: ApplicationRepository):
    found = repo.get_by_package("com.whatsapp")
    assert isinstance(found, ApplicationDetail)
    assert found.app_name == "WhatsApp Messenger"
    assert found.app_id > 0
    assert found.first_seen_at is not None


def test_get_by_package_is_case_sensitive(repo: ApplicationRepository):
    """Android package names are case-sensitive identifiers.

    Folding case here would let two distinct identifiers resolve to one row,
    which the UNIQUE constraint on package_name does not permit.
    """
    assert repo.get_by_package("COM.WHATSAPP") is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_get_by_package_handles_missing_input(repo: ApplicationRepository, value):
    assert repo.get_by_package(value) is None


def test_get_by_package_returns_none_for_unknown(repo: ApplicationRepository):
    assert repo.get_by_package("com.not.collected") is None


def test_exists(repo: ApplicationRepository):
    assert repo.exists("com.whatsapp") is True
    assert repo.exists("com.not.collected") is False
    assert repo.exists(None) is False


# ---------------------------------------------------------------------------
# F-03 — unknown application
# ---------------------------------------------------------------------------


def test_unknown_application_is_reported_not_raised(repo: ApplicationRepository):
    report = repo.resolve_or_report("com.not.collected")
    assert isinstance(report, UnknownApplicationReport)
    assert report.present_in_corpus is False
    assert report.package_name == "com.not.collected"


def test_known_application_resolves_to_detail(repo: ApplicationRepository):
    assert isinstance(repo.resolve_or_report("com.whatsapp"), ApplicationDetail)


def test_unknown_application_states_absence_from_the_offline_corpus():
    report = handle_unknown_application("com.not.collected")
    assert "not present in the offline corpus" in report.reason


def test_unknown_application_never_permits_an_audit_request():
    """FR-02 needs two snapshots. An absent application has none."""
    for configured in (True, False):
        report = handle_unknown_application(
            "com.not.collected", live_retrieval_configured=configured
        )
        assert report.can_request_audit is False


def test_live_retrieval_unconfigured_is_reported_accurately():
    report = handle_unknown_application("com.x", live_retrieval_configured=False)
    assert report.live_retrieval_configured is False
    assert "not configured" in report.suggested_action
    assert "M3_ACQUISITION_REPORT" in report.suggested_action


def test_configured_live_retrieval_does_not_imply_success():
    """The distinction this test exists for.

    An adapter being present means a request can be attempted. The gateway
    returns recorded failures, and Phase 1 named scraper breakage the
    highest-probability risk, so 'available' must never read as 'obtained'.
    """
    report = handle_unknown_application("com.x", live_retrieval_configured=True)
    assert report.live_retrieval_configured is True
    assert "can be attempted" in report.suggested_action
    assert "not the same as obtaining" in report.suggested_action
    for forbidden in ("has been retrieved", "was collected", "now available"):
        assert forbidden not in report.suggested_action


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_identifier_is_handled(value):
    report = handle_unknown_application(value)
    assert report.package_name == ""
    assert report.can_request_audit is False
    assert "No package identifier" in report.reason


def test_report_is_immutable():
    report = handle_unknown_application("com.x")
    with pytest.raises(AttributeError):
        report.can_request_audit = True  # type: ignore[misc]
