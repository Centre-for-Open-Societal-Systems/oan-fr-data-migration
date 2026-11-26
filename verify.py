"""Verify a farmer profile -> Farmer registry migration.

Reads both databases and checks the registry against farmer profile: see
farmer_profile/verification.py for what is checked. Exits 1 when a check fails.
A run over every farmer also saves its results, as counts, for the health
report (schema migration_report); nothing else is written.

  python verify.py                 every farmer in scope
  python verify.py --limit 10 --complete
  python verify.py --ids 12 40

Writes its folder under --report: verify.log, verify-report.xlsx (Summary,
Checks, Columns, Differences), differences.csv (every difference) and summary.json.
"""
import argparse
import collections
import csv
import importlib
import json
import os
import sys
import time

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from migrate import init_registry, master_data


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ids", nargs="+", type=int)
    parser.add_argument("--complete", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--pack-only", action="store_true",
                        help="check against the country pack, not the Master Data Service (local tests only)")
    parser.add_argument("--pack", default=os.environ.get("PACK_ROOT", "/pack/packs"))
    parser.add_argument("--report", default=os.environ.get("REPORT_DIR", "/out"))
    args = parser.parse_args(argv)

    init_registry()
    from farmer_profile import health, report, runlog, source, summary as text_summary, tracking, verification as V
    from farmer_profile.codes import PackCodes
    from farmer_profile.geo import Geo
    from farmer_profile.transform import MIGRATED_BY, Result, Transformer

    run_dir, log = runlog.start(args.report, "verify", argv)
    started = time.monotonic()
    models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
    engine = create_engine(os.environ["TARGET_DSN"], pool_pre_ping=True)
    conn = psycopg2.connect(os.environ["SOURCE_DSN"])
    conn.set_session(readonly=True)
    checks, comparison, direct = V.Checks(), V.Comparison(), V.Direct()
    everything = not args.limit and not args.ids

    diff_file = open(run_dir / "differences.csv", "w", newline="", encoding="utf-8")
    diff_csv = csv.DictWriter(diff_file, fieldnames=["register", "record_id", "odoo_id", "column", "expected", "found"])
    diff_csv.writeheader()
    kept, n_diff = [], 0
    try:
        chosen = source.select_farmers(conn, args.limit, args.ids, args.complete)
        planned, _ = source.units(conn, chosen)
        conn.rollback()
        log.info("%d farmers to verify, in %d households, %d farmers per batch", len(chosen), len(planned), args.batch_size)
        master = master_data(args, engine, log)
        transformer = Transformer(PackCodes(args.pack), Geo(args.pack, master.nodes), master)
        expected_ids = collections.defaultdict(set)
        skipped = collections.Counter()
        tracked = tracking.exists(engine)
        current = tracked and tracking.current(engine)
        left_out, unreadable, twice = collections.defaultdict(list), [], []
        groups = source.batches(planned, args.batch_size)
        n_batches = len(groups)
        for b, group in enumerate(groups, start=1):
            state = tracking.State(engine, group) if tracked else tracking.NoState()
            chosen_here = []
            for unit, data, error in source.read_units(conn, group):
                status = state.progress.get(unit.key, ("",))[0] if tracked else ""
                plan = state.plan(unit)
                if status in ("FAILED", "CHANGED", "CONFLICT") or plan["do"] == "recomposed":
                    left_out[status or "CHANGED"].append(unit.key)
                    continue
                if error is not None:
                    unreadable.append(unit.key)
                    continue
                if plan["do"] == "compare" and plan["version"] == source.FINGERPRINT_VERSION \
                        and source.changed_parts(plan["fingerprint"], source.fingerprint(data)):
                    left_out["CHANGED"].append(unit.key)  # changed since the last run
                    continue
                chosen_here.append((unit, data, transformer(data)))
            conn.rollback()
            if current:  # a household the registry has edited since is not compared: it is the registry's now
                ids = {r["internal_record_id"] for _, _, res in chosen_here for _, rows in res.tables() for r in rows}
                raw = engine.raw_connection()
                try:
                    edited = tracking.edited(raw.cursor(), models, ids)
                    raw.rollback()
                finally:
                    raw.close()
                mine = []
                for unit, data, res in chosen_here:
                    if edited & {r["internal_record_id"] for _, rows in res.tables() for r in rows}:
                        left_out["EDITED"].append(unit.key)
                    else:
                        mine.append((unit, data, res))
                chosen_here = mine
            parts, results = [d for _, d, _ in chosen_here], [r for _, _, r in chosen_here]
            for unit, _, _ in chosen_here:
                if unit.households:
                    twice += [(unit.key, V.record_id("member", f"solo-{f}")) for f in unit.farmers]
            odoo_of = {}
            data = source.merge(parts)
            for kind, rows in (("farmer", data["farmers"]), ("land", data["lands"]), ("crop", data["crops"])):
                odoo_of.update({V.record_id(kind, r["id"]): r["id"] for r in rows})
            with Session(engine) as session, session.begin():
                for result in results:
                    for register, rows in result.tables():
                        for r in rows:
                            expected_ids[register].add(r["internal_record_id"])
                    for i in result.issues:
                        if i.severity == "skipped":
                            skipped[i.entity] += 1
                comparison.run(session, models, Result.joined(results), odoo_of)
                direct.run(session.connection(), data)
                session.rollback()
            for d in comparison.differences:
                diff_csv.writerow(d)
                n_diff += 1
                if len(kept) < report.MAX_DETAIL_ROWS:
                    kept.append(d)
            comparison.differences = []
            log.info("batch %d/%d: %d households checked, %d differences so far", b, n_batches, len(group), n_diff)

        if tracked:
            V.progress_checks(engine, models, checks, left_out)
        checks.add("Records", "every household could be read from farmer profile", 0, len(unreadable),
                   detail=", ".join(unreadable[:20]))
        both = V.existing_members(engine, models, twice)
        checks.add("Registry", "nobody is in a household of their own and in farmer profile's household too", 0, len(both),
                   detail=", ".join(both[:20]))
        for register in comparison.expected:
            n = comparison.expected[register]
            checks.add("Records", f"{register}: every record migrated", n, n - comparison.missing[register],
                       detail=f"{comparison.missing[register]} missing" if comparison.missing[register] else "")
        for entity, n in skipped.items():
            checks.add("Records", f"{entity}: not migrated by design (the migration's 'skipped' issues)", "-", n,
                       ok=True, detail="see the migration's issues.csv")
        bad_columns = [c for c in comparison.column_rows() if c["differ"]]
        checks.add("Values", "every migrated column holds the expected value",
                   sum(c["compared"] for c in comparison.column_rows()),
                   sum(c["compared"] - c["differ"] for c in comparison.column_rows()), ok=not bad_columns,
                   detail=("columns that differ: " + ", ".join(f"{c['register']}.{c['column']}" for c in bad_columns))[:500])
        direct.add_to(checks)

        with engine.connect() as tconn:
            if everything:
                n_src = len(chosen)
                not_compared = sum(len(left_out[k]) for k in ("CHANGED", "CONFLICT", "EDITED"))
                # records set inactive because farmer profile no longer has them are not expected
                inactive = (" AND internal_record_id NOT IN (SELECT gen2_id FROM migration.migrated_record "
                            "WHERE removed_run_id IS NOT NULL)") if current else ""
                for register, cls_ids in expected_ids.items():
                    cls = getattr(models, f"G2PRegister{register}")
                    n = tconn.execute(text(f"SELECT count(*) FROM {cls.__tablename__} WHERE created_by = :by{inactive}"),
                                      {"by": MIGRATED_BY}).scalar()
                    # the records of households not compared are not among the expected ones
                    checks.add("Records", f"{register}: no migrated records beyond farmer profile's", len(cls_ids), n,
                               warn_only=bool(not_compared),
                               detail=("the registry has migrated records farmer profile no longer has, still active"
                                       + (f", or of the {not_compared} households not compared"
                                          if not_compared else "")) if n > len(cls_ids) else "")
                log.info("%d farmers in scope in farmer profile", n_src)
            V.registry_checks(tconn, models, master, checks)
    finally:
        conn.close()
        diff_file.close()

    result = collections.Counter(c["result"] for c in checks.rows)
    info = collections.OrderedDict([
        ("Run", run_dir.name), ("Arguments", " ".join(argv) or "(every farmer in scope)"),
        ("Source", runlog._safe_dsn(os.environ.get("SOURCE_DSN", ""))),
        ("Target", runlog._safe_dsn(os.environ.get("TARGET_DSN", ""))),
        ("Farmers verified", len(chosen)), ("Values checked against", master.describe()), ("Duration (s)", round(time.monotonic() - started, 1)),
    ])
    try:
        health.save_verify(engine, checks.rows, everything)
    except Exception as exc:  # the checks themselves stand
        log.error("the results could not be saved for the health report: %s", str(exc).strip())
    report.verify_workbook(run_dir / "verify-report.xlsx", info, checks.rows, comparison.column_rows(), kept)
    (run_dir / "summary.json").write_text(json.dumps(
        {"info": info, "result": result, "differences": n_diff,
         "failed": [c for c in checks.rows if c["result"] == "FAIL"]}, indent=2, default=str), encoding="utf-8")
    files = ["verify.log", "summary.txt", "verify-report.xlsx", "differences.csv", "summary.json"]
    lines = text_summary.verification(info, checks.rows, comparison.column_rows(), n_diff, files)
    (run_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for line in lines:
        log.info("%s", line)
    return 1 if result["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
