"""Tests on a real (throwaway) Postgres: the registry's own tables, and a small farmer profile.

dev/test.sh starts the database and sets TEST_PG (a libpq DSN without dbname).
Never SOURCE_DSN or TARGET_DSN: the databases here are dropped and filled.
"""
import importlib
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEST_PG = os.environ.get("TEST_PG")
TABLES = ["households", "farmers", "household_members", "farmer_phones", "lands", "crops"]
QUEUES = ["g2p_functional_id_generation_queue", "g2p_completion_score_computation_queue"]


def pytest_collection_modifyitems(items):
    if not TEST_PG:
        for item in items:
            if HERE in Path(str(item.fspath)).parents:
                item.add_marker(pytest.mark.skip(reason="no TEST_PG (dev/test.sh sets it)"))


def connect(db):
    conn = psycopg2.connect(f"{TEST_PG} dbname={db}")
    conn.autocommit = True
    return conn


@pytest.fixture(scope="session")
def databases(models):
    admin = connect("postgres")
    for db in ("registry_test", "gen1_test"):
        admin.cursor().execute(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
        admin.cursor().execute(f"CREATE DATABASE {db}")
    host = dict(p.split("=") for p in TEST_PG.split())
    target = f"postgresql+psycopg2://{host['user']}:{host['password']}@{host['host']}:{host.get('port', 5432)}/registry_test"
    from openg2p_fastapi_common.models import BaseORMModel
    from sqlalchemy import create_engine
    reg = connect("registry_test")
    reg.cursor().execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    engine = create_engine(target)
    BaseORMModel.metadata.create_all(engine)
    engine.dispose()
    # what the registry's db-seed brings, as little as is needed
    reg.cursor().execute("""
        INSERT INTO g2p_register_definitions (register_id, register_mnemonic, register_subject, register_description,
          register_rank, functional_id_generation_required, register_purpose, has_image, dedup_is_enabled,
          dedup_threshold_score, completion_score_required, outgest_applicable, requires_registrant_authentication)
        VALUES ('r-f', 'Farmer', 'Farmers', '', 1, true, 'REGISTER', false, false, 0, false, false, false),
               ('r-h', 'Household', 'Households', '', 2, true, 'REGISTER', false, false, 0, false, false, false)""")
    connect("gen1_test").cursor().execute((HERE / "gen1.sql").read_text())
    return {"TARGET_DSN": target, "SOURCE_DSN": f"{TEST_PG} dbname=gen1_test"}


class World:
    """Both databases, and the programs run on them."""

    def __init__(self, env, tmp_path, pack_root):
        self.tmp, self.pack = tmp_path, pack_root
        self.env = {**os.environ, **env, "MIGRATION_RETRY_DELAYS": "0.1,0.2,0.4", "REPORT_DIR": str(tmp_path / "out"),
                    "PACK_ROOT": str(pack_root), "PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1"}
        self.started, self.processes = 0, []
        self.gen1, self.gen2 = connect("gen1_test"), connect("registry_test")

    def reset(self):
        cur = self.gen1.cursor()
        cur.execute("TRUNCATE res_partner, g2p_group_membership, g2p_group_membership_g2p_group_membership_kind_rel, "
                    "g2p_reg_id, g2p_phone_number, g2p_land_information, g2p_crop_information, ir_config_parameter")
        cur.execute("INSERT INTO ir_config_parameter (key, value) VALUES ('database.uuid', 'gen1-uuid')")
        cur = self.gen2.cursor()
        cur.execute("TRUNCATE " + ", ".join([f"g2p_register_{t}" for t in TABLES]
                                            + [f"g2p_register_history_{t}" for t in TABLES] + QUEUES))
        cur.execute("DROP SCHEMA IF EXISTS migration CASCADE; DROP SCHEMA IF EXISTS migration_report CASCADE")
        cur.execute("DELETE FROM g2p_register_sections")

    def source(self, sql, *params):
        cur = self.gen1.cursor()
        cur.execute(sql, params or None)

    def rows(self, sql, *params):
        cur = self.gen2.cursor()
        cur.execute(sql, params or None)
        return cur.fetchall() if cur.description else None

    def one(self, sql, *params):
        return self.rows(sql, *params)[0][0]

    def farmers(self, n, start=1):
        """n farmers in no household, each with a phone and two lands."""
        self.source("INSERT INTO res_partner (id, given_name, family_name, gf_name_eng, gender, birthdate) "
                    "SELECT i, 'Abebe' || i, 'Kebede', 'Tola', 'male', date '1980-01-01' + i FROM generate_series(%s, %s) i",
                    start, start + n - 1)
        self.source("INSERT INTO g2p_phone_number (id, partner_id, phone_no, phone_type) SELECT i, i, '0911' || lpad(i::text, 6, '0'), "
                    "'primary' FROM generate_series(%s, %s) i", start, start + n - 1)
        self.source("INSERT INTO g2p_land_information (id, partner_id, land_id, ownership_type, total_land_area) "
                    "SELECT i * 10 + j, i, 'L' || i || '-' || j, 'owner', 1.5 FROM generate_series(%s, %s) i, generate_series(1, 2) j",
                    start, start + n - 1)

    def household(self, gid, *people, head=None):
        self.source("INSERT INTO res_partner (id, name, is_group) VALUES (%s, 'hh', true) ON CONFLICT DO NOTHING", gid)
        for person in people:
            mid = gid * 1000 + person
            self.source("INSERT INTO g2p_group_membership (id, \"group\", individual) VALUES (%s, %s, %s)", mid, gid, person)
            self.source("INSERT INTO g2p_group_membership_g2p_group_membership_kind_rel VALUES (%s, %s)", mid,
                        1 if person == (head or people[0]) else 4)

    def start(self, *args, fault="", program=HERE / "driver.py", **env):
        """The program, running. Its output goes to a file: nobody has to read a pipe for it to go on."""
        extra = [] if "--status" in args or program.name == "health.py" else ["--pack-only", "--pack", str(self.pack)]
        self.started += 1
        log = self.tmp / f"output-{self.started}"
        with open(log, "w") as out:
            p = subprocess.Popen([sys.executable, str(program), *args, *extra], cwd=ROOT, stdout=out,
                                 stderr=subprocess.STDOUT, env={**self.env, "FAULT": fault, **env})
        p.log = log
        self.processes.append(p)
        return p

    def wait(self, p, timeout=400):
        """(exit code, output). A process that does not end shows where it is."""
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGABRT)  # faulthandler prints the stacks
            p.wait(timeout=30)
            raise AssertionError("it hangs:\n" + p.log.read_text()[-6000:]) from None
        return p.returncode, p.log.read_text()

    def run(self, *args, fault="", timeout=400, **env):
        return self.wait(self.start(*args, fault=fault, **env), timeout)

    def migrate(self, *args, **kw):
        return self.run(*(args or ("--all",)), **kw)

    def apply(self, path):
        """Run migration.sql as psql does (the image has no psql). The error, or None."""
        conn = psycopg2.connect(f"{TEST_PG} dbname=registry_test")
        conn.autocommit = True
        cur, statement, lines = conn.cursor(), [], iter(path.read_text().split("\n"))
        try:
            for line in lines:
                if not statement and (line.startswith("\\") or line.startswith("--") or not line.strip()):
                    continue
                if not statement and line.startswith("COPY "):
                    rows = list(iter(lambda: next(lines), "\\."))
                    cur.copy_expert(line, io.StringIO("".join(r + "\n" for r in rows)))
                    continue
                statement.append(line)
                text = "\n".join(statement)
                if line.rstrip().endswith(";") and text.count("$guard$") % 2 == 0:
                    cur.execute(text)
                    statement = []
        except psycopg2.Error as exc:
            return str(exc)
        finally:
            conn.close()

    def verify(self, *args):
        return self.wait(self.start(*args, program=ROOT / "verify.py"))

    def health(self):
        return self.wait(self.start(program=ROOT / "health.py"))

    def measured(self, metric, record_type="", split_value=None):
        """(count, total, result) in the latest health snapshot."""
        rows = self.rows("SELECT count, total, result FROM migration_report.measure WHERE metric = %s AND record_type = %s "
                         "AND (%s::text IS NULL OR split_value = %s) AND snapshot_id = (SELECT max(snapshot_id) FROM "
                         "migration_report.snapshot WHERE taken_by <> 'verify')", metric, record_type, split_value, split_value)
        assert len(rows) == 1, (metric, record_type, rows)
        return rows[0]

    def edited(self, table, where):
        """As an approved change leaves it: a row in the registry's history."""
        self.rows(f"INSERT INTO g2p_register_history_{table} (history_record_id, internal_record_id, tab_id, section_id, "
                  f"change_request_source, is_primary_section, record_status, created_by, created_at, approved_by, approved_at) "
                  f"SELECT gen_random_uuid()::text, internal_record_id, 't', 's', 'STAFF', true, 'ACTIVE', 'x', now(), 'x', now() "
                  f"FROM g2p_register_{table} WHERE {where}")

    def counts(self):
        return {t: self.one(f"SELECT count(*) FROM g2p_register_{t}") for t in TABLES}

    def contents(self):
        """Every migrated row, but for what a run makes up anew (TEMP- ids)."""
        out = {t: self.rows(f"SELECT (to_jsonb(x) - 'functional_record_id')::text FROM g2p_register_{t} x ORDER BY 1")
               for t in TABLES}
        out["migrated_record"] = self.rows("SELECT * FROM migration.migrated_record ORDER BY kind, odoo_id")
        return out

    def unlinked(self):
        """Registry records without their migrated_record row, and the other way round."""
        every = " UNION ALL ".join(f"SELECT internal_record_id AS id FROM g2p_register_{t}" for t in TABLES)
        return (self.rows(f"SELECT id FROM ({every}) r WHERE id NOT IN (SELECT gen2_id FROM migration.migrated_record)"),
                self.rows(f"SELECT kind, odoo_id FROM migration.migrated_record WHERE gen2_id NOT IN ({every})"))

    def progress(self):
        return dict(self.rows("SELECT household_key, status FROM migration.household_progress"))

    def issues(self, severity, status="OPEN"):
        return self.rows("SELECT household_key, reason FROM migration.issue WHERE severity = %s AND status = %s "
                         "ORDER BY 1", severity, status)

    def statuses(self):
        return [r[0] for r in self.rows("SELECT status FROM migration.run ORDER BY started_at")]

    def folder(self):
        return sorted((self.tmp / "out").glob("*-migrate*"))[-1]

    def summary(self):
        return json.loads((self.folder() / "summary.json").read_text())


@pytest.fixture
def world(databases, tmp_path, pack_root):
    w = World(databases, tmp_path, pack_root)
    w.reset()
    yield w
    for p in w.processes:  # one test's leftovers must not hold the next one's lock
        if p.poll() is None:
            p.kill()
            p.wait()
    w.gen1.close()
    w.gen2.close()


@pytest.fixture(scope="session")
def models():
    import migrate
    migrate.init_registry()
    return importlib.import_module("openg2p_registry_extensions.register_domain.models")
