#!/usr/bin/env python3
"""Bring the farmer profile's (Gen1) record history into the Farmer registry (Gen2).

Runs after the database migration (it reads migration.migrated_record). Gen1 and its
audit database are only read.

Two parts:

1. Version 1 in Gen2. Every migrated record gets one row in its register's history
   table (g2p_register_history_farmers, _lands, ...): a copy of the record as the
   migration wrote it, approved by whoever the record says last approved it. It is
   written the way the registry writes history for an approved intake form, so the
   record's history in the Staff Portal starts at the migration. The row is
   registered in migration.migrated_record (kind history_<kind>, gen2_id = its
   history_record_id): the migration's health check and delta then know it is the
   migration's, not an edit made in Gen2.

2. The Gen1 history, archived. Every Gen1 change (audit database: g2p_change_log and
   g2p_change_log_line, field by field, old and new value) and every Gen1 update
   request (res_partner_change_request) is copied into migration.gen1_change_log,
   migration.gen1_change_log_line and migration.gen1_change_request, with the Gen2
   record it belongs to. Nothing of Gen1's history is lost; it is not shown in the
   Staff Portal.

    python migrate_history.py plan               what would be written; writes nothing
    python migrate_history.py apply              write both parts (safe to run again)
    python migrate_history.py apply --only version1|audit|requests
    python migrate_history.py validate           every migrated record and every Gen1 change against Gen2
    python migrate_history.py evidence FR-...    one farmer's history, Gen1 and Gen2

Settings (environment or .env next to this script, as in the database migration):
  SOURCE_DSN   Gen1 farmer profile (Odoo) database, libpq form: users and update requests
  AUDIT_DSN    Gen1 audit database (log_db.db.* / G2P_CHANGE_LOG_DB_*), libpq form
  TARGET_DSN   Gen2 registry database (postgresql+psycopg2://... or libpq form)
  HISTORY_SOURCE  change_request_source of the version 1 rows (default PARTNER)
  LOG_DIR      reports (default ./logs);  BATCH  rows per transaction (default 1000)

Exit code: 0 = clean, 1 = something to resolve or a check failed, 2 = setup error.
"""
import argparse
import csv
import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

HERE = os.path.dirname(os.path.abspath(__file__))
# The database migration's namespace (farmer_profile), so ids stay in one family.
NAMESPACE = uuid.UUID("5b0c7f0e-6f43-4c2e-9a39-6d0f0a7c2f11")

# migrated_record kind -> register mnemonic in Gen2
RECORD_KINDS = {"farmer": "Farmer", "household": "Household", "solo_household": "Household",
                "member": "HouseholdMember", "solo_member": "HouseholdMember", "phone": "FarmerPhone",
                "land": "Land", "crop": "Crop"}
TABLES = {"Farmer": "g2p_register_farmers", "Household": "g2p_register_households",
          "HouseholdMember": "g2p_register_household_members", "FarmerPhone": "g2p_register_farmer_phones",
          "Land": "g2p_register_lands", "Crop": "g2p_register_crops"}
# Gen1 audit model -> migrated_record kinds it can be (tried in order)
GEN1_MODELS = {"res.partner": ("farmer", "household"), "g2p.group.membership": ("member",),
               "g2p.phone.number": ("phone",), "g2p.land.information": ("land",),
               "g2p.crop.information": ("crop",)}
HISTORY_COLUMNS = {"history_record_id", "tab_id", "section_id", "change_request_id", "submission_id",
                   "change_request_source", "is_primary_section", "subject_internal_record_id",
                   "approved_by", "approved_at"}
SOURCES = {"PARTNER", "INTAKE_FORM", "STAFF_PORTAL", "BENEFICIARY_PORTAL", "AGENT_PORTAL"}
SCHEMA_FILE = os.path.join(HERE, "history-schema.sql")


class SetupError(Exception):
    pass


# -- settings and connections --------------------------------------------------------------

def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def setting(name, default=None):
    value = os.environ.get(name, default)
    if value in (None, ""):
        raise SetupError(f"{name} is not set (environment or .env)")
    return value


def connect(name):
    dsn = setting(name)
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]
    try:
        return psycopg2.connect(dsn)
    except psycopg2.Error as e:
        raise SetupError(f"cannot connect with {name}: {str(e).strip().splitlines()[0]}")


def rows(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def one(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
        return r[0] if r else None


def table_exists(conn, schema, table):
    return bool(one(conn, "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                    (schema, table)))


def history_id(kind, odoo_id):
    return str(uuid.uuid5(NAMESPACE, f"farmer-profile/history/{kind}/{odoo_id}"))


def run_dir(command):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(os.environ.get("LOG_DIR", os.path.join(HERE, "logs")), f"{stamp}-{command}")
    os.makedirs(path, exist_ok=True)
    return stamp, path


def write_csv(path, header, data):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)


# -- Gen2: where each kind's version 1 goes ----------------------------------------------------

class Register:
    """One register's tables, the section its version 1 is written under, and its subject."""

    def __init__(self, dst, mnemonic, defs):
        self.mnemonic = mnemonic
        self.register_id = defs[mnemonic]["register_id"]
        self.live = TABLES[mnemonic]
        self.history = self.live.replace("g2p_register_", "g2p_register_history_", 1)
        for t in (self.live, self.history):
            if not table_exists(dst, "public", t):
                raise SetupError(f"{t} is not in the Gen2 database")
        cols = {t: {r["column_name"]: r["data_type"] for r in rows(
            dst, "SELECT column_name, data_type FROM information_schema.columns "
                 "WHERE table_schema = 'public' AND table_name = %s", (t,))} for t in (self.live, self.history)}
        missing = HISTORY_COLUMNS - set(cols[self.history])
        if missing:
            raise SetupError(f"{self.history} has no {', '.join(sorted(missing))}: not a register history table")
        self.columns = sorted((set(cols[self.live]) & set(cols[self.history])) - HISTORY_COLUMNS)
        self.json_columns = {c for c in self.columns if cols[self.live][c] == "json"}
        self.approved = ("live.last_approved_by", "live.last_approved_at") \
            if {"last_approved_by", "last_approved_at"} <= set(cols[self.live]) else ("live.created_by", "live.created_at")
        # The section: one that holds this register's records and is on a tab; the
        # register's own first, then by tab and section order (as the Staff Portal shows them).
        found = rows(dst, """
            SELECT s.section_id, s.register_id, ts.tab_id, (s.section_register_id = s.register_id) AS is_primary
              FROM g2p_register_sections s
              JOIN g2p_register_ui_tab_sections ts ON ts.section_id = s.section_id
              JOIN g2p_register_ui_tabs t ON t.tab_id = ts.tab_id
             WHERE s.section_register_id = %s
             ORDER BY (s.register_id = %s) DESC, t.tab_order, ts.section_order, s.section_id
             LIMIT 1""", (self.register_id, self.register_id))
        if not found:
            raise SetupError(f"no section on a tab holds {mnemonic} records: cannot place its history")
        self.section_id, self.tab_id = found[0]["section_id"], found[0]["tab_id"]
        self.is_primary = found[0]["is_primary"]
        # The subject: the record of the register the section is in (the farmer for a
        # land, the household for a member), up the link_internal_record_id chain.
        by_id = {d["register_id"]: m for m, d in defs.items()}
        target, current = found[0]["register_id"], self.register_id
        self.subject_register = by_id.get(target, target)
        expr, depth = "live.internal_record_id", 0
        while current != target:
            if depth == 0:
                expr = "live.link_internal_record_id"
            else:
                table = TABLES.get(by_id.get(current))
                if not table:
                    raise SetupError(f"cannot follow {mnemonic} up to {self.subject_register}")
                expr = f"(SELECT p{depth}.link_internal_record_id FROM {table} p{depth} WHERE p{depth}.internal_record_id = {expr})"
            current = defs[by_id[current]]["master_register_id"] if current in by_id else None
            depth += 1
            if current is None or depth > 6:
                raise SetupError(f"{mnemonic} is not under {self.subject_register}")
        self.subject = expr

    def compare(self, alias):
        return ", ".join(f"{alias}.{c}::text" if c in self.json_columns else f"{alias}.{c}" for c in self.columns)


def registers(dst):
    for t in ("g2p_register_definitions", "g2p_register_sections", "g2p_register_ui_tabs", "g2p_register_ui_tab_sections"):
        if not table_exists(dst, "public", t):
            raise SetupError(f"{t} is not in the Gen2 database: is TARGET_DSN the registry?")
    defs = {r["register_mnemonic"]: r for r in rows(
        dst, "SELECT register_id, register_mnemonic, master_register_id FROM g2p_register_definitions")}
    for m in TABLES:
        if m not in defs:
            raise SetupError(f"register {m} is not defined in the Gen2 database")
    return {m: Register(dst, m, defs) for m in TABLES}


def require_migration(dst):
    if not table_exists(dst, "migration", "migrated_record"):
        raise SetupError("migration.migrated_record is not in the Gen2 database: run the database migration first")


def history_kinds_allowed(dst):
    """migrated_record's kind check accepts history_<kind> (history-schema.sql has been run)."""
    d = one(dst, "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                 "WHERE conrelid = 'migration.migrated_record'::regclass AND conname = 'migrated_record_kind_check'")
    return d is None or all(f"history_{k}" in d for k in RECORD_KINDS)


def record_status(dst, reg, kinds):
    """(kind, odoo_id, gen2_id, household_key, status) of every migrated record of these kinds.
    status: to_write, done (version 1 is in), has_gen2_history (Gen2 already has history for
    it that is not the migration's), no_gen2_record (not in the register table)."""
    return rows(dst, f"""
        SELECT m.kind, m.odoo_id, m.gen2_id, m.household_key,
               CASE WHEN live.internal_record_id IS NULL THEN 'no_gen2_record'
                    WHEN EXISTS (SELECT 1 FROM migration.migrated_record h
                                   JOIN {reg.history} e ON e.history_record_id = h.gen2_id
                                  WHERE h.kind = 'history_' || m.kind AND h.odoo_id = m.odoo_id) THEN 'done'
                    WHEN EXISTS (SELECT 1 FROM {reg.history} e WHERE e.internal_record_id = m.gen2_id) THEN 'has_gen2_history'
                    ELSE 'to_write' END AS status
          FROM migration.migrated_record m
          LEFT JOIN {reg.live} live ON live.internal_record_id = m.gen2_id
         WHERE m.kind = ANY(%s)
         ORDER BY m.kind, m.odoo_id""", (list(kinds),))


def kinds_of(mnemonic):
    return [k for k, m in RECORD_KINDS.items() if m == mnemonic]


# -- Gen1: users, changes and update requests --------------------------------------------------

def gen1_records(dst):
    """(kind, Odoo id) -> Gen2 id, for the kinds a Gen1 change can be about."""
    wanted = sorted({k for ks in GEN1_MODELS.values() for k in ks})
    return {(r["kind"], r["odoo_id"]): r["gen2_id"] for r in rows(
        dst, "SELECT kind, odoo_id, gen2_id FROM migration.migrated_record WHERE kind = ANY(%s)", (wanted,))}


def resolve(records, model, res_id):
    """(kind, gen2_id, status) of a Gen1 change about (model, res_id)."""
    kinds = GEN1_MODELS.get(model)
    if not kinds:
        return None, None, "other_model"
    for kind in kinds:
        gen2 = records.get((kind, res_id))
        if gen2:
            return kind, gen2, "linked"
    return None, None, "not_migrated"


def users(src):
    return {r["id"]: r["login"] for r in rows(src, "SELECT id, login FROM res_users")}


def stream(conn, sql, size):
    with conn.cursor(name=f"stream_{uuid.uuid4().hex[:8]}", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.itersize = size
        cur.execute(sql)
        batch = []
        for r in cur:
            batch.append(r)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch


LOG_SQL = ("SELECT id, name, model_id, model_name, model_model, res_id, user_id, method, log_type, create_date "
           "FROM g2p_change_log ORDER BY id")
LINE_SQL = ("SELECT id, log_id, field_id, field_name, field_description, old_value, new_value, "
            "old_value_text, new_value_text, create_date FROM g2p_change_log_line ORDER BY id")
REQUEST_SQL = ("SELECT id, partner_id, name, state, request_source, requested_by, validator, new_values::text AS new_values, "
               "update_message, replace_related_records, validated_on, create_date FROM res_partner_change_request ORDER BY id")


def require_audit(audit):
    for t in ("g2p_change_log", "g2p_change_log_line"):
        if not table_exists(audit, "public", t):
            raise SetupError(f"{t} is not in the audit database: is AUDIT_DSN the Gen1 audit database?")


# -- plan -------------------------------------------------------------------------------------

def cmd_plan(args):
    dst = connect("TARGET_DSN")
    require_migration(dst)
    regs = registers(dst)
    stamp, out = run_dir("plan")
    summary, attention = [], []
    print("Version 1 in Gen2 (one history row per migrated record):")
    for m, reg in regs.items():
        counts = Counter()
        for r in record_status(dst, reg, kinds_of(m)):
            counts[r["status"]] += 1
            if r["status"] in ("has_gen2_history", "no_gen2_record"):
                attention.append((r["kind"], r["odoo_id"], r["gen2_id"], r["status"]))
        print(f"  {m:16} {reg.history}: tab {reg.tab_id}, section {reg.section_id}, subject {reg.subject_register}")
        print("                   " + ", ".join(f"{s} {n}" for s, n in sorted(counts.items())) if counts else
              "                   no migrated records")
        summary += [("version1", m, s, n) for s, n in sorted(counts.items())]
    if not history_kinds_allowed(dst):
        print("  note: apply first runs history-schema.sql (migrated_record must accept the history_<kind> kinds)")

    if os.environ.get("AUDIT_DSN"):
        audit = connect("AUDIT_DSN")
        require_audit(audit)
        records = gen1_records(dst)
        counts = Counter()
        for batch in stream(audit, LOG_SQL, int(os.environ.get("BATCH", "1000"))):
            for r in batch:
                counts[(r["model_model"] or "", resolve(records, r["model_model"], r["res_id"])[2])] += 1
        lines = one(audit, "SELECT count(*) FROM g2p_change_log_line")
        print(f"Gen1 changes (audit database): {sum(counts.values())} changes, {lines} field lines")
        for (model, status), n in sorted(counts.items()):
            print(f"  {model or '(none)':28} {status:14} {n}")
        summary += [("gen1_change_log", model, status, n) for (model, status), n in sorted(counts.items())]
        summary.append(("gen1_change_log_line", "", "all", lines))
    else:
        print("Gen1 changes: AUDIT_DSN is not set, not counted")

    if os.environ.get("SOURCE_DSN"):
        src = connect("SOURCE_DSN")
        if table_exists(src, "public", "res_partner_change_request"):
            records = gen1_records(dst)
            counts = Counter()
            for r in rows(src, "SELECT partner_id, state FROM res_partner_change_request"):
                counts[(r["state"], resolve(records, "res.partner", r["partner_id"])[2])] += 1
            print(f"Gen1 update requests: {sum(counts.values())}")
            for (state, status), n in sorted(counts.items()):
                print(f"  {state:28} {status:14} {n}")
            summary += [("gen1_change_request", state, status, n) for (state, status), n in sorted(counts.items())]
        else:
            print("Gen1 update requests: res_partner_change_request is not in Gen1")
    else:
        print("Gen1 update requests: SOURCE_DSN is not set, not counted")

    write_csv(os.path.join(out, "summary.csv"), ["part", "what", "status", "count"], summary)
    write_csv(os.path.join(out, "to-resolve.csv"), ["kind", "odoo_id", "gen2_id", "status"], attention)
    print(f"Reports: {out}")
    if attention:
        print(f"{len(attention)} records need a decision (to-resolve.csv): "
              "has_gen2_history = edited in Gen2 before its history came; no_gen2_record = not in its register")
        return 1
    return 0


# -- apply ------------------------------------------------------------------------------------

def ensure_schema(dst):
    with open(SCHEMA_FILE) as f:
        sql = f.read()
    try:
        with dst.cursor() as cur:
            cur.execute(sql)
        dst.commit()
    except psycopg2.Error as e:
        dst.rollback()
        raise SetupError(f"cannot run history-schema.sql ({str(e).strip().splitlines()[0]}): "
                         "a DBA runs it once, then apply again")


def apply_version1(dst, regs, run_id, size):
    source = os.environ.get("HISTORY_SOURCE", "PARTNER")
    if source not in SOURCES:
        raise SetupError(f"HISTORY_SOURCE {source} is not one of {', '.join(sorted(SOURCES))}")
    written, skipped = Counter(), Counter()
    for m, reg in regs.items():
        todo = []
        for r in record_status(dst, reg, kinds_of(m)):
            if r["status"] == "to_write":
                todo.append((history_id(r["kind"], r["odoo_id"]), r["gen2_id"], r["kind"], r["odoo_id"], r["household_key"]))
            elif r["status"] != "done":
                skipped[(m, r["status"])] += 1
        cols = ", ".join(reg.columns)
        live_cols = ", ".join(f"live.{c}" for c in reg.columns)
        for i in range(0, len(todo), size):
            with dst.cursor() as cur:
                cur.execute("CREATE TEMP TABLE IF NOT EXISTS hist_v1 (history_record_id text, gen2_id text, kind text, "
                            "odoo_id bigint, household_key text) ON COMMIT DELETE ROWS")
                psycopg2.extras.execute_values(cur, "INSERT INTO hist_v1 VALUES %s", todo[i:i + size])
                cur.execute(f"""
                    INSERT INTO {reg.history} (history_record_id, tab_id, section_id, change_request_id, submission_id,
                                               change_request_source, is_primary_section, subject_internal_record_id,
                                               approved_by, approved_at, {cols})
                    SELECT t.history_record_id, %s, %s, NULL, NULL, %s, %s, {reg.subject},
                           {reg.approved[0]}, {reg.approved[1]}, {live_cols}
                      FROM hist_v1 t JOIN {reg.live} live ON live.internal_record_id = t.gen2_id
                     WHERE NOT EXISTS (SELECT 1 FROM {reg.history} e WHERE e.internal_record_id = t.gen2_id)
                    ON CONFLICT (history_record_id) DO NOTHING
                    RETURNING history_record_id""", (reg.tab_id, reg.section_id, source, reg.is_primary))
                done = [r[0] for r in cur.fetchall()]
                cur.execute("""INSERT INTO migration.migrated_record (kind, odoo_id, gen2_id, household_key)
                               SELECT 'history_' || t.kind, t.odoo_id, t.history_record_id, t.household_key
                                 FROM hist_v1 t WHERE t.history_record_id = ANY(%s)
                               ON CONFLICT DO NOTHING""", (done,))
            dst.commit()
            written[m] += len(done)
        print(f"  {m:16} version 1 written: {written[m]}")
    for (m, status), n in sorted(skipped.items()):
        print(f"  {m:16} not written, {status}: {n}")
    return written, skipped


def apply_audit(dst, audit, src, run_id, size):
    require_audit(audit)
    records = gen1_records(dst)
    logins = users(src) if src else {}
    counts = Counter()
    for batch in stream(audit, LOG_SQL, size):
        values = []
        for r in batch:
            kind, gen2, status = resolve(records, r["model_model"], r["res_id"])
            counts[status] += 1
            values.append((r["id"], r["model_model"], r["model_name"], r["res_id"], r["name"], r["method"], r["log_type"],
                           r["user_id"], logins.get(r["user_id"]), r["create_date"], kind, gen2, status, run_id))
        with dst.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO migration.gen1_change_log (gen1_log_id, model, model_name, res_id, name, method, log_type,
                       gen1_user_id, user_login, changed_at, kind, gen2_id, status, run_id) VALUES %s
                ON CONFLICT (gen1_log_id) DO UPDATE SET kind = EXCLUDED.kind, gen2_id = EXCLUDED.gen2_id,
                       status = EXCLUDED.status, user_login = EXCLUDED.user_login, run_id = EXCLUDED.run_id
                 WHERE (gen1_change_log.kind, gen1_change_log.gen2_id, gen1_change_log.status, gen1_change_log.user_login)
                       IS DISTINCT FROM (EXCLUDED.kind, EXCLUDED.gen2_id, EXCLUDED.status, EXCLUDED.user_login)""", values)
        dst.commit()
    lines = 0
    for batch in stream(audit, LINE_SQL, size):
        with dst.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO migration.gen1_change_log_line (gen1_line_id, gen1_log_id, field_id, field_name,
                       field_description, old_value, new_value, old_value_text, new_value_text, changed_at, run_id)
                VALUES %s ON CONFLICT (gen1_line_id) DO NOTHING""",
                [(r["id"], r["log_id"], r["field_id"], r["field_name"], r["field_description"], r["old_value"],
                  r["new_value"], r["old_value_text"], r["new_value_text"], r["create_date"], run_id) for r in batch])
        dst.commit()
        lines += len(batch)
    print(f"  Gen1 changes archived: {sum(counts.values())} ("
          + ", ".join(f"{s} {n}" for s, n in sorted(counts.items())) + f"), {lines} field lines")
    return counts


def apply_requests(dst, src, run_id, size):
    if not table_exists(src, "public", "res_partner_change_request"):
        print("  Gen1 update requests: res_partner_change_request is not in Gen1, nothing to archive")
        return Counter()
    records = gen1_records(dst)
    logins = users(src)
    counts = Counter()
    for batch in stream(src, REQUEST_SQL, size):
        values = []
        for r in batch:
            kind, gen2, status = resolve(records, "res.partner", r["partner_id"])
            counts[status] += 1
            values.append((r["id"], r["partner_id"], r["name"], r["state"], r["request_source"],
                           logins.get(r["requested_by"]), logins.get(r["validator"]), r["new_values"],
                           r["update_message"], r["replace_related_records"], r["validated_on"], r["create_date"],
                           kind, gen2, status, run_id))
        with dst.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO migration.gen1_change_request (gen1_request_id, partner_id, name, state, request_source,
                       requested_by, validator, new_values, update_message, replace_related_records, validated_on,
                       requested_at, kind, gen2_id, status, run_id) VALUES %s
                ON CONFLICT (gen1_request_id) DO UPDATE SET state = EXCLUDED.state, validator = EXCLUDED.validator,
                       validated_on = EXCLUDED.validated_on, kind = EXCLUDED.kind, gen2_id = EXCLUDED.gen2_id,
                       status = EXCLUDED.status, run_id = EXCLUDED.run_id
                 WHERE (gen1_change_request.state, gen1_change_request.validator, gen1_change_request.validated_on,
                        gen1_change_request.gen2_id, gen1_change_request.status)
                       IS DISTINCT FROM (EXCLUDED.state, EXCLUDED.validator, EXCLUDED.validated_on,
                        EXCLUDED.gen2_id, EXCLUDED.status)""",
                values, template="(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)")
        dst.commit()
    print(f"  Gen1 update requests archived: {sum(counts.values())} ("
          + ", ".join(f"{s} {n}" for s, n in sorted(counts.items())) + ")")
    return counts


def cmd_apply(args):
    dst = connect("TARGET_DSN")
    require_migration(dst)
    regs = registers(dst)
    size = int(os.environ.get("BATCH", "1000"))
    parts = [args.only] if args.only else ["version1", "audit", "requests"]
    # Every connection a part needs, before anything is written
    src = connect("SOURCE_DSN") if ("requests" in parts or "audit" in parts) else None
    audit = connect("AUDIT_DSN") if "audit" in parts else None
    if audit:
        require_audit(audit)
    stamp, out = run_dir("apply")
    run_id = f"history-{stamp}"
    ensure_schema(dst)
    if not history_kinds_allowed(dst):
        raise SetupError("migration.migrated_record does not accept the history_<kind> kinds: run history-schema.sql")
    print(f"Run {run_id}")
    skipped = Counter()
    if "version1" in parts:
        _, skipped = apply_version1(dst, regs, run_id, size)
    if "audit" in parts:
        apply_audit(dst, audit, src, run_id, size)
    if "requests" in parts:
        apply_requests(dst, src, run_id, size)
    write_csv(os.path.join(out, "skipped.csv"), ["register", "status", "count"],
              [(m, s, n) for (m, s), n in sorted(skipped.items())])
    print(f"Reports: {out}. Next: python migrate_history.py validate")
    return 1 if skipped else 0


# -- validate ---------------------------------------------------------------------------------

def cmd_validate(args):
    dst = connect("TARGET_DSN")
    require_migration(dst)
    regs = registers(dst)
    stamp, out = run_dir("validate")
    problems = []
    for m, reg in regs.items():
        for r in record_status(dst, reg, kinds_of(m)):
            if r["status"] != "done":
                problems.append(("version1", m, r["kind"], r["odoo_id"], r["gen2_id"], r["status"]))
        # The row registered in migrated_record is in the history table, for its record.
        for r in rows(dst, f"""
                SELECT h.kind, h.odoo_id, h.gen2_id FROM migration.migrated_record h
                  JOIN migration.migrated_record m ON 'history_' || m.kind = h.kind AND m.odoo_id = h.odoo_id
                 WHERE m.kind = ANY(%s) AND NOT EXISTS (
                       SELECT 1 FROM {reg.history} e WHERE e.history_record_id = h.gen2_id AND e.internal_record_id = m.gen2_id)""",
                      (kinds_of(m),)):
            problems.append(("version1", m, r["kind"], r["odoo_id"], r["gen2_id"], "history_row_missing"))
        # Version 1 is the record: same values as the register, where it has not been approved again since.
        for r in rows(dst, f"""
                SELECT h.kind, h.odoo_id, h.gen2_id FROM migration.migrated_record h
                  JOIN {reg.history} e ON e.history_record_id = h.gen2_id
                  JOIN {reg.live} live ON live.internal_record_id = e.internal_record_id
                 WHERE h.kind = ANY(%s) AND e.approved_at = {reg.approved[1]}
                   AND ROW({reg.compare('e')}) IS DISTINCT FROM ROW({reg.compare('live')})""",
                      ([f"history_{k}" for k in kinds_of(m)],)):
            problems.append(("version1", m, r["kind"], r["odoo_id"], r["gen2_id"], "differs_from_record"))
    counts = {"version1": sum(one(dst, f"SELECT count(*) FROM migration.migrated_record WHERE kind = ANY(%s)",
                                  ([f"history_{k}" for k in kinds_of(m)],)) for m in regs)}

    archived = table_exists(dst, "migration", "gen1_change_log")
    if os.environ.get("AUDIT_DSN"):
        audit = connect("AUDIT_DSN")
        require_audit(audit)
        for gen1, mine, label in (("g2p_change_log", "gen1_change_log", "changes"),
                                  ("g2p_change_log_line", "gen1_change_log_line", "field lines")):
            a = one(audit, f"SELECT count(*) FROM {gen1}")
            b = one(dst, f"SELECT count(*) FROM migration.{mine}") if archived else 0
            counts[mine] = b
            if a != b:
                problems.append(("archive", mine, "", "", "", f"Gen1 has {a} {label}, the archive {b}"))
    if os.environ.get("SOURCE_DSN"):
        src = connect("SOURCE_DSN")
        if table_exists(src, "public", "res_partner_change_request"):
            a = one(src, "SELECT count(*) FROM res_partner_change_request")
            b = one(dst, "SELECT count(*) FROM migration.gen1_change_request") \
                if table_exists(dst, "migration", "gen1_change_request") else 0
            counts["gen1_change_request"] = b
            if a != b:
                problems.append(("archive", "gen1_change_request", "", "", "", f"Gen1 has {a} update requests, the archive {b}"))
    if archived:
        # A linked change points at a record Gen2 has.
        for r in rows(dst, """SELECT gen1_log_id, kind, gen2_id FROM migration.gen1_change_log c
                               WHERE status = 'linked' AND gen2_id NOT IN (SELECT gen2_id FROM migration.migrated_record)"""):
            problems.append(("archive", "gen1_change_log", r["kind"], r["gen1_log_id"], r["gen2_id"], "linked_to_unknown_record"))

    write_csv(os.path.join(out, "validate.csv"), ["part", "what", "kind", "id", "gen2_id", "problem"], problems)
    print("Validated: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    by = Counter((p[0], p[1], p[5] if p[0] == "version1" else "count") for p in problems)
    for (part, what, problem), n in sorted(by.items()):
        print(f"  {part:9} {what:22} {problem}: {n}")
    print(f"Report: {os.path.join(out, 'validate.csv')}")
    if problems:
        print(f"Validation FAILED: {len(problems)} problems")
        return 1
    print("Validation passed: every migrated record has its version 1, and every Gen1 change is archived.")
    return 0


# -- evidence ---------------------------------------------------------------------------------

def cmd_evidence(args):
    dst = connect("TARGET_DSN")
    require_migration(dst)
    regs = registers(dst)
    farmer = rows(dst, "SELECT internal_record_id FROM g2p_register_farmers WHERE functional_record_id = %s", (args.fr_id,))
    if not farmer:
        raise SetupError(f"{args.fr_id} is not in the Gen2 farmers register")
    fid = farmer[0]["internal_record_id"]
    odoo = one(dst, "SELECT odoo_id FROM migration.migrated_record WHERE kind = 'farmer' AND gen2_id = %s", (fid,))
    if odoo is None:
        raise SetupError(f"{args.fr_id} is not a migrated farmer (not in migration.migrated_record)")
    out_lines = [f"History evidence for {args.fr_id}", f"Gen1 res.partner {odoo}  ->  Gen2 farmer {fid}", ""]
    out_lines.append("Gen2 history (version 1 rows of the farmer and its records):")
    ids = {fid}
    for m, reg in regs.items():
        for r in rows(dst, f"""
                SELECT e.history_record_id, e.internal_record_id, e.section_id, e.tab_id, e.approved_by, e.approved_at,
                       e.change_request_source, h.kind AS registered_as
                  FROM {reg.history} e LEFT JOIN migration.migrated_record h ON h.gen2_id = e.history_record_id
                 WHERE e.internal_record_id = %s OR e.subject_internal_record_id = %s
                 ORDER BY e.approved_at""", (fid, fid)):
            ids.add(r["internal_record_id"])
            out_lines.append(f"  {m:16} record {r['internal_record_id']}  history {r['history_record_id']}  "
                             f"tab {r['tab_id']} / {r['section_id']}  approved {r['approved_at']} by {r['approved_by']}  "
                             f"source {r['change_request_source']}  "
                             + (f"migration ({r['registered_as']})" if r["registered_as"] else "made in Gen2"))
    out_lines += ["", "Gen1 changes archived for these records:"]
    if table_exists(dst, "migration", "gen1_change_log"):
        for r in rows(dst, """SELECT c.gen1_log_id, c.model, c.res_id, c.method, c.user_login, c.changed_at, c.kind, c.gen2_id,
                                     l.field_name, l.old_value_text, l.new_value_text
                                FROM migration.gen1_change_log c
                                LEFT JOIN migration.gen1_change_log_line l ON l.gen1_log_id = c.gen1_log_id
                               WHERE c.gen2_id = ANY(%s) ORDER BY c.changed_at, c.gen1_log_id, l.gen1_line_id""", (list(ids),)):
            out_lines.append(f"  {r['changed_at']}  {r['model']} {r['res_id']} ({r['kind']})  {r['method']} by {r['user_login']}"
                             + (f"  {r['field_name']}: {r['old_value_text']!s} -> {r['new_value_text']!s}" if r["field_name"] else ""))
    out_lines += ["", "Gen1 update requests archived for the farmer:"]
    if table_exists(dst, "migration", "gen1_change_request"):
        for r in rows(dst, """SELECT gen1_request_id, state, request_source, requested_by, validator, requested_at, new_values
                                FROM migration.gen1_change_request WHERE gen2_id = %s ORDER BY requested_at""", (fid,)):
            out_lines.append(f"  {r['requested_at']}  request {r['gen1_request_id']}  {r['state']} ({r['request_source']})  "
                             f"by {r['requested_by']}, validated by {r['validator']}  {json.dumps(r['new_values'])[:200]}")
    log_dir = os.environ.get("LOG_DIR", os.path.join(HERE, "logs"))
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(log_dir, f"{stamp}-history-evidence-{args.fr_id}.txt")
    with open(path, "w") as f:
        f.write("\n".join(out_lines) + "\n")
    print("\n".join(out_lines))
    print(f"\nWritten to {path}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Migrate the farmer profile's record history into the Farmer registry.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    a = sub.add_parser("apply")
    a.add_argument("--only", choices=["version1", "audit", "requests"])
    sub.add_parser("validate")
    e = sub.add_parser("evidence")
    e.add_argument("fr_id")
    args = p.parse_args(argv)
    load_env()
    try:
        return {"plan": cmd_plan, "apply": cmd_apply, "validate": cmd_validate, "evidence": cmd_evidence}[args.command](args)
    except SetupError as e:
        print(f"migrate_history: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
