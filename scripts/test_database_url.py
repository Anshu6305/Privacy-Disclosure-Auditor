#!/usr/bin/env python3
"""Compose a TEST_DATABASE_URL for a named test database, without exposing
the password.

Why this exists. The integration tests need a SQLAlchemy URL containing the
database password. Typing one by hand puts the password in the shell history,
and a password containing ``@``, ``:``, ``/`` or ``#`` silently breaks a
hand-written URL because those characters are URL syntax. This reads the
password from the project's own settings, percent-encodes it, and prints only
the finished URL, so the intended use is command substitution:

    export TEST_DATABASE_URL="$(python scripts/test_database_url.py privacy_auditor_c53_20261105_test)"

Nothing is echoed to the terminal by that line, and the password never appears
in shell history.

**Safety.** The database name must end in ``_test``, and the three protected
project databases are refused outright even if one of them were renamed to
match that pattern. This script only prints a string: it creates nothing,
connects to nothing and modifies nothing.

Exit codes:
    0  the URL was printed
    2  the name was refused, or no password is configured
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

#: Never composed by this script, whatever is asked for. These hold the
#: project's own data and the verified frozen baseline.
PROTECTED = frozenset(
    {
        "privacy_auditor",
        "privacy_auditor_test",
        "privacy_auditor_frozen_20261105_test",
    }
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        help="Name of the disposable test database. Must end in '_test'.",
    )
    args = parser.parse_args()
    database = args.database.strip()

    if database in PROTECTED:
        print(
            f"Refusing to compose a URL for {database!r}: it is a protected "
            "project database. Create a disposable one instead.",
            file=sys.stderr,
        )
        return 2

    if not database.endswith("_test"):
        print(
            f"Refusing to compose a URL for {database!r}: the name must end "
            "in '_test'. The integration tests reject anything else anyway.",
            file=sys.stderr,
        )
        return 2

    from app.config import get_settings

    settings = get_settings()
    if not settings.postgres_password:
        print(
            "No POSTGRES_PASSWORD is configured. Set it in .env at the "
            "repository root.",
            file=sys.stderr,
        )
        return 2

    # quote() with an empty safe set, because every reserved character in a
    # password has to be encoded for the URL to parse correctly.
    user = quote(settings.postgres_user, safe="")
    password = quote(settings.postgres_password, safe="")
    print(
        f"postgresql+psycopg://{user}:{password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{database}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
