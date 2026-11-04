"""Environment verification tests (Milestone 1).

These prove that the application assembles, serves requests, and reports the
database state truthfully. They are the evidence behind the Milestone 1 entry
in the traceability document.
"""


def test_health_endpoint_reports_ok(api_client):
    response = api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_unconfigured_without_credentials(api_client):
    """With no password set, the endpoint must say so rather than claim health.

    This is the guard against a readiness check that reports success without
    having executed a query.
    """
    response = api_client.get("/api/health/database")
    assert response.status_code == 200
    assert response.json()["status"] in {"unconfigured", "unavailable"}


def test_scope_statement_disclaims_legal_judgement(api_client):
    """FR/GI requirement: the system states its limits wherever it reports.

    The scope wording is served from one place. This test fails if anyone
    weakens it, which is the point of asserting on its content.
    """
    response = api_client.get("/api/meta/scope")
    assert response.status_code == 200

    scope = response.json()["scope"].lower()
    assert "inconsistency" in scope
    for disclaimed in ("legality", "intent", "malicious"):
        assert disclaimed in scope, f"scope statement no longer disclaims {disclaimed}"
