"""manual collection -> corpus import -> the worker loading the policy.

The Spotify pilot audit stuck at `running` because these three disagreed
about what a relative policy path is relative to. A corpus record stores it
relative to the **corpus** root so the corpus can be moved; a snapshot row
stores it relative to the **repository** root because that is what
`load_policy_document` resolves against. Storing the record's string
verbatim meant the worker looked in the wrong place, and every stage before
it reported success.

Nothing here mocks the filesystem: a real policy file is written, collected,
imported and then loaded back the way the worker loads it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from app.db.models import Application, Base, DisclosureSnapshot
from app.db.repositories.snapshot_repo import (
    PolicyDocumentUnavailableError,
    SnapshotRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from acquisition.corpus import CorpusPaths, iter_records

ROOT = Path(__file__).resolve().parents[2]

POLICY_HTML = (
    "<html><body><h2>Privacy</h2>"
    "<p>We collect your email address to create your account.</p>"
    "<p>We collect your precise location to show nearby content.</p>"
    "</body></html>"
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def collected(tmp_path):
    """A real corpus, built by running `scripts/manual_collect.py`."""
    corpus = tmp_path / "corpus"
    policy_file = tmp_path / "saved_policy.html"
    policy_file.write_text(POLICY_HTML, encoding="utf-8")

    record_input = tmp_path / "app.json"
    record_input.write_text(
        json.dumps(
            {
                "package_name": "com.example.pathcontract",
                "app_name": "Path Contract",
                "play_store_url": "https://play.google.com/store/apps/details?id=com.example.pathcontract",
                "policy_url": "https://example.invalid/privacy",
                "declaration": {
                    "declares_no_data_collected": False,
                    "entries": [
                        {
                            "ds_category": "Location",
                            "data_type": "Precise location",
                            "is_collected": True,
                            "is_shared": False,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/manual_collect.py"),
            "--input", str(record_input),
            "--policy-file", str(policy_file),
            "--root", str(corpus),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return CorpusPaths(corpus)


def test_manual_collection_stores_the_policy_inside_the_corpus(collected):
    """The record's path is corpus-relative, which is correct: it keeps the
    corpus relocatable. It is not what a snapshot row stores."""
    (_path, record), = list(iter_records(collected))
    assert record.policy_path is not None
    assert not Path(record.policy_path).is_absolute()
    assert (collected.root / record.policy_path).is_file()


def test_the_imported_snapshot_path_resolves_from_the_repository_root(
    session, collected, tmp_path
):
    """The regression. Before the fix the snapshot stored the record's
    corpus-relative string and the worker could not find the file."""
    (_path, record), = list(iter_records(collected))
    repository_root = tmp_path  # stands in for the checkout

    application = Application(
        package_name=record.package_name, app_name=record.app_name
    )
    session.add(application)
    session.flush()

    importer = SnapshotRepository(
        session, policy_root=repository_root, corpus_root=collected.root
    )
    snapshot = importer.record_collection_event(application.app_id, record)
    session.flush()

    assert snapshot.policy_doc_path != record.policy_path, (
        "the record's corpus-relative path was stored verbatim again"
    )
    assert (repository_root / snapshot.policy_doc_path).is_file()


def test_the_worker_can_load_the_policy_it_was_imported_with(
    session, collected, tmp_path
):
    """End to end: collect, import, then load exactly as the pipeline does."""
    (_path, record), = list(iter_records(collected))
    repository_root = tmp_path

    application = Application(
        package_name=record.package_name, app_name=record.app_name
    )
    session.add(application)
    session.flush()
    SnapshotRepository(
        session, policy_root=repository_root, corpus_root=collected.root
    ).record_collection_event(application.app_id, record)
    session.flush()

    snapshot = session.query(DisclosureSnapshot).one()

    # The pipeline builds its repository with the repository root only.
    reader = SnapshotRepository(session, policy_root=repository_root)
    document = reader.load_policy_document(snapshot.snapshot_id)

    assert document is not None
    assert "We collect your email address" in document.content
    assert document.content_sha256 == snapshot.policy_doc_sha256


def test_a_corpus_relative_path_stored_verbatim_still_fails_loudly(
    session, collected, tmp_path
):
    """The old behaviour, asserted so the fix cannot be undone quietly.

    Importing without a corpus root stores the record's string unchanged,
    which is what every pre-fix import did, and the loader must still raise
    rather than return None. A None here would read as 'this collection
    event has no policy', which is a different and much worse answer.
    """
    (_path, record), = list(iter_records(collected))
    application = Application(
        package_name=record.package_name, app_name=record.app_name
    )
    session.add(application)
    session.flush()

    SnapshotRepository(session, policy_root=tmp_path).record_collection_event(
        application.app_id, record
    )
    session.flush()
    snapshot = session.query(DisclosureSnapshot).one()
    assert snapshot.policy_doc_path == record.policy_path

    reader = SnapshotRepository(session, policy_root=tmp_path)
    with pytest.raises(PolicyDocumentUnavailableError, match="does not exist"):
        reader.load_policy_document(snapshot.snapshot_id)


def test_an_absolute_record_path_is_left_alone(session, collected, tmp_path):
    from dataclasses import replace

    (_path, record), = list(iter_records(collected))
    absolute = (collected.root / record.policy_path).resolve()
    record = replace(record, policy_path=str(absolute))

    application = Application(package_name="com.example.abs", app_name="Abs")
    session.add(application)
    session.flush()
    snapshot = SnapshotRepository(
        session, policy_root=tmp_path, corpus_root=collected.root
    ).record_collection_event(application.app_id, record)
    session.flush()

    assert snapshot.policy_doc_path == str(absolute)
    document = SnapshotRepository(
        session, policy_root=tmp_path
    ).load_policy_document(snapshot.snapshot_id)
    assert document is not None


def test_a_corpus_outside_the_repository_is_stored_absolute(
    session, collected, tmp_path
):
    """Storing a shorter relative path that cannot resolve would be worse
    than storing a long absolute one."""
    (_path, record), = list(iter_records(collected))
    elsewhere = tmp_path / "not-the-repo"
    elsewhere.mkdir()

    application = Application(package_name="com.example.outside", app_name="Out")
    session.add(application)
    session.flush()
    snapshot = SnapshotRepository(
        session, policy_root=elsewhere, corpus_root=collected.root
    ).record_collection_event(application.app_id, record)
    session.flush()

    assert Path(snapshot.policy_doc_path).is_absolute()
    assert Path(snapshot.policy_doc_path).is_file()
