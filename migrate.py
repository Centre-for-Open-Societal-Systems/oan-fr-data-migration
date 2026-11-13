"""Migrate farmer profile (Odoo) records into the Farmer registry.

Runs in the migration image (Dockerfile) or, locally, the registry staff-api
image (run.sh), so it writes through the registry's own models. Reads
SOURCE_DSN (Odoo, read-only) and writes TARGET_DSN.

  python migrate.py --all                     every farmer in scope, in batches
  python migrate.py --limit 10 --complete     the first 10 farmers with a household, land and crop
  python migrate.py --ids 12 40 --dry-run     transform and write, then roll back

Each batch is one transaction. A record already in the registry is left
alone, so after a failure the same command picks up where it stopped. At the
end the run queues the functional ids and completion scores the registry
generates, and writes its folder under --report: the log, the Excel report
(migration-report.xlsx: every field, where it went, how many records hold
it), every issue (issues.csv) and summary.json.
"""
import argparse
import collections
import csv
import dataclasses
import importlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import psycopg2
from sqlalchemy import create_engine


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
    parser.add_argument("--complete", action="store_true", help="with --limit: only farmers with a household, land and crop")
    parser.add_argument("--batch-size", type=int, default=500, help="farmers per transaction (default 500)")
    parser.add_argument("--dry-run", action="store_true", help="write each batch, then roll it back")
    parser.add_argument("--keep-going", action="store_true", help="log a failed batch and go on (default: stop)")
    parser.add_argument("--no-finalize", action="store_true", help="do not queue functional ids and scores")
    parser.add_argument("--no-completion-scores", action="store_true", help="queue functional ids only")
    parser.add_argument("--pack-only", action="store_true",
                        help="check codes and locations against the country pack, not the Master Data Service "
                             "(local tests only; without it MDS_API_URL must be set)")
    parser.add_argument("--pack", default=os.environ.get("PACK_ROOT", "/pack/packs"))
    parser.add_argument("--report", default=os.environ.get("REPORT_DIR", "/out"))
    return parser.parse_args(argv)


def master_data(args, engine, log):
    """Master Data's code lists and locations, and which code list each column uses."""
    from farmer_profile.masterdata import MasterData
    master = MasterData.from_pack(args.pack) if args.pack_only else MasterData.from_service()
    master.load_bindings(engine)
    log.info("codes and locations checked against %s; %d coded columns", master.describe(), len(master.bindings))
    if args.pack_only:
        log.warning("--pack-only: values are NOT checked against the Master Data Service")
    return master


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    init_registry()
    from farmer_profile import finalize, inventory, load, report, runlog, source, summary as text_summary
    from farmer_profile.codes import PackCodes
    from farmer_profile.geo import Geo
    from farmer_profile.transform import Transformer

    run_dir, log = runlog.start(args.report, "migrate", argv)
    started = time.monotonic()
    engine = create_engine(os.environ["TARGET_DSN"], pool_pre_ping=True)
    conn = psycopg2.connect(os.environ["SOURCE_DSN"])
    conn.set_session(readonly=True)

    totals = collections.OrderedDict()
    # Issues go to issues.csv as they come; the workbook gets the counts and the first rows
    issue_file = open(run_dir / "issues.csv", "w", newline="", encoding="utf-8")
    issue_csv = csv.DictWriter(issue_file, fieldnames=["severity", "entity", "odoo_id", "field", "value", "reason"])
    issue_csv.writeheader()
    issues, issue_counts, seen, batches, failed = [], collections.Counter(), set(), [], []
    written = {}  # what the batches wrote (or, in a dry run, would have): for the report
    chosen, covered = [], set()  # chosen, and with their household members: every farmer read
    after_load = {}
    master = None
    try:
        if not args.finalize_only:
            chosen = source.select_farmers(conn, None if args.all else args.limit, args.ids, args.complete)
            log.info("%d farmers chosen, %d per batch%s", len(chosen), args.batch_size,
                     " (dry run: every batch rolled back)" if args.dry_run else "")
            master = master_data(args, engine, log)
            transformer = Transformer(PackCodes(args.pack), Geo(args.pack, master.nodes), master)
            n_batches = (len(chosen) + args.batch_size - 1) // args.batch_size
            for b, start in enumerate(range(0, len(chosen), args.batch_size), start=1):
                ids = chosen[start:start + args.batch_size]
                t0 = time.monotonic()
                entry = {"batch": b, "farmers": len(ids), "first": ids[0], "last": ids[-1]}
                try:
                    data = source.read(conn, ids)
                    covered.update(f["id"] for f in data["farmers"])
                    result = transformer(data)
                    counts = load.write(engine, result, dry_run=args.dry_run)
                except Exception as exc:  # the batch is rolled back; nothing of it is written
                    conn.rollback()
                    entry.update(seconds=round(time.monotonic() - t0, 1), result=f"FAILED: {exc}"[:300], added="")
                    batches.append(entry)
                    failed.append((b, ids, exc))
                    log.error("batch %d/%d (Odoo ids %d..%d) failed and was rolled back: %s\n%s",
                              b, n_batches, ids[0], ids[-1], exc, traceback.format_exc())
                    if not args.keep_going:
                        log.error("stopping (use --keep-going to go on); rerun the same command to resume")
                        break
                    continue
                conn.rollback()  # end the read-only transaction between batches
                inventory.count_written(written, result)
                for table, c in counts.items():
                    t = totals.setdefault(table, {"rows": 0, "added": 0, "already there": 0})
                    for k in t:
                        t[k] += c[k]
                for i in result.issues:
                    key = hash((i.severity, i.entity, i.odoo_id, i.field, i.reason))
                    if key in seen:  # a household read again by a later batch repeats its issues
                        continue
                    seen.add(key)
                    row = dataclasses.asdict(i)
                    issue_csv.writerow(row)
                    issue_counts[(i.severity, i.entity, i.field, i.reason)] += 1
                    if len(issues) < report.MAX_DETAIL_ROWS:
                        issues.append(row)
                added = ", ".join(f"{t.replace('g2p_register_', '')} {c['added']}" for t, c in counts.items())
                entry.update(seconds=round(time.monotonic() - t0, 1), result="rolled back" if args.dry_run else "ok",
                             added=added)
                batches.append(entry)
                log.info("batch %d/%d: %d farmers (Odoo ids %d..%d) in %.1fs, added %s",
                         b, n_batches, len(ids), ids[0], ids[-1], entry["seconds"], added)

        if not args.dry_run and not args.no_finalize and not failed:
            log.info("queueing what the registry generates after the load")
            after_load = finalize.queue(engine, log, completion_scores=not args.no_completion_scores)
        elif failed:
            log.warning("functional ids and scores not queued: %d batches failed", len(failed))

        log.info("counting fields for the report")
        scope = None if (args.all or args.finalize_only) else sorted(covered)
        source_fields = inventory.source_fields(conn, scope)
        conn.rollback()
        target_cols = inventory.target_columns(engine, written if args.dry_run else None)
    finally:
        conn.close()
        issue_file.close()

    finished = datetime.now(timezone.utc)
    info = collections.OrderedDict([
        ("Run", run_dir.name), ("Finished (UTC)", finished.strftime("%Y-%m-%d %H:%M:%S")),
        ("Duration (s)", round(time.monotonic() - started, 1)), ("Arguments", " ".join(argv)),
        ("Source", runlog._safe_dsn(os.environ.get("SOURCE_DSN", ""))),
        ("Target", runlog._safe_dsn(os.environ.get("TARGET_DSN", ""))),
        ("Pack", args.pack), ("Values checked against", master.describe() if master else "-"), ("Farmers chosen", len(chosen)), ("Farmers read (with household members)", len(covered)), ("Batches", len(batches)),
        ("Batches failed", len(failed)), ("Dry run", "yes (nothing kept)" if args.dry_run else "no"),
    ])
    report.migration_workbook(run_dir / "migration-report.xlsx",
                              {"info": info, "counts": totals, "after_load": after_load},
                              source_fields, target_cols, issues, issue_counts, batches)
    severity_counts = collections.Counter()
    for (severity, *_), n in issue_counts.items():
        severity_counts[severity] += n
    status = collections.Counter(f["status"] for f in source_fields)
    tstatus = collections.Counter(c["status"] for c in target_cols)
    summary = {"info": info, "records": totals, "after_load": after_load,
               "farmer_profile_fields": status, "gen2_columns": tstatus,
               "issues": severity_counts,
               "failed_batches": [{"batch": b, "first": ids[0], "last": ids[-1], "error": str(e)} for b, ids, e in failed]}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    files = ["migrate.log", "summary.txt", "migration-report.xlsx", "issues.csv", "summary.json"]
    lines = text_summary.migration(info, totals, source_fields, target_cols, after_load, issue_counts,
                                   failed, args.dry_run, files)
    (run_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        log.info("%s", line)
    if failed:
        log.error("%d batches failed: rerun the same command to retry them", len(failed))
        return 1
    log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
