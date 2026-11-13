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


def migration(info: dict, totals: dict, source_fields: list, target_cols: list, after_load: dict,
              issue_counts: collections.Counter, failed: list, dry_run: bool, files: list) -> list[str]:
    out = []
    add = out.append
    title = "MIGRATION SUMMARY" + ("  (DRY RUN: every batch rolled back, nothing kept)" if dry_run else "")
    add("=" * 78)
    add(title)
    add("=" * 78)
    add(f"Run {info['Run']}, {info['Duration (s)']} s, arguments: {info['Arguments']}")
    add(f"Codes and locations checked against {info.get('Values checked against', '-')}")
    add(f"Farmers: {info['Farmers chosen']} chosen, {info['Farmers read (with household members)']} read with "
        f"their household members; {info['Batches']} batches, {len(failed)} failed")
    add("")

    add(f"{'Records':34}{'read':>10}{'added':>10}{'already there':>15}")
    for table, c in totals.items():
        add(f"  {table.replace('g2p_register_', ''):32}{c['rows']:>10}{c['added']:>10}{c['already there']:>15}")
    if dry_run:
        add("  (dry run: 'added' is what a real run would add)")
    add("")

    add(f"{f'Farmer profile fields ({len(source_fields)})':44}{'fields':>8}{'holding data':>16}")
    count, data = collections.Counter(), collections.Counter()
    for f in source_fields:
        count[f["status"]] += 1
        data[f["status"]] += _has(f["rows_with_value"])
    for status in F.SOURCE_STATUSES:
        add(f"  {_SOURCE_LABELS[status]:42}{count[status]:>8}{data[status]:>16}")
    add("")

    add(f"{f'Gen2 columns ({len(target_cols)})':44}{'columns':>8}{'filled':>16}")
    count, data = collections.Counter(), collections.Counter()
    for c in target_cols:
        count[c["status"]] += 1
        data[c["status"]] += _has(c["rows_with_value"])
    for status in F.TARGET_STATUSES:
        add(f"  {_TARGET_LABELS[status]:42}{count[status]:>8}{data[status]:>16}")
    if dry_run:
        add("  (dry run: counted in the rows the run would write; registry-set columns not counted)")
    add("")

    add("Generated after the load")
    if dry_run:
        add("  not queued: dry run")
    elif failed:
        add("  not queued: a batch failed (rerun the same command)")
    elif not after_load:
        add("  not queued: --no-finalize")
    else:
        for key, n in after_load.items():
            add(f"  {key}: {n}")
    add("  Record history: not written (a migrated record's history starts empty)")
    add("")

    lost = [f for f in source_fields if f["status"] in (F.NOT_YET, F.NO_COLUMN, F.UNREVIEWED)
            and _has(f["rows_with_value"])]
    add(f"Farmer profile data not in Gen2 after this run ({len(lost)} fields holding data)")
    for status in (F.UNREVIEWED, F.NOT_YET, F.NO_COLUMN):
        mine = sorted((f for f in lost if f["status"] == status), key=lambda f: -(f["rows_with_value"] or 0))
        if not mine:
            continue
        add(f"  {_SOURCE_LABELS[status]}:")
        for f in mine[:MAX_LISTED]:
            add(f"    {f['model'] + '.' + f['field']:52}{f['rows_with_value']:>8} of {f['rows_in_scope']}")
        if len(mine) > MAX_LISTED:
            add(f"    ... {len(mine) - MAX_LISTED} more in migration-report.xlsx")
    add("")

    by_severity = collections.Counter()
    for (severity, *_), n in issue_counts.items():
        by_severity[severity] += n
    add(f"Issues: {sum(by_severity.values())} (skipped {by_severity['skipped']}: record not migrated; "
        f"dropped {by_severity['dropped']}: value left out; check {by_severity['check']}: migrated, worth a look)")
    for (severity, entity, field, reason), n in issue_counts.most_common(MAX_LISTED):
        add(f"  {n:>7}  {severity:8} {entity}.{field}: {reason}")
    if len(issue_counts) > MAX_LISTED:
        add(f"  ... {len(issue_counts) - MAX_LISTED} more kinds in migration-report.xlsx")
    add("")

    for b, ids, exc in failed:
        add(f"FAILED batch {b} (Odoo ids {ids[0]}..{ids[-1]}): {exc}")
    if failed:
        add("Rerun the same command: finished batches are skipped, failed ones retried.")
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
