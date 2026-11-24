"""The plain-text summary a run prints at its end and saves as summary.txt."""
import collections

from . import fieldmap as F

_SOURCE_LABELS = {
    F.MIGRATED: "Went to Gen2",
    F.RECOMPUTED: "Recomputed by Gen2",
    F.NOT_YET: "Gen2 has a column, not migrated yet",
    F.NO_COLUMN: "No Gen2 column: cannot be added",
    F.WORKFLOW: "Old Odoo workflow: not carried",
    F.TECHNICAL: "Odoo technical",
    F.UNREVIEWED: "Not reviewed (add to fieldmap.py)",
}
_TARGET_LABELS = {
    F.FILLED: "Filled from farmer profile",
    F.DERIVED: "Computed by the migration",
    F.REGISTRY: "Set by the registry on insert",
    F.AFTER: "Generated after the load",
    F.T_NOT_YET: "Not migrated yet",
    F.ABSENT: "Not in farmer profile: stays empty",
}
# Items listed by name in the "data not migrated" section
MAX_LISTED = 15


def _has(n):
    return (n or 0) > 0


def mapping_exceptions(source_fields: list) -> list:
    """Farmer profile fields holding data that does not reach Gen2, or that nobody has mapped."""
    lost = [f for f in source_fields if f["status"] in (F.NOT_YET, F.NO_COLUMN, F.UNREVIEWED) and _has(f["rows_with_value"])]
    order = {s: i for i, s in enumerate((F.UNREVIEWED, F.NOT_YET, F.NO_COLUMN))}
    return sorted(lost, key=lambda f: (order[f["status"]], -(f["rows_with_value"] or 0)))


def _overall(totals: dict) -> list[str]:
    out = [f"{'Households, over all runs':34}{'households':>12}{'farmers':>10}"]
    for status, label in (("LOADED", "in the registry"), ("FAILED", "failed, not in the registry"),
                          ("CHANGED", "in; changed in farmer profile")):
        n, farmers = totals["households"].get(status, (0, 0))
        out.append(f"  {label:32}{n:>12}{farmers:>10}")
    issues = ", ".join(f"{s} {totals['open'][s]}" for s in ("failed", "changed", "skipped", "dropped", "check")
                       if totals["open"].get(s)) or "none"
    out.append(f"  Open issues: {issues}; resolved: {totals['resolved']}")
    return out


def status(totals: dict, runs: list) -> list[str]:
    """migrate.py --status"""
    out = _overall(totals) + ["", "Latest runs"]
    for r in runs:
        counts = r["counts"] or {}
        did = ", ".join(f"{k} {v}" for k, v in counts.items() if isinstance(v, int) and v)
        out.append(f"  {r['run_id']:28}{r['mode']:10}{r['status']:24}{did}")
        if r["error"]:
            out.append(f"      {r['error'][:200]}")
    if any(r["status"] == "RUNNING" for r in runs):
        out.append("  (RUNNING: still going, or killed; the next run tells, and takes over from a killed one)")
    return out


def migration(info: dict, data: dict, source_fields: list, target_cols: list, issue_counts: collections.Counter,
              files: list, dry_run=False, sql_out=False, finalized=True, error=None) -> list[str]:
    out = []
    add = out.append
    households, totals, failed = data["households"], data["counts"], data["failed"]
    title = "MIGRATION SUMMARY: " + info["Status"] + (
        "  (DRY RUN: every batch rolled back, nothing kept)" if dry_run else
        "  (SQL FILE: nothing written; run migration.sql to load)" if sql_out else "")
    add("=" * 78)
    add(title)
    add("=" * 78)
    add(f"Run {info['Run']}, {info['Duration (s)']} s, arguments: {info['Arguments']}")
    add(f"Codes and locations checked against {info.get('Values checked against', '-')}")
    if error:
        add(f"STOPPED BEFORE THE END: {error}")
        add("Run the same command again: what is in is skipped, the rest is migrated.")
    add("")

    add(f"Households in this run: {households['planned']} planned")
    for word, n in households.items():
        if word not in ("planned", "records added", "remaining") and n:
            add(f"  {word:32}{n:>12}")
    add(f"  {'remaining':32}{households['remaining']:>12}")
    add("")
    if data["overall"]:
        out.extend(_overall(data["overall"]))
        add("")

    add(f"{'Records':34}{'read':>10}{'added':>10}{'already there':>15}")
    for table, c in totals.items():
        add(f"  {table.replace('g2p_register_', ''):32}{c['rows']:>10}{c['added']:>10}{c['already there']:>15}")
    if dry_run or sql_out:
        add("  ('added' is what loading would add)")
    add("")

    if failed:
        add(f"Failed households ({len(failed)}): left out, nothing of them is in the registry")
        for h in failed[:MAX_LISTED]:
            farmers = ", ".join(map(str, h["farmer_ids"] or []))
            add(f"  {h['household_key']} (farmers {farmers[:60]}): {h['error_class']}: {(h['error'] or '').splitlines()[0][:160]}")
        if len(failed) > MAX_LISTED:
            add(f"  ... {len(failed) - MAX_LISTED} more in migration-report.xlsx")
        add("  Fix them in farmer profile and run the same command again.")
        add("")
    if data["changed"]:
        add(f"Changed in farmer profile since they were migrated ({len(data['changed'])}): not touched; correct them in "
            "the registry")
        for h in data["changed"][:MAX_LISTED]:
            add(f"  {h['household_key']}: {h['what']}")
        if len(data["changed"]) > MAX_LISTED:
            add(f"  ... {len(data['changed']) - MAX_LISTED} more in migration-report.xlsx")
        add("")

    add("Generated after the load")
    if error:
        add("  not queued: the run stopped before its end (the run that finishes queues them)")
    elif sql_out:
        add("  in migration.sql, after the inserts" if finalized else "  not in migration.sql: --no-finalize")
    elif dry_run:
        add("  not queued: dry run")
    elif not finalized:
        add("  not queued: --no-finalize")
    elif not data["after_load"]:
        add("  nothing to queue: the registry asks for no ids or scores")
    else:
        for key, n in data["after_load"].items():
            add(f"  {key}: {n}")
    add("  Record history: not written (a migrated record's history starts empty)")
    add("")

    for label, entries, statuses, labels, extra in (
            ("Farmer profile fields", source_fields, F.SOURCE_STATUSES, _SOURCE_LABELS, "holding data"),
            ("Gen2 columns", target_cols, F.TARGET_STATUSES, _TARGET_LABELS, "filled")):
        add(f"{f'{label} ({len(entries)})':44}{'':>8}{extra:>16}")
        count, filled = collections.Counter(), collections.Counter()
        for e in entries:
            count[e["status"]] += 1
            filled[e["status"]] += _has(e["rows_with_value"])
        for s in statuses:
            add(f"  {labels[s]:42}{count[s]:>8}{filled[s]:>16}")
    if dry_run or sql_out:
        add("  (counted in the finished rows of this run)")
    add("")

    lost = mapping_exceptions(source_fields)
    add(f"Farmer profile data not in Gen2 after this run ({len(lost)} fields holding data)")
    for s in (F.UNREVIEWED, F.NOT_YET, F.NO_COLUMN):
        mine = [f for f in lost if f["status"] == s]
        if not mine:
            continue
        add(f"  {_SOURCE_LABELS[s]}:")
        for f in mine[:MAX_LISTED]:
            add(f"    {f['model'] + '.' + f['field']:52}{f['rows_with_value']:>8} of {f['rows_in_scope']}")
        if len(mine) > MAX_LISTED:
            add(f"    ... {len(mine) - MAX_LISTED} more in migration-report.xlsx")
    add("")

    by_severity = collections.Counter()
    for (severity, *_), n in issue_counts.items():
        by_severity[severity] += n
    add(f"{'Open issues, over all runs' if data['overall'] else 'Issues'}: {sum(by_severity.values())} "
        f"(failed {by_severity['failed']}: household left out; changed {by_severity['changed']}: not touched; "
        f"skipped {by_severity['skipped']}: record not migrated; dropped {by_severity['dropped']}: value left out; "
        f"check {by_severity['check']}: migrated, worth a look)")
    for (severity, entity, field, reason), n in issue_counts.most_common(MAX_LISTED):
        add(f"  {n:>7}  {severity:8} {entity}.{field}: {reason.splitlines()[0][:160] if reason else ''}")
    if len(issue_counts) > MAX_LISTED:
        add(f"  ... {len(issue_counts) - MAX_LISTED} more kinds in migration-report.xlsx")
    add("")

    if sql_out and not error:
        add("Load it:  psql -v ON_ERROR_STOP=1 -f " + info["Run"] + "/migration.sql <registry database>")
        add("          (locally: ./run.sh apply)")
        add("Then run verify.py.")
        add("")
    add("Files in " + info["Run"] + ": " + ", ".join(files))
    add("=" * 78)
    return out


def verification(info: dict, checks: list, columns: list, n_diff: int, files: list) -> list[str]:
    out = []
    add = out.append
    result = collections.Counter(c["result"] for c in checks)
    add("=" * 78)
    add(f"VERIFICATION SUMMARY: {'FAIL' if result['FAIL'] else 'PASS'}")
    add("=" * 78)
    add(f"Run {info['Run']}, {info['Duration (s)']} s, {info['Farmers verified']} farmers, "
        f"arguments: {info['Arguments']}")
    add(f"Codes and locations checked against {info.get('Values checked against', '-')}")
    add(f"Checks: {result['PASS']} passed, {result['FAIL']} failed, {result['WARN']} warnings")
    add(f"Values compared: {sum(c['compared'] for c in columns)} in {len(columns)} columns; {n_diff} differ")
    add("")
    groups = collections.OrderedDict()
    for c in checks:
        groups.setdefault(c["group"], collections.Counter())[c["result"]] += 1
    add(f"{'Group':28}{'pass':>8}{'fail':>8}{'warn':>8}")
    for group, n in groups.items():
        add(f"  {group:26}{n['PASS']:>8}{n['FAIL']:>8}{n['WARN']:>8}")
    add("")
    problems = [c for c in checks if c["result"] != "PASS"]
    if problems:
        add("Not passed:")
        for c in problems:
            add(f"  {c['result']}  [{c['group']}] {c['check']}: expected {c['expected']}, found {c['found']}")
            if c["detail"]:
                add(f"        {c['detail']}")
        add("")
    add("Files in " + info["Run"] + ": " + ", ".join(files))
    add("=" * 78)
    return out
