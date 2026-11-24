"""migrate.py with a fault put in: a process of its own, so that it can be killed.

FAULT=kill_before_commit:3   SIGKILL the main process in the 3rd load, before its commit
      kill_after_commit:3    ... just after its commit
      kill_mid_insert:3      ... between two of its inserts
      kill_in_finalize       ... while queueing
      term_in_batch:2        SIGTERM during the 2nd load
      worker:solo-70         SIGKILL the worker that prepares this unit
      worker_once:solo-70    ... the first time only
      lose_connection:2      the 2nd load's connection is dropped by the server
      lose_answer:2          the 2nd load commits, and its answer is lost
      slow:0.5               every load takes this long more
COUNT_PREPARED=<file>        one line per unit prepared
"""
import os
import pathlib
import signal
import sys
import time

import psycopg2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import migrate  # noqa: E402
from farmer_profile import finalize, load  # noqa: E402

fault, _, arg = os.environ.get("FAULT", "").partition(":")
die = lambda: os.kill(os.getpid(), signal.SIGKILL)  # noqa: E731
real_write, real_insert, real_outcome, real_queue = load.write, load.insert_sql, migrate._unit_outcome, finalize.queue
calls = {"n": 0, "inserts": 0}


def write(engine, prepared, dry_run=False, before=None, after=None):
    calls["n"] += 1
    mine = arg and arg.replace(".", "").isdigit() and calls["n"] == int(float(arg))
    if fault == "slow":
        time.sleep(float(arg))
    if fault == "term_in_batch" and mine:
        os.kill(os.getpid(), signal.SIGTERM)
    calls["inserts"] = 0
    calls["mid"] = fault == "kill_mid_insert" and mine

    def last(cur, counts):
        if after:
            after(cur, counts)
        if fault == "kill_before_commit" and mine:
            die()
        if fault == "lose_connection" and mine:
            cur.execute("SELECT pg_backend_pid()")
            pid = cur.fetchone()[0]
            with psycopg2.connect(os.environ["TARGET_DSN"].replace("+psycopg2", "")) as other:
                other.cursor().execute("SELECT pg_terminate_backend(%s)", (pid,))
            time.sleep(0.3)

    out = real_write(engine, prepared, dry_run, before, last)
    if fault == "kill_after_commit" and mine:
        die()
    if fault == "lose_answer" and mine:
        raise psycopg2.OperationalError("server closed the connection unexpectedly")
    return out


def insert_sql(table, names):
    calls["inserts"] += 1
    if calls.get("mid") and calls["inserts"] == 4:
        die()
    return real_insert(table, names)


def unit_outcome(unit, plan, data, error):
    if fault in ("worker", "worker_once") and unit.key == arg:
        marker = pathlib.Path(os.environ.get("COUNT_PREPARED", "/tmp/x") + ".died")
        if fault == "worker" or not marker.exists():
            marker.write_text("x")
            die()
    out = real_outcome(unit, plan, data, error)
    if os.environ.get("COUNT_PREPARED") and "prepared" in out:
        with open(os.environ["COUNT_PREPARED"], "a") as f:
            f.write(unit.key + "\n")
    return out


def queue(*a, **k):
    before = k.get("before")

    def both(cur):
        if before:
            before(cur)
        if fault == "kill_in_finalize":
            die()
    return real_queue(*a, **{**k, "before": both})


load.write, load.insert_sql, migrate._unit_outcome, finalize.queue = write, insert_sql, unit_outcome, queue
sys.exit(migrate.main(sys.argv[1:]))
