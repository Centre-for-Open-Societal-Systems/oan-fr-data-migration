"""The health of the migration, in numbers.

The test for a metric: did the migration lose, change or fail to load something?
Every Gen1 record is put in exactly one group (Reconciliation), and the rest says
how the runs went, whether the data arrived, and whether it can be traced.

Counts only. What is stored and shown holds no names, numbers, ids or error
messages; an error is its kind. Farmer profile is only read. In the registry,
only temporary tables are written, and the results (schema migration_report).

A record is the migration's when migration.migrated_record has it, and edited in
Gen2 when the registry's history has a row for it that is not the migration's: the
registry writes one for every approved change. History the migration brings from
Gen1 must be in migrated_record too (its history_record_id as gen2_id), like every
record it writes. Neither depends on what created_by and last_approved_by hold.
"""
import collections
import contextlib
import dataclasses
import io
from pathlib import Path

import psycopg2
from sqlalchemy import text

from . import fieldmap as F
from . import source
from .load import copy_data
from .transform import LARGE_PARCEL_HA, record_id

SCHEMA_SQL = Path(__file__).resolve().parents[1] / "deploy" / "migration-report-schema.sql"
GREEN, AMBER, RED, INFO, NOT_CHECKED = "GREEN", "AMBER", "RED", "INFO", "NOT CHECKED"
RECONCILIATION, RUNS, QUALITY, IDS, SPLITS, VERIFY = ("Reconciliation", "Run health", "Quality", "IDs", "Splits", "Verify")
AREAS = (RECONCILIATION, RUNS, QUALITY, IDS)

KINDS = {"farmer": "Farmer", "household": "Household", "member": "HouseholdMember", "phone": "FarmerPhone",
         "land": "Land", "crop": "Crop"}
# How the issues name a record of the kind
_ENTITY = {"farmer": "farmer", "household": "household", "member": "household_member", "phone": "phone",
           "land": "land", "crop": "crop"}
GROUPS = {"loaded": "Loaded", "failed": "Failed",
          "not_added": "Not added",
          "left_out": "Left out",
          "out_of_scope": "Out of scope",
          "not_reached": "Not reached yet", "unexplained": "Unexplained"}
# Why a record is out of scope: when it belongs to nobody in scope, and when it is ruled out itself.
# Draft, rejected and disabled farmers are in scope: they are migrated. Who is in scope is what
# source.units says, so a change of the migration's rules (e.g. archived farmers) is a change here too.
_OUT_OF_SCOPE = {"farmer": ("The farmer is archived in Gen1", ""),
                 "household": ("No active farmer is in it", ""),
                 "member": ("No active farmer is in the household", "The membership has ended in Gen1"),
                 "phone": ("The farmer is archived in Gen1", "The number is disabled in Gen1"),
                 "land": ("The farmer is archived in Gen1", ""),
                 "crop": ("The farmer is archived in Gen1", "")}
# What verification.structure_checks asks for, as what is wrong when it is not so
RULES = {"every Farmer links to a Household": "Farmers without their household",
         "every HouseholdMember links to a Household": "Members without their household",
         "every FarmerPhone links to a Farmer": "Phones without their farmer",
         "every Land links to a Farmer": "Lands without their farmer",
         "every Crop links to a Land": "Crops without their land",
         "every household has exactly one head member": "Households without exactly one head",
         "every farmer with a phone has exactly one primary number": "Farmers with phones, and not exactly one primary"}
MADE = "Made for lone farmers"


@dataclasses.dataclass
class Measure:
    area: str
    metric: str
    count: int | None = None
    total: int | None = None
    result: str = INFO
    target: str = ""
    record_type: str = ""
    split_by: str = ""
    split_value: str = ""
    blocking: bool = False


def worst(measures) -> str:
    """RED if a blocking one is; else AMBER if any is not as it should be, or not checked yet."""
    if any(m.blocking and m.result == RED for m in measures):
        return RED
    return AMBER if any(m.result in (RED, AMBER, NOT_CHECKED) for m in measures) else GREEN


class NotMeasurable(Exception):
    pass


# -- storing ------------------------------------------------------------------------------

def exists(engine) -> bool:
    with engine.connect() as conn:
        return all(conn.exec_driver_sql(f"SELECT to_regclass('migration_report.{t}')").scalar()
                   for t in ("snapshot", "measure"))


def ensure(engine):
    if exists(engine):
        return
    raw = engine.raw_connection()
    try:
        raw.cursor().execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        raw.commit()
    except psycopg2.errors.InsufficientPrivilege as exc:
        raw.rollback()
        raise NotMeasurable(f"the report's tables are missing and this user may not create them: have a DBA run "
                            f"{SCHEMA_SQL.name}") from exc
    finally:
        raw.close()


_COLUMNS = [f.name for f in dataclasses.fields(Measure)]


def save(engine, taken_by, run_id, measures, overall) -> int:
    ensure(engine)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("INSERT INTO migration_report.snapshot (taken_by, run_id, overall) VALUES (%s, %s, %s) "
                    "RETURNING snapshot_id", (taken_by, run_id, overall))
        snapshot = cur.fetchone()[0]
        rows = [(snapshot, *(getattr(m, c) for c in _COLUMNS)) for m in measures]
        cur.copy_expert(f"COPY migration_report.measure (snapshot_id, {', '.join(_COLUMNS)}) FROM STDIN",
                        io.StringIO(copy_data(rows)))
        raw.commit()
        return snapshot
    except Exception:
        with contextlib.suppress(Exception):
            raw.rollback()
        raise
    finally:
        raw.close()


def history(engine, limit=10) -> list[tuple[dict, dict]]:
    """The latest snapshots, oldest first: (snapshot, (area, metric, record_type) -> its count, total, result)."""
    with engine.connect() as conn:
        taken = [dict(r) for r in conn.exec_driver_sql(
            "SELECT snapshot_id, taken_at, taken_by, run_id, overall FROM migration_report.snapshot "
            "WHERE taken_by <> 'verify' ORDER BY snapshot_id DESC LIMIT %s", (limit,)).mappings()]
        out = []
        for s in reversed(taken):
            out.append((s, {(r[0], r[1], r[2]): tuple(r[3:]) for r in conn.exec_driver_sql(
                "SELECT area, metric, record_type, count, total, result FROM migration_report.measure "
                "WHERE snapshot_id = %s AND split_by = ''", (s["snapshot_id"],))}))
        return out


def save_verify(engine, rows, everything):
    """verify.py's checks, for the health report: what was compared and what agreed. Their
    details hold ids and values and are not kept."""
    if not everything:
        return
    measures = {}
    for c in rows:
        number = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None  # noqa: E731
        measures[c["check"]] = Measure(VERIFY, c["check"], number(c["found"]), number(c["expected"]),
                                       {"PASS": GREEN, "FAIL": RED, "WARN": AMBER}[c["result"]], record_type=c["group"])
    run = None
    with engine.connect() as conn:
        if conn.exec_driver_sql("SELECT to_regclass('migration.run')").scalar():
            run = conn.exec_driver_sql("SELECT run_id FROM migration.run WHERE mode <> 'finalize' "
                                       "ORDER BY started_at DESC LIMIT 1").scalar()
    result = collections.Counter(c["result"] for c in rows)
    save(engine, "verify", run, list(measures.values()), RED if result["FAIL"] else AMBER if result["WARN"] else GREEN)


# -- measuring ----------------------------------------------------------------------------

class Health:
    """One measurement. connection: psycopg2, on the registry; conn: on farmer profile."""

    def __init__(self, raw, conn, models, log, status=None):
        """status: of the run that is measuring itself, which is still marked RUNNING."""
        self.raw, self.conn, self.models, self.log, self.status = raw, conn, models, log, status
        self.cur = raw.cursor()
        self.measures = []
        self.tables = {k: getattr(models, f"G2PRegister{r}").__tablename__ for k, r in KINDS.items()}
        self.history = {k: getattr(models, f"G2PRegisterHistory{r}").__tablename__ for k, r in KINDS.items()}

    def add(self, *args, **kw):
        self.measures.append(Measure(*args, **kw))

    def rows(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur.fetchall()

    def one(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur.fetchone()[0]

    def mine(self, alias):
        return f"{alias}.internal_record_id IN (SELECT gen2_id FROM migration.migrated_record)"

    def edited(self, kind, alias):
        return (f"EXISTS (SELECT 1 FROM {self.history[kind]} e WHERE e.internal_record_id = {alias}.internal_record_id "
                "AND e.history_record_id NOT IN (SELECT gen2_id FROM migration.migrated_record))")

    def zero(self, area, metric, count, total=None, blocking=False, bad=None, **kw):
        """A metric that should be 0."""
        self.add(area, metric, count, total, GREEN if not count else (bad or (RED if blocking else AMBER)),
                 target="0", blocking=blocking, **kw)

    def all_of(self, area, metric, count, total, blocking=False, **kw):
        """A metric that should be all of the total."""
        self.add(area, metric, count, total, GREEN if count == total else (RED if blocking else AMBER),
                 target="100%", blocking=blocking, **kw)

    def measure(self):
        if not self.one("SELECT to_regclass('migration.household_progress') IS NOT NULL") \
                or not self.one("SELECT EXISTS (SELECT 1 FROM migration.household_progress)"):
            raise NotMeasurable("nothing has been migrated yet (the migration's tables are missing or empty)")
        self.copy_gen1()
        self.reconcile()
        self.run_health()
        self.quality()
        self.ids()
        return self.measures

    # -- Gen1's records, in temporary tables beside the registry's -----------------------

    def copy(self, table, query, params=None, change=None):
        """change: what is written for a row as read."""
        cur = self.conn.cursor(name=f"copy_{table}")
        cur.itersize = 50000
        cur.execute(query, params)
        while rows := cur.fetchmany(50000):
            self.cur.copy_expert(f"COPY {table} FROM STDIN", io.StringIO(copy_data(map(change, rows) if change else rows)))
        cur.close()

    def copy_gen1(self):
        chosen = source.select_farmers(self.conn)
        planned, _ = source.units(self.conn, chosen)
        self.units = {u.key: u for u in planned}
        self.cur.execute("""
            CREATE TEMP TABLE h_farmer_unit (farmer_id bigint, key text) ON COMMIT DROP;
            CREATE TEMP TABLE h_household_unit (household_id bigint, key text) ON COMMIT DROP;
            CREATE TEMP TABLE h_gen1 (kind text, odoo_id bigint, farmer_id bigint, household_id bigint, ruled_out boolean,
              gen2_id text) ON COMMIT DROP;
            CREATE TEMP TABLE h_made (kind text, gen2_id text) ON COMMIT DROP;
            CREATE TEMP TABLE h_person (farmer_id bigint, region text, source text, state text, legacy_number text,
              uid text, fan text, rid text, odk text) ON COMMIT DROP;
            CREATE TEMP TABLE h_land (odoo_id bigint, land_id text) ON COMMIT DROP;""")
        self.cur.copy_expert("COPY h_farmer_unit FROM STDIN", io.StringIO(copy_data(
            (f, u.key) for u in planned for f in u.farmers)))
        self.cur.copy_expert("COPY h_household_unit FROM STDIN", io.StringIO(copy_data(
            (h, u.key) for u in planned for h in u.households)))
        self.cur.copy_expert("COPY h_made FROM STDIN", io.StringIO(copy_data(
            (kind, record_id(kind, f"solo-{f}")) for u in planned if not u.households for f in u.farmers
            for kind in ("household", "member"))))
        with_id = lambda row: (*row, record_id(row[0], row[1]))  # noqa: E731
        # people in scope only as members of a farmer's household count as farmers too
        people = "(p.is_registrant OR p.id = ANY(%s)) AND NOT p.is_group"
        registrants = set(chosen)
        extra = [f for u in planned for f in u.farmers if f not in registrants]
        self.copy("h_gen1", f"SELECT 'farmer', p.id, p.id, NULL, false FROM res_partner p WHERE {people}", (extra,), with_id)
        self.copy("h_gen1", "SELECT 'household', p.id, NULL, p.id, false FROM res_partner p WHERE p.is_group "
                            "AND (p.is_registrant OR p.id = ANY(%s))", ([h for u in planned for h in u.households],), with_id)
        self.copy("h_gen1", "SELECT 'member', m.id, m.individual, m.\"group\", coalesce(m.is_ended, false) "
                            "FROM g2p_group_membership m WHERE m.\"group\" IS NOT NULL", None, with_id)
        for kind, table, ruled_out in (("phone", "g2p_phone_number", "x.disabled IS NOT NULL"),
                                       ("land", "g2p_land_information", "false"),
                                       ("crop", "g2p_crop_information", "false")):
            self.copy("h_gen1", f"SELECT '{kind}', x.id, x.partner_id, NULL, {ruled_out} FROM {table} x "
                                f"JOIN res_partner p ON p.id = x.partner_id WHERE {people}", (extra,), with_id)
        first = lambda t: ("(SELECT r.value FROM g2p_reg_id r JOIN g2p_id_type t ON t.id = r.id_type "  # noqa: E731
                           f"WHERE r.partner_id = p.id AND t.name = '{t}' ORDER BY r.id LIMIT 1)")
        self.copy("h_person", f"""
            SELECT p.id, reg.name, src.name, coalesce(p.state, '(none)'), nullif(p.farmer_id, ''),
                   nullif(replace({first('UID')}, ' ', ''), ''), nullif(replace({first('FAN')}, ' ', ''), ''),
                   nullif({first('RID')}, ''), nullif({first('Farmer ODK ACK ID')}, '')
              FROM res_partner p LEFT JOIN g2p_region reg ON reg.id = p.region
              LEFT JOIN g2p_import_source src ON src.id = p.rec_import_source WHERE {people}""", (extra,))
        self.copy("h_land", "SELECT id, land_id FROM g2p_land_information WHERE coalesce(land_id, '') <> ''")
        for t in ("h_farmer_unit", "h_household_unit", "h_gen1", "h_person", "h_land"):
            self.cur.execute(f"ANALYZE {t}")

    # -- where every Gen1 record went -------------------------------------------------------

    def reconcile(self):
        self.cur.execute("""
            CREATE TEMP TABLE h_class (kind text, odoo_id bigint, farmer_id bigint, key text, grp text, why text) ON COMMIT DROP;
            CREATE TEMP TABLE h_owned ON COMMIT DROP AS
              SELECT DISTINCT u.key FROM h_farmer_unit u JOIN migration.migrated_record m
                  ON m.kind = 'farmer' AND m.odoo_id = u.farmer_id
              UNION SELECT u.key FROM h_household_unit u JOIN migration.migrated_record m
                  ON m.kind = 'household' AND m.odoo_id = u.household_id""")
        for kind, table in self.tables.items():
            unit = "h_household_unit h ON h.household_id = g.household_id" if kind in ("household", "member") \
                else "h_farmer_unit h ON h.farmer_id = g.farmer_id"
            named = "g.farmer_id" if kind == "member" else "g.odoo_id"  # a skipped member is named by the person
            none, ruled = _OUT_OF_SCOPE[kind]
            self.cur.execute(f"""
                INSERT INTO h_class
                SELECT g.kind, g.odoo_id, g.farmer_id, h.key, CASE
                  WHEN m.odoo_id IS NOT NULL THEN CASE WHEN r.internal_record_id IS NOT NULL THEN 'loaded' ELSE 'unexplained' END
                  WHEN g.ruled_out OR h.key IS NULL THEN 'out_of_scope'
                  WHEN p.status = 'FAILED' THEN 'failed'
                  WHEN p.status = 'CHANGED' THEN 'not_added'
                  WHEN p.status IS NULL THEN CASE WHEN o.key IS NULL THEN 'not_reached' ELSE 'not_added' END
                  WHEN EXISTS (SELECT 1 FROM migration.issue i WHERE i.household_key = h.key
                                AND i.severity IN ('skipped', 'dropped') AND i.entity = %s AND i.odoo_id = {named}::text)
                    THEN 'left_out'
                  ELSE 'look' END, CASE WHEN h.key IS NULL THEN '{none}' ELSE '{ruled}' END
                  FROM h_gen1 g LEFT JOIN {unit}
                  LEFT JOIN migration.migrated_record m ON m.kind = g.kind AND m.odoo_id = g.odoo_id
                  LEFT JOIN {table} r ON r.internal_record_id = m.gen2_id
                  LEFT JOIN migration.household_progress p ON p.household_key = h.key
                  LEFT JOIN h_owned o ON o.key = h.key
                 WHERE g.kind = %s""", (_ENTITY[kind], kind))
        self.look()
        counts = collections.defaultdict(collections.Counter)
        for kind, grp, n in self.rows("SELECT kind, grp, count(*) FROM h_class GROUP BY 1, 2"):
            counts[kind][grp] = n
        for kind in KINDS:
            total, mine = sum(counts[kind].values()), counts[kind]
            self.add(RECONCILIATION, "In Gen1", total, record_type=kind)
            for grp, label in GROUPS.items():
                if grp == "unexplained":
                    self.zero(RECONCILIATION, label, mine[grp], total, blocking=True, record_type=kind)
                elif grp == "not_reached":
                    self.zero(RECONCILIATION, label, mine[grp], total, record_type=kind)
                else:
                    self.add(RECONCILIATION, label, mine[grp], total, record_type=kind)
            in_scope = total - mine["out_of_scope"]
            self.all_of(RECONCILIATION, "Loaded, of what should be", mine["loaded"], in_scope, record_type=kind)
            gone = self.one("SELECT count(*) FROM migration.migrated_record m WHERE m.kind = %s AND NOT EXISTS "
                            "(SELECT 1 FROM h_gen1 g WHERE g.kind = m.kind AND g.odoo_id = m.odoo_id)", (kind,))
            self.add(RECONCILIATION, "Loaded, and no longer in Gen1", gone, record_type=kind)
            made = self.one("SELECT count(*) FROM migration.migrated_record WHERE kind = %s", (f"solo_{kind}",))
            self.add(RECONCILIATION, MADE, made, record_type=kind)
        for kind, why, n in self.rows("SELECT kind, why, count(*) FROM h_class WHERE grp = 'out_of_scope' GROUP BY 1, 2 "
                                      "ORDER BY 1, 3 DESC"):
            self.add(RECONCILIATION, "Out of scope, by reason", n, record_type=kind, split_by="Why", split_value=why)
        for by in ("region", "source", "state"):
            for value, loaded, total in self.rows(f"""
                    SELECT coalesce(p.{by}, '(none)'), count(*) FILTER (WHERE c.grp = 'loaded'), count(*)
                      FROM h_class c JOIN h_person p ON p.farmer_id = c.farmer_id
                     WHERE c.kind = 'farmer' AND c.grp <> 'out_of_scope' GROUP BY 1 ORDER BY 3 DESC, 1"""):
                self.add(SPLITS, "Farmers loaded", loaded, total, record_type="farmer",
                         split_by={"region": "Region", "source": "Import source", "state": "Gen1 status"}[by],
                         split_value=value)

    def look(self):
        """Records of a loaded household that are not in and have no reason: Gen1 has changed
        since (the next run will report the household), or they are unexplained."""
        keys = [k for (k,) in self.rows("SELECT DISTINCT key FROM h_class WHERE grp = 'look'")]
        changed = []
        for i in range(0, len(keys), 500):
            some = [self.units[k] for k in keys[i:i + 500] if k in self.units]
            before = {k: (f, v) for k, f, v in self.rows(
                "SELECT household_key, fingerprint, fingerprint_version FROM migration.household_progress "
                "WHERE household_key = ANY(%s)", ([u.key for u in some],))}
            for unit, data, error in source.read_units(self.conn, some):
                was, version = before.get(unit.key, (None, None))
                if error is not None or (was and version == source.FINGERPRINT_VERSION
                                         and source.changed_parts(was, source.fingerprint(data))):
                    changed.append(unit.key)
        self.cur.execute("UPDATE h_class SET grp = CASE WHEN key = ANY(%s) THEN 'not_added' ELSE 'unexplained' END "
                         "WHERE grp = 'look'", (changed,))

    # -- how the runs went --------------------------------------------------------------------

    def run_health(self):
        run = self.rows("SELECT run_id, status, extract(epoch FROM coalesce(finished_at, clock_timestamp()) - started_at), "
                        "counts FROM migration.run WHERE mode <> 'finalize' ORDER BY started_at DESC LIMIT 1")
        status = self.status or (run[0][1] if run else None)
        self.run_id = run[0][0] if run else None
        done = status in ("COMPLETED", "COMPLETED_WITH_FAILURES")
        self.add(RUNS, "Last run completed", int(done), 1, GREEN if done else RED, target="Yes", blocking=True)
        if run:
            seconds = int(run[0][2])
            self.add(RUNS, "Last run: seconds", seconds)
            loaded = self.one("SELECT coalesce(sum(cardinality(farmer_ids)), 0) FROM migration.household_progress "
                              "WHERE last_run_id = %s AND status = 'LOADED'", (self.run_id,))
            self.add(RUNS, "Last run: farmers loaded", int(loaded))
            self.add(RUNS, "Last run: farmers per minute", int(loaded * 60 / seconds) if seconds else None)
        for s, n in self.rows("SELECT status, count(*) FROM migration.run WHERE mode <> 'finalize' GROUP BY 1 ORDER BY 1"):
            if not (s == "RUNNING" and self.status):
                self.add(RUNS, "Runs by how they ended", n, split_by="Status", split_value=s)

        failed = self.one("SELECT count(*) FROM migration.household_progress WHERE status = 'FAILED'")
        self.zero(RUNS, "Households that failed to load", failed, blocking=True, record_type="household")
        for cls, n in self.rows("SELECT coalesce(error_class, '(unknown)'), count(*) FROM migration.household_progress "
                                "WHERE status = 'FAILED' GROUP BY 1 ORDER BY 2 DESC") or [("(none)", 0)]:
            self.add(RUNS, "Failed households by kind of error", n, failed, split_by="Error", split_value=cls)
        for age, n in self.rows("""
                SELECT CASE WHEN d < 1 THEN 'under 1 day' WHEN d < 7 THEN '1 to 7 days' ELSE 'over 7 days' END, count(*)
                  FROM (SELECT household_key, extract(epoch FROM clock_timestamp() - min(first_seen)) / 86400 AS d
                          FROM migration.issue WHERE severity = 'failed' AND status = 'OPEN' GROUP BY 1) x
                 GROUP BY 1 ORDER BY 1""") or [("(none)", 0)]:
            self.add(RUNS, "Failed households by age", n, failed, split_by="Open for", split_value=age)
        taken = self.one("SELECT count(*) FROM migration.household_progress WHERE status = 'FAILED' "
                         "AND error_class = 'UniqueViolation' AND error LIKE %s", ("%functional_record_id%",))
        self.zero(RUNS, "Households left out because a farmer's number is taken", taken, record_type="household")
        changed = self.one("SELECT count(*) FROM migration.household_progress WHERE status = 'CHANGED'")
        self.add(RUNS, "Households changed in Gen1 since they were migrated", changed, None,
                 AMBER if changed else GREEN, target="Reviewed", record_type="household")
        self.numbers("farmer")
        self.numbers("household")
        scores = dict(self.rows("SELECT q.compute_status, count(*) FROM g2p_completion_score_computation_queue q "
                                "JOIN migration.migrated_record m ON m.gen2_id = q.internal_record_id GROUP BY 1"))
        self.add(RUNS, "Completion scores done", scores.get("COMPLETED", 0), sum(scores.values()))
        self.add(RUNS, "Completion scores waiting", scores.get("PENDING", 0) + scores.get("PROCESSING", 0))
        self.zero(RUNS, "Completion scores failed", scores.get("FAILED", 0))

    def numbers(self, kind):
        """Farmer and household numbers: copied from Gen1, generated by Gen2, waiting or failed."""
        kinds = ("farmer",) if kind == "farmer" else ("household", "solo_household")
        got = dict(self.rows(f"""
            SELECT CASE
              WHEN p.legacy_number IS NOT NULL AND r.functional_record_id = p.legacy_number THEN 'copied'
              WHEN coalesce(r.functional_record_id, '') <> '' AND r.functional_record_id NOT LIKE 'TEMP-%%' THEN 'generated'
              WHEN EXISTS (SELECT 1 FROM g2p_functional_id_generation_queue q WHERE q.internal_record_id = r.internal_record_id
                            AND q.id_allocation_status = 'FAILED') THEN 'failed'
              WHEN EXISTS (SELECT 1 FROM g2p_functional_id_generation_queue q
                            WHERE q.internal_record_id = r.internal_record_id) THEN 'waiting'
              ELSE 'not queued' END, count(*)
              FROM migration.migrated_record m JOIN {self.tables[kind]} r ON r.internal_record_id = m.gen2_id
              LEFT JOIN h_person p ON m.kind = 'farmer' AND p.farmer_id = m.odoo_id
             WHERE m.kind = ANY(%s) GROUP BY 1""", (list(kinds),)))
        total = sum(got.values())
        name = kind.capitalize()
        if kind == "farmer":
            self.add(RUNS, f"{name} numbers copied from Gen1", got.get("copied", 0), total, record_type=kind)
        self.add(RUNS, f"{name} numbers generated by Gen2", got.get("generated", 0), total, record_type=kind)
        self.add(RUNS, f"{name} numbers waiting", got.get("waiting", 0), total, record_type=kind)
        self.zero(RUNS, f"{name} numbers not queued", got.get("not queued", 0), total, record_type=kind)
        self.zero(RUNS, f"{name} numbers failed", got.get("failed", 0), total, record_type=kind)

    # -- did the data arrive --------------------------------------------------------------------

    def quality(self):
        self.verified()
        self.fields()
        self.issues()
        self.structure()
        self.required()
        self.shared()
        for value, n in self.rows(f"""
                SELECT coalesce(p.state, '(none)') || ' -> ' || coalesce(r.record_status, '(none)'), count(*)
                  FROM migration.migrated_record m JOIN {self.tables['farmer']} r ON r.internal_record_id = m.gen2_id
                  JOIN h_person p ON p.farmer_id = m.odoo_id WHERE m.kind = 'farmer' GROUP BY 1 ORDER BY 1"""):
            self.add(QUALITY, "Gen1 status to Gen2 status", n, record_type="farmer", split_by="Gen1 -> Gen2",
                     split_value=value)
        for kind, table in self.tables.items():
            n = self.one(f"SELECT count(*) FROM {table} r WHERE {self.mine('r')} AND {self.edited(kind, 'r')}")
            self.add(QUALITY, "Edited in Gen2 since (not compared)", n, record_type=kind)

    def verified(self):
        """What verify.py found, if it ran over everything since the last load."""
        have = None
        if self.one("SELECT to_regclass('migration_report.snapshot') IS NOT NULL") and not self.status:
            have = self.rows("""
                SELECT s.snapshot_id FROM migration_report.snapshot s WHERE s.taken_by = 'verify'
                   AND s.taken_at > (SELECT max(coalesce(finished_at, started_at)) FROM migration.run WHERE mode <> 'finalize')
                 ORDER BY s.snapshot_id DESC LIMIT 1""")
        found = {} if not have else {(r[1], r[0]): r[2:] for r in self.rows(
            "SELECT metric, record_type, count, total, result FROM migration_report.measure WHERE snapshot_id = %s "
            "AND area = %s", (have[0][0], VERIFY))}
        values = found.get(("Values", "every migrated column holds the expected value"))
        if values:
            self.all_of(QUALITY, "Values matching Gen1 (verify)", values[0], values[1], blocking=True)
        else:
            self.add(QUALITY, "Values matching Gen1 (verify)", result=NOT_CHECKED, target="100%", blocking=True)
        codes = [v for (group, _), v in found.items() if group == "Master Data" and v[0] is not None and v[1] is not None]
        if codes:
            self.all_of(QUALITY, "Loaded codes and locations still in Master Data (verify)", sum(c[0] for c in codes),
                        sum(c[1] for c in codes))
        else:
            self.add(QUALITY, "Loaded codes and locations still in Master Data (verify)", result=NOT_CHECKED, target="100%")

    def fields(self):
        """For the fields that go to one column: filled in Gen1, filled in Gen2. Over the loaded
        records that neither side has changed since."""
        gen1 = {"farmer": ("res.partner", "res_partner"), "phone": ("g2p.phone.number", "g2p_phone_number"),
                "land": ("g2p.land.information", "g2p_land_information"),
                "crop": ("g2p.crop.information", "g2p_crop_information")}
        # the last two Gen2 fills itself, also where Gen1 has nothing
        skip = {"link_internal_record_id", "created_at", "last_approved_at", "country_code", "functional_record_id",
                "record_status"}
        with self.conn.cursor() as cur:
            cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = ANY(%s)", ([t for _, t in gen1.values()],))
            have = {(t, c): d for t, c, d in cur.fetchall()}
        from .inventory import _count_expr
        for kind, (model, table) in gen1.items():
            register = KINDS[kind]
            columns = getattr(self.models, f"G2PRegister{register}").__table__.columns
            pairs = []
            for (m, name), entry in F.SOURCE.items():
                mine = [t.split(".")[1] for t in entry["targets"] if t.startswith(register + ".")]
                if m != model or entry["status"] != F.MIGRATED or not mine or (table, name) not in have:
                    continue
                column = mine[0]
                if column in skip or column not in columns or len(F.sources_of(register, column)) > 1 \
                        or str(columns[column].type).upper() == "BOOLEAN":
                    continue
                pairs.append((name, column))
            if not pairs:
                continue
            totals = collections.Counter()
            rows = self.rows(f"""
                SELECT m.odoo_id, m.gen2_id FROM migration.migrated_record m
                  JOIN {self.tables[kind]} r ON r.internal_record_id = m.gen2_id AND NOT {self.edited(kind, 'r')}
                  JOIN migration.household_progress p ON p.household_key = m.household_key AND p.status = 'LOADED'
                 WHERE m.kind = %s""", (kind,))
            left = [_count_expr(name, have[(table, name)]) for name, _ in pairs]
            right = [f"count(nullif(nullif(nullif(nullif(btrim(x.\"{c}\"::text), ''), 'null'), '[]'), '{{}}'))" for _, c in pairs]
            for i in range(0, len(rows), 20000):
                some = rows[i:i + 20000]
                with self.conn.cursor() as cur:
                    cur.execute(f"SELECT {', '.join(left)} FROM {table} x WHERE x.id = ANY(%s)", ([r[0] for r in some],))
                    for (name, _), n in zip(pairs, cur.fetchone()):
                        totals[(name, 1)] += n
                got = self.rows(f"SELECT {', '.join(right)} FROM {self.tables[kind]} x WHERE x.internal_record_id = ANY(%s)",
                                ([r[1] for r in some],))[0]
                for (name, _), n in zip(pairs, got):
                    totals[(name, 2)] += n
            explained = collections.Counter()
            for field, n in self.rows("""
                    SELECT i.field, count(DISTINCT i.odoo_id) FROM migration.issue i
                      JOIN migration.household_progress p ON p.household_key = i.household_key AND p.status = 'LOADED'
                     WHERE i.severity = 'dropped' AND i.status = 'OPEN' AND i.entity = %s GROUP BY 1""", (_ENTITY[kind],)):
                explained[field] += n
            unexplained = 0
            for name, column in pairs:
                a, b = totals[(name, 1)], totals[(name, 2)]
                reasons = explained[name] + (explained[column] if column != name else 0)
                lost = max(0, a - b - reasons)
                unexplained += lost
                if a or b:
                    self.add(QUALITY, "Values that arrived", b, a, AMBER if lost else INFO, record_type=kind,
                             split_by="Field", split_value=f"{name} -> {column}")
            self.zero(QUALITY, "Values lost without a reason", unexplained, record_type=kind)

    def issues(self):
        """What the migration left out or moved, by its reason: the reasons are its own words, and
        those that hold a value are cut before it."""
        for entity, field, n in self.rows(
                "SELECT entity, field, count(*) FROM migration.issue WHERE status = 'OPEN' AND severity = 'dropped' "
                "AND reason LIKE 'not in Master Data%%' GROUP BY 1, 2 ORDER BY 3 DESC") or [("", "(none)", 0)]:
            self.add(QUALITY, "Left empty: not in Master Data", n, record_type=entity, split_by="Field", split_value=field)
        for entity, field, n in self.rows(
                "SELECT entity, field, count(*) FROM migration.issue WHERE status = 'OPEN' AND severity = 'dropped' "
                "AND reason = 'no registry code for this value' GROUP BY 1, 2 ORDER BY 3 DESC") or [("", "(none)", 0)]:
            self.add(QUALITY, "Left empty: no Gen2 code for the value", n, record_type=entity, split_by="Field", split_value=field)
        count = lambda where, *p: self.one(  # noqa: E731
            "SELECT count(*) FROM migration.issue WHERE status = 'OPEN' AND " + where, p or None)
        for metric, where in (
                ("Locations placed at a higher level", "field = 'location' AND severity = 'check'"),
                ("Locations left empty", "field IN ('location', 'land_kebele') AND severity = 'dropped'")):
            for entity in ("farmer", "household", *(("land",) if "empty" in metric else ())):
                self.add(QUALITY, metric, count(where + " AND entity = %s", entity), record_type=entity)
        for metric, where, params in (
                ("Phone numbers left out: not readable", "entity = 'phone' AND reason LIKE %s", ("not a readable%",)),
                ("Phone numbers left out: the farmer has it already", "entity = 'phone' AND reason LIKE %s", ("the farmer has%",)),
                ("Map shapes left out", "field = 'polygon_data' AND severity = 'dropped'", ()),
                ("Crops left out: the farmer has no land", "entity = 'crop' AND severity = 'skipped'", ()),
                (f"Lands over {LARGE_PARCEL_HA} ha, kept as they are", "field = 'total_land_area' AND severity = 'check'", ())):
            self.add(QUALITY, metric, count(where, *params))

    def structure(self):
        from . import verification as V
        checks = V.Checks()
        V.structure_checks(self.one, self.models, checks, self.mine)
        for c in checks.rows:
            self.zero(QUALITY, RULES[c["check"]], c["found"], blocking=True)

    def required(self):
        """Gen2's required fields (its own form settings) that are empty on migrated records."""
        register_of = dict(self.rows("SELECT register_id, register_mnemonic FROM g2p_register_definitions"))
        kind_of = {r: k for k, r in KINDS.items()}
        seen = set()
        for register_id, column in self.rows("""
                SELECT DISTINCT CASE WHEN w->>'widget-data-path' LIKE '%%.%%' THEN split_part(w->>'widget-data-path', '.', 1)
                            ELSE s.section_register_id END, regexp_replace(w->>'widget-data-path', '^.*[.]', '')
                  FROM g2p_register_sections s, jsonb_path_query(s.section_ui_schema::jsonb, 'strict $.**') w
                 WHERE jsonb_typeof(w) = 'object' AND w->>'widget-required' = 'true' AND w ? 'widget-data-path'"""):
            register = register_of.get(register_id)
            if register not in kind_of or (register, column) in seen:
                continue
            if column not in getattr(self.models, f"G2PRegister{register}").__table__.columns:
                continue
            seen.add((register, column))
            empty, total = self.rows(f"SELECT count(*) FILTER (WHERE nullif(btrim(\"{column}\"::text), '') IS NULL), count(*) "
                                     f"FROM {self.tables[kind_of[register]]} r WHERE {self.mine('r')}")[0]
            self.add(QUALITY, "Required by Gen2's forms, and empty", empty, total, record_type=kind_of[register],
                     split_by="Field", split_value=column)
        if not seen:
            self.add(QUALITY, "Required by Gen2's forms, and empty", 0, split_by="Field", split_value="(none required)")

    def shared(self):
        t = self.tables["farmer"]
        fayda = "nullif(replace({}.foundational_id, ' ', ''), '')"  # the registry's own comparison
        a, b = fayda.format("a"), fayda.format("b")
        live = "record_status <> 'ARCHIVED'"
        with_other = self.one(f"""
            SELECT coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM {t} a WHERE {self.mine('a')} AND a.{live}
               AND {a} IS NOT NULL GROUP BY {a} HAVING count(*) > 1) x""")
        self.zero(QUALITY, "Farmers sharing a Fayda ID with another migrated farmer", int(with_other), record_type="farmer")
        in_gen2 = self.one(f"""
            SELECT count(*) FROM {t} a WHERE {self.mine('a')} AND a.{live} AND {a} IN
               (SELECT {b} FROM {t} b WHERE NOT {self.mine('b')} AND b.{live} AND {b} IS NOT NULL)""")
        self.zero(QUALITY, "Farmers sharing a Fayda ID with a farmer already in Gen2", in_gen2, record_type="farmer")
        for column, name in (("rid", "an RID"), ("odk_farmer_id", "an ODK farmer ID")):
            n = self.one(f"""
                SELECT coalesce(sum(n), 0) FROM (SELECT count(*) AS n FROM {t} a WHERE {self.mine('a')}
                   AND coalesce({column}, '') <> '' GROUP BY {column} HAVING count(*) > 1) x""")
            self.add(QUALITY, f"Farmers sharing {name} with another migrated farmer", int(n), record_type="farmer")

    # -- can every record be traced -------------------------------------------------------------

    def ids(self):
        for kind, table in self.tables.items():
            # what the migration would have made of Gen1's records, and is in Gen2
            n, all_ = self.rows(f"""
                SELECT count(m.gen2_id), count(*) FROM (SELECT gen2_id FROM h_gen1 WHERE kind = %s
                        UNION ALL SELECT gen2_id FROM h_made WHERE kind = %s) g
                  JOIN {table} r ON r.internal_record_id = g.gen2_id
                  LEFT JOIN migration.migrated_record m ON m.gen2_id = g.gen2_id""", (kind, kind))[0]
            self.all_of(IDS, "Migrated records with both IDs saved", n, all_, blocking=True, record_type=kind)
        t = self.tables["farmer"]
        base = (f"FROM migration.migrated_record m JOIN h_person p ON p.farmer_id = m.odoo_id JOIN {t} r "
                "ON r.internal_record_id = m.gen2_id JOIN migration.household_progress h ON h.household_key = m.household_key "
                f"WHERE m.kind = 'farmer' AND h.status = 'LOADED' AND NOT {self.edited('farmer', 'r')}")
        for metric, gen1, same_as, blocking in (
                ("Gen1 Farmer IDs that arrived unchanged", "p.legacy_number", "= r.functional_record_id", True),
                # written with or without spaces
                ("Fayda IDs (UID or FAN) that arrived", "coalesce(p.uid, p.fan)", None, False),
                ("RIDs that arrived", "p.rid", "= r.rid", False),
                ("ODK farmer IDs that arrived", "p.odk", "= r.odk_farmer_id", False)):
            same = f"{gen1} {same_as}" if same_as else "replace(r.foundational_id, ' ', '') IN (p.uid, p.fan)"
            same, all_ = self.rows(f"SELECT count(*) FILTER (WHERE {same}), count({gen1}) {base}")[0]
            self.all_of(IDS, metric, same, all_, blocking=blocking, record_type="farmer")
        lost = self.one(f"SELECT count(*) FILTER (WHERE p.uid IS NOT NULL AND p.fan IS NOT NULL) {base}")
        self.add(IDS, "FANs not carried: the farmer has a UID too", lost, record_type="farmer")
        same, all_ = self.rows(f"""
            SELECT count(*) FILTER (WHERE l.land_id = r.land_id), count(*) FROM migration.migrated_record m
              JOIN h_land l ON l.odoo_id = m.odoo_id JOIN {self.tables['land']} r ON r.internal_record_id = m.gen2_id
              JOIN migration.household_progress h ON h.household_key = m.household_key
             WHERE m.kind = 'land' AND h.status = 'LOADED' AND NOT {self.edited('land', 'r')}""")[0]
        self.all_of(IDS, "Land IDs that arrived", same, all_, record_type="land")


def verify_said(engine, run_id):
    """What verify.py concluded, if it ran over everything since the last load: (failed checks, checks), else None."""
    with engine.connect() as conn:
        row = conn.exec_driver_sql("""
            SELECT count(*) FILTER (WHERE m.result = 'RED'), count(*) FROM migration_report.measure m
             WHERE m.snapshot_id = (SELECT max(snapshot_id) FROM migration_report.snapshot WHERE taken_by = 'verify'
               AND taken_at > (SELECT max(coalesce(finished_at, started_at)) FROM migration.run WHERE mode <> 'finalize'))""").first()
    return tuple(row) if row and row[1] else None


def take(engine, source_dsn, models, log, taken_by, status=None) -> dict:
    """Measure, store and return: {"measures", "overall", "run_id", "history"}."""
    ensure(engine)
    conn = psycopg2.connect(source_dsn)
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    raw = engine.raw_connection()
    try:
        raw.rollback()
        raw.cursor().execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        health = Health(raw, conn, models, log, status)
        measures = health.measure()
        run_id = health.run_id
    finally:
        with contextlib.suppress(Exception):
            raw.rollback()  # only temporary tables were written
        raw.close()
        conn.close()
    overall = worst(measures)
    save(engine, taken_by, run_id, measures, overall)
    return {"measures": measures, "overall": overall, "run_id": run_id, "history": history(engine),
            "verify": None if status else verify_said(engine, run_id)}
