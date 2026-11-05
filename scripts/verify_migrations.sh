#!/usr/bin/env bash
#
# Migration verification, end to end, on this machine.
#
# Grew out of C-53's verification (docs/C53_VERIFICATION_PROCEDURE.md) and now
# verifies the whole revision chain: it upgrades a fresh disposable database to
# head, runs the integration suite against it, downgrades to the baseline,
# re-runs to prove the revision-gated tests start skipping, and re-upgrades.
# Everything it does is either a read or a single CREATE DATABASE on a new,
# uniquely named database.
#
#   bash scripts/verify_migrations.sh
#
# Safety, enforced rather than documented:
#   * The three protected databases - privacy_auditor, privacy_auditor_test,
#     privacy_auditor_frozen_20261105_test - are never named as a target. The
#     script aborts if the disposable name matches one of them.
#   * It aborts if the disposable database already exists. It never drops,
#     resets, truncates or reuses an existing database.
#   * The only DDL it issues is CREATE DATABASE, plus Alembic's own migrations
#     against the new database only. There is no DROP anywhere in this file.
#   * No password is printed, typed or passed on a command line. Inside the
#     container psql reads the container's own $POSTGRES_PASSWORD; on the host
#     the URL is composed by scripts/test_database_url.py and captured into a
#     variable.
#
# Everything is also written to a log file, so the output can be pasted back
# in full. Exit code 0 means every check passed.
#
# To re-run after a failure: the script never reuses a database, so add the
# one from the failed run to PROTECTED above and move DISPOSABLE_DB to the
# next free letter. Nothing is dropped and nothing is reused.

set -euo pipefail

# C-53 was verified on 2026-11-05 against privacy_auditor_c53_20261105d_test.
# This run verifies the whole chain, whatever its head currently is.
DISPOSABLE_DB="privacy_auditor_m3b_20261105d_test"
# Never a target. The first three are the project's own databases. The three
# c53 databases are earlier verification runs the team asked to keep, so this
# script must neither reuse nor disturb them:
#   _test   hit the collision guard
#   b_test  gave the operator classes and the en_US.utf8 collation
#   c_test  got as far as the CursorResult failure (C-57)
#   d_test  the run that verified C-53 end to end
#   m3b_20261105_test  reached step 6 before the hard-coded head check failed
PROTECTED=("privacy_auditor" "privacy_auditor_test" "privacy_auditor_frozen_20261105_test"
           "privacy_auditor_c53_20261105_test" "privacy_auditor_c53_20261105b_test"
           "privacy_auditor_c53_20261105c_test" "privacy_auditor_c53_20261105d_test"
           "privacy_auditor_m3b_20261105_test" "privacy_auditor_m3b_20261105b_test"
           "privacy_auditor_m3b_20261105c_test")
# Every earlier disposable database is listed above so none can be reused. Add
# the current one here and move DISPOSABLE_DB on before the next run.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="$ROOT/migration_verification_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$LOG") 2>&1

PY="$ROOT/.venv/bin/python"

step()  { printf '\n==== %s\n' "$*"; }
ok()    { printf '  ok: %s\n' "$*"; }
fail()  { printf '\nFAILED: %s\n' "$*" >&2; printf 'Log: %s\n' "$LOG" >&2; exit 1; }

printf 'Migration verification\nrepository: %s\nstarted: %s\nlog: %s\n' \
  "$ROOT" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$LOG"

# --- 0. Guards ------------------------------------------------------------
step "0. Safety guards"
for name in "${PROTECTED[@]}"; do
  [[ "$DISPOSABLE_DB" == "$name" ]] && fail "the disposable name is a protected database"
done
ok "disposable target is $DISPOSABLE_DB; protected databases are not targeted"

[[ -x "$PY" ]] || fail "$PY not found. Build the venv with Python 3.12 first."
ok "interpreter $("$PY" -V)"

[[ -f .env ]] || fail ".env is missing at the repository root"
ok ".env present (contents never printed)"

# --- 0b. The migration graph ------------------------------------------------
# Head and base are read from Alembic's own script directory. The previous
# version asserted the literal "0002_pattern_ops" and failed the moment
# 0003_collection_event was added - a correctly migrated database reported as
# a failure. That is the same category error as C-56, in a shell script
# instead of a test, so it is fixed the same way: ask the graph.
step "0b. Migration graph"
read -r HEAD_REV BASE_REV CHAIN <<<"$("$PY" - <<'PYEOF'
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from alembic.config import Config
from alembic.script import ScriptDirectory

config = Config(str(ROOT / "backend" / "alembic.ini"))
config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
scripts = ScriptDirectory.from_config(config)

heads = scripts.get_heads()
if len(heads) != 1:
    sys.exit(f"expected one head, found {heads}: a branched history needs a merge")
head = heads[0]
chain = [s.revision for s in scripts.iterate_revisions(head, "base")][::-1]
print(head, chain[0], ",".join(chain))
PYEOF
)" || fail "could not read the migration graph"
[[ -n "$HEAD_REV" && -n "$BASE_REV" ]] || fail "the migration graph produced no head"
ok "chain: ${CHAIN//,/ -> }"
ok "head: $HEAD_REV   base: $BASE_REV"

# --- 1. Compose service ---------------------------------------------------
step "1. Identify the PostgreSQL Compose service from the configuration"
docker compose config --services || fail "docker compose config failed; is this the repository root?"

DB_SERVICE="$(docker compose config --format json \
  | "$PY" -c '
import json,sys
cfg = json.load(sys.stdin)
services = cfg.get("services", {})
hits = [n for n, s in services.items() if str(s.get("image", "")).startswith("postgres")]
if len(hits) != 1:
    sys.exit(f"expected exactly one postgres service, found {hits}")
print(hits[0])
')" || fail "could not determine the PostgreSQL service name"
ok "PostgreSQL service: $DB_SERVICE"

# --- 2. Docker daemon -----------------------------------------------------
step "2. Docker Desktop"
docker info --format 'server version: {{.ServerVersion}}' \
  || fail "the Docker daemon is not reachable. Start Docker Desktop and retry."

# --- 3. Container health --------------------------------------------------
step "3. Container health"
docker compose ps "$DB_SERVICE"
CONTAINER="$(docker compose ps -q "$DB_SERVICE")"
[[ -n "$CONTAINER" ]] || fail "the $DB_SERVICE container is not running. Start it with: docker compose up -d $DB_SERVICE"

for _ in $(seq 1 24); do
  HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER")"
  [[ "$HEALTH" == "healthy" ]] && break
  printf '  health: %s, waiting\n' "$HEALTH"
  sleep 5
done
[[ "$HEALTH" == "healthy" ]] || fail "the container is '$HEALTH', not healthy"
ok "container healthy"

# psql inside the container, reading the password from the container's own
# environment. Nothing is printed and nothing is passed on a command line.
pg() {
  local db="$1"; shift
  # The inner shell shifts the database name off before expanding "$@", so the
  # remaining arguments reach psql exactly once. Writing -d "$1" "$@" instead
  # passes the database name twice, which psql reads as a second dbname.
  docker compose exec -T "$DB_SERVICE" sh -c \
    'db="$1"; shift; PGPASSWORD="$POSTGRES_PASSWORD" exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" "$@"' \
    _ "$db" "$@"
}

# --- 4. Collision check ---------------------------------------------------
step "4. Confirm the disposable name is unused"
pg postgres -c "SELECT datname FROM pg_database ORDER BY datname" || fail "could not list databases"

EXISTS="$(pg postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$DISPOSABLE_DB'" | tr -d '[:space:]')"
if [[ "$EXISTS" == "1" ]]; then
  fail "$DISPOSABLE_DB already exists. Nothing was changed. Choose another unused name (the next free letter, for example privacy_auditor_c53_20261105d_test), add the existing one to PROTECTED, and re-run. Do not drop the existing one."
fi
ok "$DISPOSABLE_DB does not exist"

# --- 5. Create it ---------------------------------------------------------
step "5. Create the disposable database"
pg postgres -c "CREATE DATABASE $DISPOSABLE_DB" || fail "CREATE DATABASE failed"
ok "created $DISPOSABLE_DB"

# --- 6. Migrate -----------------------------------------------------------
step "6. Apply both migrations to the disposable database only"
( cd backend && POSTGRES_DB="$DISPOSABLE_DB" ../.venv/bin/alembic upgrade head ) \
  || fail "alembic upgrade head failed"

REV="$(pg "$DISPOSABLE_DB" -tAc "SELECT version_num FROM alembic_version" | tr -d '[:space:]')"
printf '  alembic_version: %s\n' "$REV"
[[ "$REV" == "$HEAD_REV" ]] || fail "expected head $HEAD_REV, got '$REV'"
ok "migrations recorded at head: $HEAD_REV"

# --- 7. Operator classes from pg_opclass ----------------------------------
# indexdef omits the operator class when it is the default, so a text_ops and a
# text_pattern_ops index print identically. pg_opclass is the only honest
# source, and this is the check the whole correction rests on.
OPCLASS_SQL="SELECT c.relname AS index_name, oc.opcname AS operator_class,
       pg_get_indexdef(i.indexrelid) AS definition
  FROM pg_index i
  JOIN pg_class c  ON c.oid = i.indexrelid
  JOIN pg_class tb ON tb.oid = i.indrelid
  JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
  JOIN pg_opclass oc ON oc.oid = u.oid
 WHERE tb.relname = 'application'
 ORDER BY c.relname, u.ord"

step "7. Index operator classes, read from pg_opclass"
pg "$DISPOSABLE_DB" -c "$OPCLASS_SQL" || fail "could not read operator classes"

check_opclass() {
  local index="$1" expected="$2"
  local actual
  actual="$(pg "$DISPOSABLE_DB" -tAc \
    "SELECT oc.opcname FROM pg_index i
       JOIN pg_class c ON c.oid = i.indexrelid
       JOIN unnest(i.indclass) WITH ORDINALITY AS u(oid, ord) ON TRUE
       JOIN pg_opclass oc ON oc.oid = u.oid
      WHERE c.relname = '$index'" | tr -d '[:space:]')"
  [[ "$actual" == "$expected" ]] \
    || fail "$index has operator class '$actual', expected '$expected'"
  ok "$index -> $expected"
}
check_opclass ix_application_lower_name_pattern    text_pattern_ops
check_opclass ix_application_lower_package_pattern text_pattern_ops
check_opclass ix_application_lower_name            text_ops
check_opclass ix_application_lower_package         text_ops

# --- 8. Collation ---------------------------------------------------------
step "8. Database collation (recorded, not guessed)"
pg postgres -c "SELECT datname, datcollate, datctype FROM pg_database
                 WHERE datname LIKE 'privacy_auditor%' ORDER BY datname" \
  || fail "could not read the collation"

# --- 9. Integration tests, revision applied -------------------------------
step "9. Integration tests against the disposable database"
TEST_DATABASE_URL="$("$PY" scripts/test_database_url.py "$DISPOSABLE_DB")" \
  || fail "could not compose TEST_DATABASE_URL"
export TEST_DATABASE_URL

# Counts are not hard-coded. What matters at head is that **nothing skips**:
# every integration test must be applicable to the fully migrated schema, and
# a skip there would mean a guard fired when it should not have.
HEAD_OUTPUT="$("$PY" -m pytest tests/integration -p no:warnings -v 2>&1)" || {
  printf '%s\n' "$HEAD_OUTPUT"
  fail "integration tests failed at head $HEAD_REV"
}
printf '%s\n' "$HEAD_OUTPUT"
HEAD_SUMMARY="$(printf '%s\n' "$HEAD_OUTPUT" | tail -1)"
grep -q "skipped" <<<"$HEAD_SUMMARY" \
  && fail "a test skipped at head: $HEAD_SUMMARY. Every integration test should be applicable to the fully migrated schema."
ok "integration tests passed with no skips at head: $HEAD_SUMMARY"

# --- 10. Downgrade --------------------------------------------------------
step "10. Downgrade to the baseline, then re-check"
( cd backend && POSTGRES_DB="$DISPOSABLE_DB" ../.venv/bin/alembic downgrade "$BASE_REV" ) \
  || fail "alembic downgrade to $BASE_REV failed"

REV="$(pg "$DISPOSABLE_DB" -tAc "SELECT version_num FROM alembic_version" | tr -d '[:space:]')"
[[ "$REV" == "$BASE_REV" ]] || fail "after downgrade, alembic_version is '$REV'"
ok "downgraded to $BASE_REV"

GONE="$(pg "$DISPOSABLE_DB" -tAc \
  "SELECT count(*) FROM pg_indexes WHERE tablename = 'application'
     AND indexname LIKE '%_pattern'" | tr -d '[:space:]')"
[[ "$GONE" == "0" ]] || fail "$GONE pattern indexes survived the downgrade"
ok "both pattern indexes removed"

KEPT="$(pg "$DISPOSABLE_DB" -tAc \
  "SELECT count(*) FROM pg_indexes WHERE tablename = 'application'
     AND indexname IN ('ix_application_lower_name','ix_application_lower_package')" | tr -d '[:space:]')"
[[ "$KEPT" == "2" ]] || fail "expected the 2 baseline indexes to remain, found $KEPT"
ok "both baseline indexes retained"

step "10b. Integration tests at the baseline - the guards must fire"
# At the baseline, tests that need a later revision MUST skip rather than fail:
# the pattern-index checks need 0002, the collection-event fixture needs 0003,
# and the tests that compare the live schema against the current models only
# agree at head. Skips here are the evidence the guards work; a failure would mean a
# test assumed a schema it had not checked for. The exact number is not
# asserted, because it changes whenever a revision or a test is added - which
# is precisely how the previous hard-coded expectation broke.
BASE_OUTPUT="$("$PY" -m pytest tests/integration -p no:warnings 2>&1)" || {
  printf '%s\n' "$BASE_OUTPUT"
  fail "integration tests failed at the baseline; they should skip, not fail"
}
printf '%s\n' "$BASE_OUTPUT"
BASE_SUMMARY="$(printf '%s\n' "$BASE_OUTPUT" | tail -1)"
grep -q "skipped" <<<"$BASE_SUMMARY" \
  || fail "nothing skipped at the baseline: $BASE_SUMMARY. The revision guards did not fire, so those tests may be passing vacuously."
ok "guards fired as designed: $BASE_SUMMARY"

step "10c. Re-apply the chain"
( cd backend && POSTGRES_DB="$DISPOSABLE_DB" ../.venv/bin/alembic upgrade head ) \
  || fail "re-upgrade failed"
REV="$(pg "$DISPOSABLE_DB" -tAc "SELECT version_num FROM alembic_version" | tr -d '[:space:]')"
[[ "$REV" == "$HEAD_REV" ]] || fail "after re-upgrade, alembic_version is '$REV'"
ok "back at head: $HEAD_REV"

# The round trip must restore the schema, not merely the version row.
for index_name in ix_application_lower_name_pattern ix_application_lower_package_pattern; do
  check_opclass "$index_name" text_pattern_ops
done
STATUS_COL="$(pg "$DISPOSABLE_DB" -tAc \
  "SELECT count(*) FROM information_schema.columns
     WHERE table_name = 'disclosure_snapshot' AND column_name = 'status'" | tr -d '[:space:]')"
[[ "$STATUS_COL" == "1" ]] \
  || fail "disclosure_snapshot.status is missing after the round trip"
ok "collection-event columns restored by the re-upgrade"

# --- 11. Search diagnostic ------------------------------------------------
step "11. ALG-11 search diagnostic"
"$PY" scripts/explain_application_search.py || fail "the diagnostic failed"

# --- 12. Done -------------------------------------------------------------
step "12. Result"
cat <<'EOT'
Every automated check passed. Read these from the output above and report them:

  * step 7  - the four functional indexes and their operator classes
  * step 8  - datcollate, which is still unrecorded in the note
  * step 0b - the chain and its head
  * step 9  - the pytest summary line (no skips expected at head)
  * step 10 - the downgrade, and the baseline summary (skips ARE expected
              there: the revision-gated tests and the collection-event fixture)
  * step 10c- that the re-upgrade restored both the head revision and the
              schema it describes
  * step 11 - whether the two prefix LIKE rows now report "index used: yes"

enable_seqscan is off in step 11, which establishes index ELIGIBILITY only.
At 300-500 rows PostgreSQL will still prefer a sequential scan, and that is
the correct plan. No performance improvement is claimed.

The three protected databases were not touched. The disposable database
remains; nothing depends on it, and removing it is optional.
EOT
printf '\nLog written to: %s\n' "$LOG"
