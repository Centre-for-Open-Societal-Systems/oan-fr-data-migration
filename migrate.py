"""Migrate farmer profile (Odoo) records into the Farmer registry.

Runs on the registry that is already there (the migration image is built on
its staff-api image; locally run.sh). Reads SOURCE_DSN (Odoo, read-only);
writes TARGET_DSN. Python reads, transforms and checks every record against
Master Data, and runs the registry's own insert hooks on it in memory; SQL
loads the finished rows (COPY, then INSERT ... ON CONFLICT DO NOTHING).

  python migrate.py --all                     every farmer in scope, in batches
  python migrate.py --limit 10 --complete     the first 10 farmers with a household, land and crop
  python migrate.py --ids 12 40 --dry-run     load each batch, then roll it back
  python migrate.py --all --sql-out           write migration.sql instead: review it, then run it
                                              with psql -v ON_ERROR_STOP=1 -f migration.sql <registry db>
  python migrate.py --status                  how far the migration is, and what is open

The household (or a farmer in none) is migrated whole or not at all. One that
fails is recorded and left out, and the rest go on. Progress and issues are
kept in the registry's database (schema "migration"), in the transaction that
writes the records: run the same command again to go on after a stop, a crash
or a fix, and what is already in is skipped. A household that has changed in
farmer profile since it was migrated is reported, not touched.

Exit codes: 0 everything loaded; 3 finished, with households that failed;
1 stopped before the end (run the same command again).

At the end the run queues the functional ids and completion scores the
registry generates, and writes its folder under --report: the log,
summary.txt, the Excel report (migration-report.xlsx), every issue
(issues.csv), summary.json, and with --sql-out migration.sql.
"""
import argparse
import collections
import concurrent.futures
import contextlib
import csv
import dataclasses
import importlib
import json
import os
import signal
import sys
import time
import traceback
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timezone

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy import exc as sa_exc

OK, STOPPED_EARLY, SOME_FAILED = 0, 1, 3
# Seconds between attempts when a database is away
RETRY_DELAYS = [float(x) for x in os.environ.get("MIGRATION_RETRY_DELAYS", "2,10,30").split(",")]
# A unit with more farmers than this is worth a look: memberships that link households by mistake
LARGE_UNIT = 100


class Fatal(Exception):
    """The run cannot go on, and it is no record's fault."""


class Stopped(Exception):
    """Asked to stop (SIGTERM, Ctrl-C)."""


def init_registry():
    importlib.import_module("farmer_profile.masterdata").configure_env()
    sys.modules["openg2p_registry_extensions"] = importlib.import_module(os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_farmer_extension"))
    importlib.import_module("openg2p_registry_staff_api.config").Settings.get_config()
    importlib.import_module("openg2p_registry_extensions.app").Initializer()


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="every farmer in scope")
    which.add_argument("--limit", type=int, help="the first N farmers")
    which.add_argument("--ids", nargs="+", type=int, help="these Odoo partner ids")
    which.add_argument("--finalize-only", action="store_true", help="only queue what is generated after the load")
    which.add_argument("--status", action="store_true", help="show how far the migration is and what is open")
    parser.add_argument("--complete", action="store_true", help="with --limit: only farmers with a household, land and crop")
    parser.add_argument("--batch-size", type=int, default=500,
                        help="farmers per transaction, whole households (default 500)")
    parser.add_argument("--dry-run", action="store_true", help="load each batch, then roll it back")
    parser.add_argument("--sql-out", action="store_true",
                        help="write the load as migration.sql in the run folder instead of running it (the "
                             "registry is only read); review it, then run it with psql")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="stop after the first household that fails (default: record it and go on)")
    parser.add_argument("--max-failures", type=int, default=100,
                        help="stop when this many households have failed in this run (default 100)")
    parser.add_argument("--keep-going", action="store_true", help=argparse.SUPPRESS)  # now the default
    parser.add_argument("--accept-source", metavar="UUID",
                        help="go on although the registry was migrated from another farmer profile database: "
                             "this one's database.uuid, to confirm")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1),
                        help="processes preparing batches in parallel (default: up to 4)")
    parser.add_argument("--no-finalize", action="store_true", help="do not queue functional ids and scores")
    parser.add_argument("--no-completion-scores", action="store_true", help="queue functional ids only")
    parser.add_argument("--pack-only", action="store_true",
                        help="check codes and locations against the country pack, not the Master Data Service "
                             "(local tests only; without it MDS_API_URL must be set)")
    parser.add_argument("--pack", default=os.environ.get("PACK_ROOT", "/pack/packs"))
    parser.add_argument("--report", default=os.environ.get("REPORT_DIR", "/out"))
    return parser.parse_args(argv)


# -- the batches, prepared in worker processes ---------------------------------------------
# Reading, transforming and running the registry's hooks is CPU work (the hooks
# are most of it), so batches are prepared in parallel; the main process loads
# them in batch order. Workers are forked after Master Data and the code lists
# are loaded, so they share them; each opens its own read-only source connection.
_WORKER = {}


def _source_connection():
    conn = psycopg2.connect(os.environ["SOURCE_DSN"])
    # one batch's queries see one moment of farmer profile
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    return conn


def _worker_init(parent):
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the main process decides when to stop
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    with contextlib.suppress(Exception):  # Linux: die with the main process, however it dies
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGKILL)
        if os.getppid() != parent:
            os._exit(1)
    _WORKER["conn"] = None


def _unit_outcome(unit, plan, data, error) -> dict:
    """What became of one unit: "do" is load, same, reverted, changed, incomparable or failed."""
    from farmer_profile import load, source, tracking
    out = {"unit": unit, "issues": [], "fingerprint": None}

    def failed(exc, trace=""):
        return {**out, "do": "failed", "error_class": type(exc).__name__,
                "error": str(exc).strip() or type(exc).__name__, "trace": trace}

    if error is not None:
        if plan["do"] != "load":  # it is in the registry: not a household left out
            return {**out, "do": "changed", "what": f"cannot be read from farmer profile any more ({error}): not touched"}
        return failed(error)
    out["fingerprint"] = now = source.fingerprint(data)
    if plan["do"] == "recomposed":
        return {**out, "do": "changed", "what": "its members changed in farmer profile since it was migrated "
                f"(migrated with {', '.join(plan['owners'])}): not touched"}
    if plan["do"] == "compare":
        if plan["version"] != source.FINGERPRINT_VERSION:
            return {**out, "do": "incomparable"}
        parts = source.changed_parts(plan["fingerprint"], now)
        if parts:
            return {**out, "do": "changed",
                    "what": f"changed in farmer profile since it was migrated ({', '.join(parts)}): not touched"}
        return {**out, "do": "reverted" if plan["status"] == "CHANGED" else "same"}
    try:
        result = _WORKER["transformer"](data)
        prepared = load.prepare(result)
    except (load.SchemaMismatch, MemoryError, ImportError):
        raise
    except Exception as exc:
        return failed(exc, traceback.format_exc())
    gen2_ids = {i for table, _ in prepared.items() for i in prepared.ids(table)}
    return {**out, "do": "load", "prepared": prepared, "records": tracking.links(unit, data, gen2_ids),
            "issues": [dataclasses.asdict(i) for i in result.issues]}


def _prepare_batch(job) -> dict:
    from farmer_profile import source
    b, work = job
    t0 = time.monotonic()
    plans = {unit.key: plan for unit, plan in work}
    try:
        if _WORKER["conn"] is None or _WORKER["conn"].closed:
            _WORKER["conn"] = _source_connection()
        read = source.read_units(_WORKER["conn"], [unit for unit, _ in work])
        _WORKER["conn"].rollback()
        return {"units": [_unit_outcome(u, plans[u.key], data, error) for u, data, error in read], "error": None,
                "seconds": time.monotonic() - t0}
    except (psycopg2.OperationalError, psycopg2.InterfaceError, MemoryError) as exc:
        kind, error = "away", exc
    except Exception as exc:
        kind, error = "fatal", exc
    trace = "".join(traceback.format_exception(error))
    with contextlib.suppress(Exception):
        _WORKER["conn"].close()
    _WORKER["conn"] = None
    return {"error": kind, "trace": trace, "message": str(error).strip() or type(error).__name__}


def _executor(workers):
    import multiprocessing
    return concurrent.futures.ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("fork"),
                                                  initializer=_worker_init, initargs=(os.getpid(),))


def _prepared_batches(jobs, workers, engine, stop, log):
    """(batch, outcome) in batch order. Only a few batches are prepared ahead of
    the one being loaded. A worker that dies (out of memory) is noticed: its
    batch is tried once more on its own."""
    jobs = iter(jobs)
    pending = collections.deque()  # (job, future)

    def submit(job):
        try:
            return executor.submit(_prepare_batch, job)
        except BrokenProcessPool as exc:
            future = concurrent.futures.Future()
            future.set_exception(exc)
            return future

    def result(future):
        while True:  # in short waits, so a signal is seen
            try:
                return future.result(timeout=0.5)
            except concurrent.futures.TimeoutError:
                if stop["asked"]:
                    raise Stopped from None

    engine.dispose()  # no connection of ours is shared with a forked process
    executor = _executor(workers)
    try:
        while True:
            while len(pending) <= workers and not stop["asked"]:
                job = next(jobs, None)
                if job is None:
                    break
                pending.append((job, submit(job)))
            if not pending:
                return
            job, future = pending.popleft()
            try:
                outcome = result(future)
            except BrokenProcessPool:
                log.warning("a worker process died (out of memory?): trying batch %d again on its own", job[0])
                executor.shutdown(wait=True, cancel_futures=True)
                engine.dispose()
                executor = _executor(1)
                try:
                    outcome = result(submit(job))
                except BrokenProcessPool:
                    raise Fatal(f"a worker process died twice preparing batch {job[0]} (first household "
                                f"{job[1][0][0].key}): probably out of memory. Nothing of it was written; try a smaller "
                                "--batch-size, fewer --workers or more memory") from None
                executor.shutdown(wait=True)
                engine.dispose()
                executor = _executor(workers)
                pending = collections.deque((j, submit(j)) for j, _ in pending)
            for delay in RETRY_DELAYS:
                if outcome["error"] != "away":
                    break
                log.warning("batch %d could not be read (%s): again in %.0fs", job[0], outcome["message"], delay)
                time.sleep(delay)
                try:
                    outcome = result(submit(job))
                except BrokenProcessPool:
                    raise Fatal("a worker process died") from None
            if outcome["error"]:
                log.error("batch %d:\n%s", job[0], outcome["trace"])
                raise Fatal(f"batch {job[0]} could not be prepared: {outcome['message']}")
            yield job, outcome
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


# -- loading -------------------------------------------------------------------------------

# A value the registry's tables do not take: some record's fault
_DATA_ERRORS = (psycopg2.DataError, psycopg2.IntegrityError, UnicodeError)
# The database is away, full or busy: nobody's fault, worth another try
_AWAY = (psycopg2.OperationalError, psycopg2.InterfaceError, sa_exc.OperationalError, sa_exc.InterfaceError)


def _retrying(what, log, action):
    for delay in [*RETRY_DELAYS, None]:
        try:
            return action()
        except _AWAY as exc:
            if delay is None:
                raise Fatal(f"{what}: {str(exc).strip()}") from exc
            log.warning("%s: %s; again in %.0fs", what, str(exc).strip().splitlines()[0], delay)
            time.sleep(delay)


class Loader:
    """Writes the units of a batch, and finds the ones that cannot be written."""

    def __init__(self, engine, log, run_id, tracked, dry_run):
        self.engine, self.log, self.run_id, self.tracked, self.dry_run = engine, log, run_id, tracked, dry_run

    def sort_out(self, outcomes):
        """Units new to the migration's tables may be in the registry already (from
        before the tables): all of their records, and they are adopted; some, and
        they are reported."""
        from farmer_profile import load
        new = [o for o in outcomes if o["do"] == "load"]
        if not new:
            return
        merged = load.merge(o["prepared"] for o in new)
        there = _retrying("the registry could not be read", self.log, lambda: load.existing_ids(self.engine, merged))
        if not there:
            return
        for o in new:
            ids = {i for table, _ in o["prepared"].items() for i in o["prepared"].ids(table)}
            if ids <= there:
                o["do"] = "adopt"
            elif ids & there:
                o.update(do="changed", what=f"partly in the registry already ({len(ids & there)} of {len(ids)} records), "
                                            "and not by a run on record: not touched")

    def load(self, outcomes) -> tuple[dict, list]:
        """(what was written per table, the outcomes that went in). One that did not is marked failed."""
        if not outcomes:
            return {}, []
        try:
            return _retrying("the batch could not be written", self.log, lambda: self._write(outcomes)), list(outcomes)
        except _DATA_ERRORS as exc:
            if len(outcomes) == 1:
                outcomes[0].update(do="failed", error_class=type(exc).__name__, error=str(exc).strip(), trace="")
                return {}, []
        middle = len(outcomes) // 2
        counts, loaded = self.load(outcomes[:middle])
        more, also = self.load(outcomes[middle:])
        for table, c in more.items():
            mine = counts.setdefault(table, dict.fromkeys(c, 0))
            for k in c:
                mine[k] += c[k]
        return counts, loaded + also

    def _write(self, outcomes):
        from farmer_profile import load, tracking
        prepared = load.merge(o["prepared"] for o in outcomes)
        if not self.tracked:
            return load.write(self.engine, prepared, dry_run=self.dry_run)
        if tracking.loaded_by(self.engine, self.run_id, [o["unit"].key for o in outcomes]):
            # a commit whose answer was lost: it is in
            return {t: {"rows": len(rows), "added": len(rows), "already there": 0} for t, (_, rows) in prepared.items()}
        batch = tracking.Batch()
        for o in outcomes:
            batch.loaded(o["unit"], o["fingerprint"], o["issues"], o["records"])

        def before(cur):
            tracking.fence(cur, self.run_id)

        def after(cur, counts):
            lost = {t: c["already there"] for t, c in counts.items() if c["already there"]}
            if lost:
                raise Fatal(f"records the registry did not have a moment ago are there now ({lost}): is something else "
                            "writing migrated records? Nothing of this batch was kept")
            tracking.apply(cur, self.run_id, batch)

        return load.write(self.engine, prepared, before=before, after=after)

    def record(self, outcomes):
        """Progress and issues of the units that were not written."""
        from farmer_profile import tracking
        batch = tracking.Batch()
        for o in outcomes:
            if o["do"] == "failed":
                batch.failed(o["unit"], o["error_class"], o["error"], o["issues"])
            elif o["do"] == "changed":
                batch.changed(o["unit"], o["fingerprint"], o["what"])
            elif o["do"] == "reverted":
                batch.unchanged_again(o["unit"], o["fingerprint"])
            elif o["do"] == "adopt":
                batch.loaded(o["unit"], o["fingerprint"], o["issues"], o["records"], adopted=True)
        if self.tracked:
            _retrying("the progress could not be written", self.log,
                      lambda: tracking.record(self.engine, self.run_id, batch))
        return batch


def master_data(args, engine, log):
    """Master Data's code lists and locations, and which code list each column uses."""
    from farmer_profile.masterdata import MasterData
    master = MasterData.from_pack(args.pack) if args.pack_only else MasterData.from_service()
    master.load_bindings(engine)
    log.info("codes and locations checked against %s; %d coded columns", master.describe(), len(master.bindings))
    if args.pack_only:
        log.warning("--pack-only: values are NOT checked against the Master Data Service")
    return master


def show_status():
    from farmer_profile import summary, tracking
    engine = create_engine(os.environ["TARGET_DSN"])
    if not tracking.exists(engine):
        print("nothing has been migrated with this version yet (no migration tables in the registry)")
        return OK
    for line in summary.status(tracking.totals(engine), tracking.runs(engine, 10)):
        print(line)
    return OK


def _issue_rows(outcome):
    """An outcome's issues, as rows of issues.csv."""
    from farmer_profile.tracking import plain
    for row in _raw_issue_rows(outcome):
        yield {k: plain(v) for k, v in row.items()}


def _raw_issue_rows(outcome):
    unit, base = outcome["unit"], {"status": "OPEN", "first_run": "", "last_run": ""}
    farmers = ", ".join(map(str, unit.farmers))
    if outcome["do"] == "failed":
        yield {**base, "household": unit.key, "severity": "failed", "entity": "household", "odoo_id": farmers,
               "field": outcome["error_class"], "value": unit.key, "reason": outcome["error"]}
    if outcome["do"] == "changed":
        yield {**base, "household": unit.key, "severity": "changed", "entity": "household", "odoo_id": farmers,
               "field": "", "value": unit.key, "reason": outcome["what"]}
        return
    for i in outcome["issues"]:
        yield {**base, "household": unit.key, **i}


class Run:
    """One execution: what it was asked, what it did, and its reports."""

    def __init__(self, args, argv):
        from farmer_profile import runlog
        self.args, self.argv = args, argv
        self.run_dir, self.log = runlog.start(args.report, "migrate", argv)
        self.run_id = self.run_dir.name
        self.started = time.monotonic()
        self.engine = create_engine(os.environ["TARGET_DSN"], pool_pre_ping=True)
        self.writes = not (args.dry_run or args.sql_out)
        self.tracked = False      # the run's row is in migration.run
        self.source_uuid = None
        self.master = None
        self.sql_file = None
        self.planned, self.not_people = [], []
        self.n_batches = 0
        self.households = collections.Counter()  # what became of the units
        self.totals = collections.OrderedDict()
        self.batches, self.failed = [], []       # failed: the outcomes
        self.issues, self.issue_counts = [], collections.Counter()
        self.covered = set()
        self.written = {}         # what the batches wrote (or would have): for the report
        self.after_load = {}
        self.stop = {"asked": False}
        self.error = None
        self.health, self.no_health = None, "Measured after a load over every farmer (--all) that reaches its end: " \
                                             "run health.py"

    # -- before ------------------------------------------------------------------------

    def plan(self):
        from farmer_profile import source
        args = self.args
        conn = _source_connection()
        try:
            self.source_uuid = source.database_uuid(conn)
            self.check_source()
            if args.finalize_only:
                return
            chosen = source.select_farmers(conn, None if args.all else args.limit, args.ids, args.complete)
            self.planned, self.not_people = source.units(conn, chosen)
        finally:
            conn.close()
        if self.not_people:
            self.log.warning("%d of the ids asked for are no active person in farmer profile: %s", len(self.not_people),
                             ", ".join(map(str, self.not_people[:20])))
        sizes = [len(u.farmers) for u in self.planned]
        shared = sum(1 for u in self.planned if len(u.households) > 1)
        self.log.info("%d farmers chosen; %d households with %d farmers (%d farmers in no household; %d units of several "
                      "households sharing a member; largest %d farmers)%s", len(chosen), len(self.planned), sum(sizes),
                      sum(1 for u in self.planned if not u.households), shared, max(sizes, default=0),
                      " (dry run: every batch rolled back)" if args.dry_run else "")
        large = [u for u in self.planned if len(u.farmers) > LARGE_UNIT]
        if large:
            self.log.warning("%d units have more than %d farmers, migrated all or none (e.g. %s, %d farmers): check "
                             "their memberships", len(large), LARGE_UNIT, large[0].key, len(large[0].farmers))

    def check_source(self):
        from farmer_profile import tracking
        if not tracking.exists(self.engine):
            return
        known = tracking.other_sources(self.engine, self.source_uuid)
        if known and self.args.accept_source != (self.source_uuid or ""):
            raise Fatal(f"this registry was migrated from another farmer profile database (its database.uuid is "
                        f"{', '.join(known)}; this one's is {self.source_uuid}). The same Odoo id may be another person "
                        "there. If it is the same data, confirm with --accept-source " + str(self.source_uuid))

    # -- the load ----------------------------------------------------------------------

    def migrate(self):
        from farmer_profile import load, source, tracking
        from farmer_profile.codes import PackCodes
        from farmer_profile.geo import Geo
        from farmer_profile.transform import Transformer
        args, log = self.args, self.log
        self.master = master_data(args, self.engine, log)
        _WORKER["transformer"] = Transformer(PackCodes(args.pack), Geo(args.pack, self.master.nodes), self.master)
        have_tables = tracking.exists(self.engine)
        if args.sql_out:
            mark = tracking.watermark(self.engine)
            self.sql_file = load.SqlFile(self.run_dir / "migration.sql", [
                "Farmer profile -> Farmer registry migration, written by migrate.py",
                f"Run {self.run_id}, arguments: {' '.join(self.argv)}",
                f"Codes and locations checked against {self.master.describe()}",
                "Every batch's finished rows are COPY data into temporary tables; at the end they are inserted",
                "into the registry's tables (a record already there is left alone), the migration's progress and",
                "issues are recorded, and the functional ids and completion scores are queued.",
                "One transaction: nothing is kept if any statement fails. It refuses to run twice, beside another",
                "migration run, or on a registry that has been migrated into since it was written.",
                "",
                "Run:  psql -v ON_ERROR_STOP=1 -f migration.sql <registry database>",
                "Then: verify.py, as after a direct run."],
                tracking.sql_guard(self.run_id, mark, self.source_uuid))
            log.info("writing the load to %s (the registry is only read)", self.run_dir / "migration.sql")
        groups = source.batches(self.planned, args.batch_size)
        self.n_batches = len(groups)
        workers = max(1, min(args.workers, self.n_batches))
        log.info("%d batches; %d worker processes read, transform and finish them, one writer loads them in order",
                 self.n_batches, workers)

        def jobs():
            for b, group in enumerate(groups, 1):
                state = _retrying("the progress could not be read", log, lambda g=group: tracking.State(self.engine, g)) \
                    if have_tables else tracking.NoState()
                yield b, [(u, state.plan(u)) for u in group]

        loader = Loader(self.engine, log, self.run_id, self.tracked, args.dry_run)
        with open(self.run_dir / "issues.csv", "w", newline="", encoding="utf-8") as handle:
            out = csv.DictWriter(handle, fieldnames=tracking.ISSUE_COLUMNS)
            out.writeheader()
            with contextlib.closing(_prepared_batches(jobs(), workers, self.engine, self.stop, log)) as prepared:
                for (b, work), outcome in prepared:
                    self.batch(b, work, outcome, loader, out)
                    handle.flush()
                    if self.failed and args.stop_on_error:
                        raise Fatal(f"household {self.failed[0]['unit'].key} failed (--stop-on-error)")
                    if len(self.failed) >= args.max_failures:
                        raise Fatal(f"{len(self.failed)} households failed: stopping, in case they all have one cause "
                                    "(--max-failures to allow more)")
                    if self.stop["asked"]:
                        raise Stopped
        if self.stop["asked"]:
            raise Stopped

    def batch(self, b, work, outcome, loader, issue_csv):
        from farmer_profile import inventory, load, report
        t0 = time.monotonic()
        outcomes = outcome["units"]
        loader.sort_out(outcomes)
        to_load = [o for o in outcomes if o["do"] == "load"]
        if self.sql_file:
            loaded = to_load
            prepared = load.merge(o["prepared"] for o in loaded)
            counts = {t: {"rows": len(rows), "added": len(rows), "already there": 0} for t, (_, rows) in prepared.items()}
            rest = loader.record([o for o in outcomes if o["do"] != "load"])
            for o in loaded:
                rest.loaded(o["unit"], o["fingerprint"], o["issues"], o["records"])
            self.sql_file.add(prepared, rest)
        else:
            counts, loaded = loader.load(to_load)
            loader.record([o for o in outcomes if o["do"] not in ("load", "same", "incomparable")])
        inventory.count_written(self.written, load.merge(o["prepared"] for o in loaded))
        for table, c in counts.items():
            mine = self.totals.setdefault(table, dict.fromkeys(c, 0))
            for k in c:
                mine[k] += c[k]
        for o in outcomes:
            self.households[o["do"]] += 1
            self.covered.update(o["unit"].farmers)
            for row in _issue_rows(o):
                issue_csv.writerow(row)
                self.issue_counts[(row["severity"], row["entity"], row["field"], row["reason"])] += 1
                # the workbook shows the first rows; issues.csv has them all
                if len(self.issues) < report.MAX_DETAIL_ROWS or row["severity"] == "changed":
                    self.issues.append(row)
            if o["do"] == "failed":
                self.failed.append(o)
                self.log.error("household %s (farmers %s) failed and was left out: %s: %s%s", o["unit"].key,
                               ", ".join(map(str, o["unit"].farmers[:20])), o["error_class"], o["error"],
                               "\n" + o["trace"] if o["trace"] else "")
            o.pop("prepared", None)
            o.pop("records", None)
        done = collections.Counter(o["do"] for o in outcomes)
        added = ", ".join(f"{t.replace('g2p_register_', '')} {c['added']}" for t, c in counts.items()) or "nothing"
        result = ", ".join(f"{n} {_WORDS[k]}" for k, n in done.items())
        farmers = [f for u, _ in work for f in u.farmers]
        self.batches.append({"batch": b, "households": len(work), "farmers": len(farmers), "first": work[0][0].key,
                             "last": work[-1][0].key, "seconds": round(outcome["seconds"] + time.monotonic() - t0, 1),
                             "result": result, "added": added + (" (rolled back)" if self.args.dry_run else
                                                                 " (in migration.sql)" if self.sql_file else "")})
        self.log.info("batch %d/%d: %d households, %d farmers (%s..%s), prepared in %.1fs, loaded in %.1fs: %s; added %s",
                      b, self.n_batches, len(work), len(farmers), work[0][0].key, work[-1][0].key, outcome["seconds"],
                      time.monotonic() - t0, result, added)

    def finalize(self, complete):
        from farmer_profile import finalize, tracking
        args = self.args
        scores = not args.no_completion_scores
        if self.sql_file:
            if complete:
                self.sql_file.finish(tracking.apply_sql(self.run_id),
                                     [] if args.no_finalize else finalize.statements(self.engine, completion_scores=scores))
                self.log.info("wrote %s", self.sql_file.path)
            else:
                self.sql_file.abandon("the run stopped before its end: this file is incomplete and does nothing")
                self.log.error("migration.sql is incomplete: it ends in ROLLBACK")
        elif complete and self.writes and not args.no_finalize:
            self.log.info("queueing what the registry generates after the load")
            self.after_load = _retrying("the queues could not be written", self.log, lambda: finalize.queue(
                self.engine, self.log, completion_scores=scores,
                before=lambda cur: tracking.fence(cur, self.run_id) if self.tracked else None))

    # -- the whole ---------------------------------------------------------------------

    def ask_to_stop(self, signum, _frame):
        if self.stop["asked"]:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        self.stop["asked"] = True
        self.log.warning("%s: stopping after the current batch (again to stop at once)", signal.Signals(signum).name)

    def execute(self):
        from farmer_profile import tracking
        before = {s: signal.signal(s, self.ask_to_stop) for s in (signal.SIGTERM, signal.SIGINT)}
        status = "FAILED"
        try:
            with tracking.run_lock(os.environ["TARGET_DSN"]):
                try:
                    self.plan()
                    if self.writes:
                        tracking.ensure(self.engine)
                        mode = "finalize" if self.args.finalize_only else "load"
                        for killed in tracking.start_run(self.engine, self.run_id, mode, " ".join(self.argv),
                                                         self.source_uuid):
                            self.log.warning("run %s was killed before its end: its finished households are kept", killed)
                        self.tracked = True
                    if not self.args.finalize_only:
                        self.migrate()
                        if self.tracked and self.args.all:
                            tracking.retire(self.engine, [u.key for u in self.planned])
                    self.finalize(True)
                    status = "COMPLETED_WITH_FAILURES" if self.failed else "COMPLETED"
                except Stopped:
                    status, self.error = "STOPPED", "asked to stop"
                except (Fatal, tracking.NotOurRun) as exc:
                    self.error = str(exc)
                except SystemExit as exc:
                    self.error = str(exc.code)
                except Exception as exc:
                    self.error = f"{type(exc).__name__}: {str(exc).strip()}"
                    self.log.error("%s", traceback.format_exc())
                if self.error:
                    self.log.error("stopped: %s", self.error)
                    if self.sql_file and not self.sql_file.handle.closed:
                        self.finalize(False)
                # the health is the whole migration's: worth its time after a run over every farmer only
                if self.tracked and not self.error and self.args.all:
                    self.measure_health(status)
                elif self.tracked and not self.error and not self.args.finalize_only:
                    self.no_health = ("Not measured: this run covered only some farmers. Run health.py for the "
                                      "whole migration")
                try:
                    self.reports(status)
                except Exception:
                    self.log.error("the reports could not be written:\n%s", traceback.format_exc())
                if self.tracked:
                    try:
                        tracking.finish_run(self.engine, self.run_id, status, self.counts(), self.error)
                    except Exception as exc:
                        self.log.error("the run's end could not be recorded (the next run marks it INTERRUPTED): %s", exc)
        except tracking.Busy as exc:
            self.log.error("%s", exc)
            return STOPPED_EARLY
        except _AWAY as exc:
            self.log.error("the registry's database could not be reached: %s", str(exc).strip())
            return STOPPED_EARLY
        finally:
            for s, handler in before.items():
                signal.signal(s, handler)
        if self.error:
            self.log.error("stopped before the end: run the same command again to go on")
            return STOPPED_EARLY
        if self.failed:
            self.log.error("%d households failed and were left out: fix them and run the same command again",
                           len(self.failed))
            return SOME_FAILED
        self.log.info("done")
        return OK

    def measure_health(self, status):
        """After a load that reached its end. Whatever goes wrong here does not change how the load ended."""
        from farmer_profile import health
        try:
            models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
            self.health = health.take(self.engine, os.environ["SOURCE_DSN"], models, self.log, "migrate", status)
        except Exception as exc:
            self.no_health = "The health could not be measured: see the log. Run health.py"
            self.log.error("the health could not be measured (the load is not affected; run health.py): %s",
                           str(exc).strip() or type(exc).__name__)

    def counts(self):
        out = {"planned": len(self.planned), **{_WORDS[k]: n for k, n in self.households.items()}}
        out["remaining"] = len(self.planned) - sum(self.households.values())
        out["records added"] = {t: c["added"] for t, c in self.totals.items()}
        return out

    def reports(self, status):
        """The run's folder. Whatever cannot be read any more is left out, not fatal."""
        from farmer_profile import inventory, report, runlog, tracking
        from farmer_profile import summary as text_summary
        args, log = self.args, self.log

        def attempt(what, action, default):
            try:
                return action()
            except Exception as exc:
                log.error("%s could not be read for the report: %s", what, str(exc).strip())
                return default

        log.info("counting fields for the report")

        def source_fields():
            conn = _source_connection()
            try:
                return inventory.source_fields(conn, None if args.all or args.finalize_only else sorted(self.covered))
            finally:
                conn.close()
        fields = attempt("farmer profile's fields", source_fields, [])
        columns = attempt("the registry's columns",
                          lambda: inventory.target_columns(self.engine, None if self.writes else self.written), [])
        # A run that writes reports what the tables hold, over all runs; others, what they found themselves
        issues, issue_counts = self.issues, self.issue_counts
        failed = [{"household_key": o["unit"].key, "farmer_ids": list(o["unit"].farmers), "error_class": o["error_class"],
                   "error": o["error"], "attempts": 1, "first_run_id": "", "last_run_id": ""} for o in self.failed]
        changed = [{"household_key": i["household"], "farmer_ids": i["odoo_id"], "what": i["reason"], "first_run_id": "",
                    "last_run_id": ""} for i in self.issues if i["severity"] == "changed"]
        runs, overall = [], None
        if self.tracked:
            got = attempt("the migration's tables", lambda: self.read_tables(tracking, report), None)
            if got:
                issues, issue_counts, failed, changed, runs, overall = got
                for r in runs:  # its end is recorded after the reports
                    if r["run_id"] == self.run_id:
                        r.update(status=status, counts=self.counts(), error=self.error)
        if not (self.run_dir / "issues.csv").exists():
            with open(self.run_dir / "issues.csv", "w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(handle, fieldnames=tracking.ISSUE_COLUMNS).writeheader()

        finished = datetime.now(timezone.utc)
        counts = self.counts()
        info = collections.OrderedDict([
            ("Run", self.run_id), ("Status", status), ("Finished (UTC)", finished.strftime("%Y-%m-%d %H:%M:%S")),
            ("Duration (s)", round(time.monotonic() - self.started, 1)), ("Arguments", " ".join(self.argv)),
            ("Source", runlog._safe_dsn(os.environ.get("SOURCE_DSN", ""))),
            ("Target", runlog._safe_dsn(os.environ.get("TARGET_DSN", ""))),
            ("Pack", args.pack), ("Values checked against", self.master.describe() if self.master else "-"),
            ("Households planned", counts["planned"]), ("Farmers covered", len(self.covered)),
            ("Households failed", len(self.failed)), ("Batches", f"{len(self.batches)} of {self.n_batches}"),
            ("Dry run", "yes (nothing kept)" if args.dry_run else "no"),
            ("Mode", "SQL file: migration.sql, nothing written" if args.sql_out else
             ("dry run: every batch rolled back" if args.dry_run else "loaded into the registry"))])
        if self.error:
            info["Stopped"] = self.error
        data = {"info": info, "counts": self.totals, "after_load": self.after_load, "households": counts,
                "overall": overall, "failed": failed, "changed": changed, "runs": runs,
                "health": self.health, "no_health": self.no_health}
        attempt("the workbook's data", lambda: report.migration_workbook(
            self.run_dir / "migration-report.xlsx", data, fields, columns, issues, issue_counts, self.batches), None)
        severity_counts = collections.Counter()
        for (severity, *_), n in issue_counts.items():
            severity_counts[severity] += n
        doc = {"info": info, "status": status, "households": counts, "overall": overall, "records": self.totals,
               "after_load": self.after_load,
               "farmer_profile_fields": collections.Counter(f["status"] for f in fields),
               "gen2_columns": collections.Counter(c["status"] for c in columns), "issues": severity_counts,
               "failed_households": failed[:1000]}
        (self.run_dir / "summary.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
        files = ["migrate.log", "summary.txt", "migration-report.xlsx", "issues.csv", "summary.json"] + \
            (["migration.sql"] if args.sql_out else [])
        lines = text_summary.migration(info, data, fields, columns, issue_counts, files, dry_run=args.dry_run,
                                       sql_out=args.sql_out, finalized=not args.no_finalize, error=self.error)
        if self.health:
            from farmer_profile import health_report
            lines = [*health_report.lines(self.health), "", *lines]
        (self.run_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for line in lines:
            log.info("%s", line)

    def read_tables(self, tracking, report):
        """Issues of every run: into issues.csv all of them, the open ones counted, the first rows kept."""
        kept, counts = [], collections.Counter()
        path = self.run_dir / "issues.csv"
        with open(path.with_suffix(".tmp"), "w", newline="", encoding="utf-8") as handle:
            out = csv.DictWriter(handle, fieldnames=tracking.ISSUE_COLUMNS)
            out.writeheader()
            for row in tracking.issues(self.engine):
                out.writerow(row)
                if len(kept) < report.MAX_DETAIL_ROWS:
                    kept.append(row)
                if row["status"] == "OPEN":
                    counts[(row["severity"], row["entity"], row["field"], row["reason"])] += 1
        os.replace(path.with_suffix(".tmp"), path)
        return (kept, counts, tracking.households(self.engine, "FAILED"), tracking.households(self.engine, "CHANGED"),
                tracking.runs(self.engine), tracking.totals(self.engine))


_WORDS = {"load": "loaded", "same": "already in", "reverted": "back to what was migrated", "adopt": "adopted",
          "changed": "changed in farmer profile", "failed": "failed", "incomparable": "already in, not comparable"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.status:
        return show_status()
    init_registry()
    return Run(args, argv).execute()


if __name__ == "__main__":
    sys.exit(main())
