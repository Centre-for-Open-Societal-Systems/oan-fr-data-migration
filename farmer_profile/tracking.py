"""The audit and progress tables (schema "migration" in the registry's database).

A household's progress and its issues are written in the transaction that
writes its records, so after a crash the two agree. What to write is gathered
in a Batch and applied with the same SQL by a direct run (in the batch's
transaction) and by migration.sql.

  run                 one row per execution
  household_progress  LOADED, FAILED or CHANGED per household: what a rerun resumes from
  migrated_record     every record that is in: its Odoo id and its registry id
  issue               every problem once, OPEN or RESOLVED
"""
import contextlib
import io
import json
import socket
from pathlib import Path

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from .source import FINGERPRINT_VERSION
from .transform import record_id

SCHEMA_SQL = Path(__file__).resolve().parents[1] / "deploy" / "migration-schema.sql"
TABLES = ("run", "household_progress", "migrated_record", "issue")
# The advisory lock a run holds on the registry's database (any constant: "FPMIGRAT")
LOCK = 0x46504D49475241 % 2**62
LOADED, FAILED, CHANGED = "LOADED", "FAILED", "CHANGED"
MAX_VALUE = 1000


class Busy(Exception):
    pass


class NotOurRun(Exception):
    """This run's row is no longer RUNNING: another run took over."""


def exists(engine) -> bool:
    with engine.connect() as conn:
        return all(conn.exec_driver_sql(f"SELECT to_regclass('migration.{t}')").scalar() for t in TABLES)


def ensure(engine):
    """Create the tables if they are not there."""
    if exists(engine):
        return
    raw = engine.raw_connection()
    try:
        raw.cursor().execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        raw.commit()
    except psycopg2.errors.InsufficientPrivilege as exc:
        raw.rollback()
        raise SystemExit(f"the migration's tables are missing and this user may not create them ({str(exc).strip()}): "
                         f"have a DBA run {SCHEMA_SQL.name}") from exc
    finally:
        raw.close()


@contextlib.contextmanager
def run_lock(dsn):
    """One run at a time: a session lock, held on a connection of its own until
    the run ends or dies. Needs a direct connection (not PgBouncer in
    transaction mode)."""
    engine = create_engine(dsn, poolclass=NullPool, isolation_level="AUTOCOMMIT",
                           connect_args={"application_name": "farmer-profile-migration-lock", "keepalives_idle": 30,
                                         "keepalives_interval": 10, "keepalives_count": 3})
    conn = engine.connect()
    try:
        if not conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({LOCK})").scalar():
            other = None
            if conn.exec_driver_sql("SELECT to_regclass('migration.run')").scalar():
                other = conn.exec_driver_sql("SELECT run_id, host, started_at FROM migration.run "
                                             "WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1").first()
            raise Busy("another migration run is active on this registry"
                       + (f": {other[0]} on {other[1]}, started {other[2]:%Y-%m-%d %H:%M:%S %Z}" if other else "")
                       + ". Wait for it to end. (If it was just killed, its connection can take a moment to close.)")
        yield conn
    finally:
        with contextlib.suppress(Exception):
            conn.close()
        engine.dispose()


# -- runs ---------------------------------------------------------------------------------

def start_run(engine, run_id, mode, arguments, source_uuid) -> list[str]:
    """Under the lock. A run still marked RUNNING was killed: mark it so. Returns those."""
    with engine.begin() as conn:
        killed = conn.exec_driver_sql("UPDATE migration.run SET status = 'INTERRUPTED', finished_at = clock_timestamp() "
                                      "WHERE status = 'RUNNING' RETURNING run_id").scalars().all()
        conn.exec_driver_sql("INSERT INTO migration.run (run_id, mode, arguments, source_uuid, status, host) "
                             "VALUES (%s, %s, %s, %s, 'RUNNING', %s)",
                             (run_id, mode, arguments, source_uuid, socket.gethostname()))
    return list(killed)


def finish_run(engine, run_id, status, counts, error=None):
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE migration.run SET status = %s, finished_at = clock_timestamp(), counts = %s, "
                             "error = %s WHERE run_id = %s AND status = 'RUNNING'",
                             (status, json.dumps(counts, default=str), plain(error) if error else None, run_id))


def fence(cur, run_id):
    """In a batch's transaction: this run must still be the one running."""
    cur.execute("SELECT 1 FROM migration.run WHERE run_id = %s AND status = 'RUNNING' FOR SHARE", (run_id,))
    if cur.fetchone() is None:
        raise NotOurRun(f"run {run_id} is no longer marked RUNNING: another run took over")


def other_sources(engine, source_uuid) -> list[str]:
    """The farmer profile databases the registry's households came from, when this one is not among them."""
    with engine.connect() as conn:
        known = conn.exec_driver_sql("""
            SELECT DISTINCT r.source_uuid FROM migration.run r WHERE r.source_uuid IS NOT NULL AND EXISTS (
              SELECT 1 FROM migration.household_progress p
               WHERE p.first_run_id = r.run_id AND p.status <> 'FAILED')""").scalars().all()
    return [] if not known or source_uuid in known else list(known)


def retire(engine, planned_keys):
    """After a run over every farmer: a household that failed and is no longer in
    farmer profile under that key has nothing left to retry. Its issues are resolved."""
    with engine.begin() as conn:
        gone = conn.exec_driver_sql("DELETE FROM migration.household_progress p WHERE status = 'FAILED' "
                                    "AND NOT household_key = ANY(%s) AND NOT EXISTS (SELECT 1 FROM "
                                    "migration.migrated_record m WHERE m.household_key = p.household_key) "
                                    "RETURNING household_key", (list(planned_keys),)).scalars().all()
        conn.exec_driver_sql("UPDATE migration.issue SET status = 'RESOLVED', resolved_at = clock_timestamp() "
                             "WHERE status = 'OPEN' AND household_key = ANY(%s)", (list(gone),))


# -- what is already in --------------------------------------------------------------------

class State:
    """What the tables say about a batch's units."""

    def __init__(self, engine, some_units):
        self.progress, self.owner, self.records = {}, {}, {}
        keys = [u.key for u in some_units]
        farmers = [f for u in some_units for f in u.farmers]
        households = [h for u in some_units for h in u.households]
        with engine.connect() as conn:
            for key, status, fingerprint, version in conn.exec_driver_sql(
                    "SELECT household_key, status, fingerprint, fingerprint_version FROM migration.household_progress "
                    "WHERE household_key = ANY(%s)", (keys,)):
                self.progress[key] = (status, fingerprint, version)
            for kind, odoo_id, key in conn.exec_driver_sql(
                    "SELECT kind, odoo_id, household_key FROM migration.migrated_record "
                    "WHERE (kind = 'farmer' AND odoo_id = ANY(%s)) OR (kind = 'household' AND odoo_id = ANY(%s))",
                    (farmers, households)):
                self.owner[(kind, odoo_id)] = key
            for kind, odoo_id, key in conn.exec_driver_sql(
                    "SELECT kind, odoo_id, household_key FROM migration.migrated_record "
                    "WHERE household_key = ANY(%s) AND kind IN ('farmer', 'household')",
                    (list(set(self.owner.values())),)):
                self.records.setdefault(key, set()).add((kind, odoo_id))

    def plan(self, unit) -> dict:
        """What to do with a unit: {"do": "load" | "compare" | "recomposed", ...}."""
        wanted = records_of(unit)
        owners = {self.owner[r] for r in wanted if r in self.owner}
        status, fingerprint, version = self.progress.get(unit.key, (None, None, None))
        if not owners:
            return {"do": "load"}
        if owners != {unit.key} or self.records[unit.key] != wanted:
            return {"do": "recomposed", "owners": sorted(owners)}
        return {"do": "compare", "fingerprint": fingerprint, "version": version, "status": status}


class NoState:
    """Without the tables (a dry run before the first run): everything is new."""

    def plan(self, unit):
        return {"do": "load"}


def records_of(unit) -> set:
    """What makes a unit the one it is: its farmers and households."""
    return {("farmer", f) for f in unit.farmers} | {("household", h) for h in unit.households}


def links(unit, data, gen2_ids) -> list[tuple]:
    """(kind, Odoo id, registry id) of a unit's records. data: its rows as read;
    gen2_ids: the ids of its finished rows. A record that is not migrated (a
    dropped phone, a skipped crop) is not among them."""
    wanted = [(kind, row["id"], record_id(kind, row["id"])) for kind, part in (
        ("household", "households"), ("farmer", "farmers"), ("member", "memberships"), ("phone", "phones"),
        ("land", "lands"), ("crop", "crops")) for row in data[part]]
    if not unit.households:
        for f in unit.farmers:
            wanted += [("solo_household", f, record_id("household", f"solo-{f}")),
                       ("solo_member", f, record_id("member", f"solo-{f}"))]
    return [link for link in wanted if link[2] in gen2_ids]


# -- what a batch writes -------------------------------------------------------------------

def plain(value, limit=MAX_VALUE) -> str:
    """Text Postgres takes: no NUL, no lone surrogate, not endless."""
    text = "" if value is None else str(value)
    text = text.replace("\x00", "\\x00").encode("utf-8", "backslashreplace").decode("utf-8")
    return text if len(text) <= limit else text[:limit] + "..."


_STAGING = {
    "mig_track_progress": ("household_key text, status text, farmer_ids bigint[], fingerprint jsonb, "
                           "fingerprint_version integer, seen_fingerprint jsonb, adopted boolean, error_class text, "
                           "error text, resolves text"),
    "mig_track_record": "kind text, odoo_id bigint, gen2_id text, household_key text",
    "mig_track_issue": ("household_key text, severity text, entity text, odoo_id text, field text, value text, "
                        "reason text"),
}


class Batch:
    """The tracking rows of some units, in the staging tables' order."""

    def __init__(self):
        self.rows = {name: [] for name in _STAGING}

    def _progress(self, unit, status, fingerprint=None, seen=None, adopted=False, error_class=None, error=None,
                  resolves="none"):
        self.rows["mig_track_progress"].append((
            unit.key, status, "{" + ",".join(map(str, unit.farmers)) + "}", fingerprint,
            FINGERPRINT_VERSION if fingerprint else None, seen, adopted, error_class, plain(error) if error else None,
            resolves))

    def _issue(self, unit, severity, entity, odoo_id="", field="", value="", reason=""):
        self.rows["mig_track_issue"].append((unit.key, severity, entity, plain(odoo_id), plain(field), plain(value),
                                             plain(reason)))

    def issues(self, unit, issues):
        for i in issues:
            self._issue(unit, i["severity"], i["entity"], i["odoo_id"], i["field"], i["value"], i["reason"])

    def loaded(self, unit, fingerprint, issues, records, adopted=False):
        """records: links()."""
        self._progress(unit, LOADED, fingerprint=fingerprint, seen=fingerprint, adopted=adopted, resolves="all")
        self.rows["mig_track_record"] += [(kind, odoo_id, gen2_id, unit.key) for kind, odoo_id, gen2_id in records]
        self.issues(unit, issues)

    def unchanged_again(self, unit, fingerprint):
        """It was CHANGED; farmer profile is back to what was migrated."""
        self._progress(unit, LOADED, seen=fingerprint, resolves="changed")

    def failed(self, unit, error_class, error, issues=()):
        self._progress(unit, FAILED, error_class=error_class, error=error, resolves="failed")
        self._issue(unit, "failed", "household", ", ".join(map(str, unit.farmers)), error_class, unit.key, error)
        self.issues(unit, issues)

    def changed(self, unit, fingerprint, what):
        self._progress(unit, CHANGED, seen=fingerprint, resolves="changed")
        self._issue(unit, "changed", "household", ", ".join(map(str, unit.farmers)), "", unit.key, what)

    def __bool__(self):
        return bool(self.rows["mig_track_progress"])


def staging_sql() -> list[str]:
    return [f"CREATE TEMP TABLE IF NOT EXISTS {name} ({columns}) ON COMMIT DROP" for name, columns in _STAGING.items()]


def apply_sql(run_id: str) -> list[str]:
    run = "'" + run_id.replace("'", "''") + "'"
    return [f"""INSERT INTO migration.household_progress AS p
       (household_key, status, farmer_ids, fingerprint, fingerprint_version, seen_fingerprint, adopted, attempts,
        error_class, error, first_run_id, last_run_id)
SELECT household_key, status, farmer_ids, fingerprint, fingerprint_version, seen_fingerprint, adopted, 1,
       error_class, error, {run}, {run}
  FROM mig_track_progress
ON CONFLICT (household_key) DO UPDATE SET
       status = excluded.status, farmer_ids = excluded.farmer_ids,
       fingerprint = coalesce(excluded.fingerprint, p.fingerprint),
       fingerprint_version = coalesce(excluded.fingerprint_version, p.fingerprint_version),
       seen_fingerprint = coalesce(excluded.seen_fingerprint, p.seen_fingerprint),
       adopted = p.adopted OR excluded.adopted, attempts = p.attempts + 1,
       error_class = excluded.error_class, error = excluded.error,
       first_run_id = CASE WHEN p.status = 'FAILED' AND excluded.status = 'LOADED' THEN excluded.first_run_id
                           ELSE p.first_run_id END,
       last_run_id = excluded.last_run_id, updated_at = clock_timestamp()""",
            """INSERT INTO migration.migrated_record (kind, odoo_id, gen2_id, household_key)
SELECT kind, odoo_id, gen2_id, household_key FROM mig_track_record
ON CONFLICT (kind, odoo_id) DO NOTHING""",
            """UPDATE migration.issue i SET status = 'RESOLVED', resolved_at = clock_timestamp()
  FROM mig_track_progress t
 WHERE t.household_key = i.household_key AND i.status = 'OPEN'
   AND (t.resolves = 'all' OR t.resolves = i.severity)
   AND NOT EXISTS (SELECT 1 FROM mig_track_issue n
                    WHERE n.household_key = i.household_key AND n.severity = i.severity AND n.entity = i.entity
                      AND n.odoo_id = i.odoo_id AND n.field = i.field AND n.value = i.value AND n.reason = i.reason)""",
            f"""INSERT INTO migration.issue
       (household_key, severity, entity, odoo_id, field, value, reason, first_run_id, last_run_id)
SELECT DISTINCT household_key, severity, entity, odoo_id, field, value, reason, {run}, {run} FROM mig_track_issue
ON CONFLICT (household_key, severity, entity, odoo_id, field, md5(value), md5(reason)) DO UPDATE SET
       status = 'OPEN', resolved_at = NULL, last_run_id = excluded.last_run_id, last_seen = clock_timestamp()"""]


def apply(cur, run_id, batch: Batch):
    """Write a batch's tracking rows, in the caller's transaction."""
    from .load import copy_data
    for sql in staging_sql():
        cur.execute(sql)
    for name, rows in batch.rows.items():
        cur.execute(f"TRUNCATE {name}")
        if rows:
            cur.copy_expert(f"COPY {name} FROM STDIN", io.StringIO(copy_data(rows)))
    for sql in apply_sql(run_id):
        cur.execute(sql)


def record(engine, run_id, batch: Batch):
    """Write tracking rows on their own: failures, and what needed no loading."""
    if not batch:
        return
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        fence(cur, run_id)
        apply(cur, run_id, batch)
        raw.commit()
    except Exception:
        with contextlib.suppress(Exception):
            raw.rollback()
        raise
    finally:
        raw.close()


def loaded_by(engine, run_id, keys) -> set:
    """Of these units, the ones this run already committed (a commit whose answer was lost)."""
    with engine.connect() as conn:
        return set(conn.exec_driver_sql("SELECT household_key FROM migration.household_progress WHERE status = 'LOADED' "
                                        "AND last_run_id = %s AND household_key = ANY(%s)", (run_id, list(keys))).scalars())


# -- migration.sql ------------------------------------------------------------------------

def watermark(engine) -> str | None:
    with engine.connect() as conn:
        return conn.exec_driver_sql("SELECT max(updated_at)::text FROM migration.household_progress").scalar() \
            if exists(engine) else None


def sql_guard(run_id, mark: str | None, source_uuid) -> list[str]:
    """Statements that open migration.sql: refuse beside a running migration, twice, or on a registry
    that has been migrated into since the file was written."""
    q = lambda v: "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"  # noqa: E731
    return [f"""DO $guard$
BEGIN
  IF NOT pg_try_advisory_xact_lock({LOCK}) THEN
    RAISE EXCEPTION 'another migration run is active on this registry';
  END IF;
END $guard$""",
            SCHEMA_SQL.read_text(encoding="utf-8").strip().rstrip(";"),
            f"""DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM migration.run WHERE run_id = {q(run_id)}) THEN
    RAISE EXCEPTION 'this file has already been applied';
  END IF;
  IF (SELECT max(updated_at) FROM migration.household_progress) IS DISTINCT FROM {q(mark)}::timestamptz THEN
    RAISE EXCEPTION 'the registry has been migrated into since this file was written: write it again';
  END IF;
END $guard$""",
            f"""INSERT INTO migration.run (run_id, mode, source_uuid, status, finished_at)
VALUES ({q(run_id)}, 'sql-file', {q(source_uuid)}, 'COMPLETED', clock_timestamp())"""]


# -- reading it back -----------------------------------------------------------------------

ISSUE_COLUMNS = ["status", "severity", "household", "entity", "odoo_id", "field", "value", "reason", "first_run",
                 "last_run"]


def issues(engine):
    """Every issue of every run, open ones first."""
    with engine.connect().execution_options(stream_results=True) as conn:
        for row in conn.exec_driver_sql("""
                SELECT status, severity, household_key, entity, odoo_id, field, value, reason, first_run_id, last_run_id
                  FROM migration.issue
                 ORDER BY status, array_position(ARRAY['failed','changed','skipped','dropped','check'], severity), issue_id"""):
            yield dict(zip(ISSUE_COLUMNS, row))


def households(engine, status) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("""
            SELECT p.household_key, p.farmer_ids, p.error_class, p.error, p.attempts, p.first_run_id, p.last_run_id,
                   p.updated_at, (SELECT string_agg(i.reason, '; ') FROM migration.issue i
                                   WHERE i.household_key = p.household_key AND i.status = 'OPEN'
                                     AND i.severity = 'changed') AS what
              FROM migration.household_progress p WHERE p.status = %s ORDER BY p.household_key""", (status,)).mappings()
        return [dict(r) for r in rows]


def runs(engine, limit=200) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.exec_driver_sql(
            "SELECT run_id, mode, status, started_at, finished_at, host, arguments, counts, error FROM migration.run "
            "ORDER BY started_at DESC LIMIT %s", (limit,)).mappings()]


def totals(engine) -> dict:
    with engine.connect() as conn:
        out = {s: (n, f) for s, n, f in conn.exec_driver_sql(
            "SELECT status, count(*), coalesce(sum(cardinality(farmer_ids)), 0) FROM migration.household_progress "
            "GROUP BY status")}
        open_issues = dict(conn.exec_driver_sql(
            "SELECT severity, count(*) FROM migration.issue WHERE status = 'OPEN' GROUP BY severity").all())
        resolved = conn.exec_driver_sql("SELECT count(*) FROM migration.issue WHERE status = 'RESOLVED'").scalar()
    return {"households": out, "open": open_issues, "resolved": resolved}


def missing_records(engine, models) -> dict:
    """kind -> how many farmers and households the tables say are in, and the registry does not have."""
    out = {}
    raw = engine.raw_connection()
    try:
        for kind, model in (("farmer", "Farmer"), ("household", "Household")):
            table = getattr(models, f"G2PRegister{model}").__tablename__
            cur = raw.cursor(name=f"tracked_{kind}")
            cur.itersize = 10000
            cur.execute("SELECT odoo_id FROM migration.migrated_record WHERE kind = %s", (kind,))
            check, missing = raw.cursor(), 0
            while chunk := cur.fetchmany(10000):
                ids = [record_id(kind, odoo_id) for (odoo_id,) in chunk]
                check.execute(f'SELECT count(*) FROM "{table}" WHERE internal_record_id = ANY(%s)', (ids,))
                missing += len(ids) - check.fetchone()[0]
            out[kind] = missing
            cur.close()
        raw.rollback()
    finally:
        raw.close()
    return out
