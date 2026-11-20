"""The Excel workbooks: the migration report (written at the end of every run)
and the verification report."""
import collections

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import fieldmap as F

# Excel holds about a million rows; the CSV next to the workbook has every issue
MAX_DETAIL_ROWS = 100_000

_BOLD = Font(bold=True)
_HEAD = PatternFill("solid", fgColor="DDE4EE")
_FILLS = {
    # farmer profile side
    F.MIGRATED: "D9EAD3", F.RECOMPUTED: "D9EAD3", F.NOT_YET: "FFF2CC", F.NO_COLUMN: "F4CCCC",
    F.WORKFLOW: "EEEEEE", F.TECHNICAL: "EEEEEE", F.UNREVIEWED: "F9CB9C",
    # Gen2 side
    F.FILLED: "D9EAD3", F.DERIVED: "D9EAD3", F.AFTER: "CFE2F3", F.REGISTRY: "D9EAD3", F.ABSENT: "EEEEEE",
    # verification
    "PASS": "D9EAD3", "FAIL": "F4CCCC", "WARN": "FFF2CC",
}


def _sheet(wb, title, header, rows, widths=None, status_col=None):
    ws = wb.create_sheet(title)
    ws.append(header)
    for cell in ws[1]:
        cell.font, cell.fill = _BOLD, _HEAD
    for row in rows:
        ws.append([_cell(v) for v in row])
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    for i, width in enumerate(widths or [], start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    if status_col is not None:
        for r in range(2, ws.max_row + 1):
            cell = ws.cell(r, status_col + 1)
            colour = _FILLS.get(cell.value)
            if colour:
                cell.fill = PatternFill("solid", fgColor=colour)
    return ws


def _cell(v):
    if isinstance(v, (list, tuple, set, dict)):
        return str(v)
    if hasattr(v, "tzinfo") and getattr(v, "tzinfo", None) is not None:
        return v.replace(tzinfo=None)
    return v


def _pairs(ws, rows, start=1):
    """Write label/value rows into the summary sheet."""
    r = start
    for row in rows:
        if row is None:
            r += 1
            continue
        for c, v in enumerate(row, start=1):
            cell = ws.cell(r, c, _cell(v))
            if c == 1 and len(row) == 1:
                cell.font = Font(bold=True, size=12)
        r += 1
    return r


def _status_table(entries, key, statuses, value_key):
    """Per status: fields, and of them how many hold any data."""
    count, with_data = collections.Counter(), collections.Counter()
    for e in entries:
        count[e[key]] += 1
        if (e.get(value_key) or 0) > 0:
            with_data[e[key]] += 1
    return [(s, count[s], with_data[s]) for s in statuses if count[s] or s in statuses]


def migration_workbook(path, run: dict, source_fields: list, target_cols: list, issues: list, issue_counts, batches: list):
    """issues: the first rows; issue_counts: (severity, record, field, reason) -> count, over all of them."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width = 44
    for col in "BCDE":
        ws.column_dimensions[col].width = 18

    rows = [("Farmer profile to Farmer registry: migration report",), None]
    rows += [(k, v) for k, v in run["info"].items()]
    rows += [None, ("Records",), ("Gen2 register", "Rows read", "Added", "Already there")]
    rows += [(t, c["rows"], c["added"], c["already there"]) for t, c in run["counts"].items()]
    rows += [None, ("Farmer profile fields (what happened to each)",), ("Status", "Fields", "Fields holding data")]
    rows += _status_table(source_fields, "status", F.SOURCE_STATUSES, "rows_with_value")
    rows += [("Total", len(source_fields), sum(1 for e in source_fields if (e["rows_with_value"] or 0) > 0))]
    rows += [None, ("Gen2 columns (where each comes from)",), ("Status", "Columns", "Columns filled")]
    rows += _status_table(target_cols, "status", F.TARGET_STATUSES, "rows_with_value")
    rows += [("Total", len(target_cols), sum(1 for e in target_cols if (e["rows_with_value"] or 0) > 0))]
    rows += [None, ("Generated after the load",), ("What", "Where", "Queued now")]
    queued = run.get("after_load", {})
    for what, where, how in F.AFTER_LOAD:
        if "functional" in what.lower():
            n = sum(v for k, v in queued.items() if "functional ids" in k)
        elif "completion" in what.lower():
            n = sum(v for k, v in queued.items() if "completion scores" in k)
        else:
            n = "-"
        rows.append((what, where, n if queued else "not run", how))
    rows += [None, ("Issues",), ("Severity", "Count")]
    by_severity = collections.Counter()
    for (severity, *_), n in issue_counts.items():
        by_severity[severity] += n
    rows += [(s, by_severity[s]) for s in ("skipped", "dropped", "check")]
    rows += [None, ("Statuses",)]
    rows += [(F.MIGRATED, "the value is carried to a Gen2 column"),
             (F.RECOMPUTED, "Gen2 computes it again from migrated data"),
             (F.NOT_YET, "Gen2 has a column for it; this migration does not write it yet"),
             (F.NO_COLUMN, "cannot be added: Gen2 has nowhere to put it"),
             (F.WORKFLOW, "the old system's review, change-request, consent or sharing state"),
             (F.TECHNICAL, "Odoo bookkeeping, not farmer data"),
             (F.UNREVIEWED, "a field the field map does not know: review it"),
             (F.FILLED, "a Gen2 column filled from a farmer profile field"),
             (F.DERIVED, "a Gen2 column the migration computes"),
             (F.AFTER, "generated by the registry's workers after the load"),
             (F.REGISTRY, "set by the registry when the row is written"),
             (F.ABSENT, "farmer profile has no data for it: stays empty"),
             ("Fields holding data", "of the records in this run: booleans count when true")]
    _pairs(ws, rows)

    _sheet(wb, "Farmer profile fields",
           ["Model", "Field", "Label", "Type", "Odoo module", "Status", "Gen2 column(s)", "How",
            "Records in scope", "Records with a value"],
           [(e["model"], e["field"], e["label"], e["type"], e["module"], e["status"], e["gen2"], e["how"],
             e["rows_in_scope"], e["rows_with_value"]) for e in source_fields],
           widths=[22, 30, 30, 12, 22, 24, 44, 60, 12, 12], status_col=5)
    _sheet(wb, "Gen2 columns",
           ["Register", "Table", "Column", "Status", "From farmer profile", "How", "Migrated records",
            "Records with a value"],
           [(e["register"], e["table"], e["column"], e["status"], e["farmer_profile"], e["how"],
             e["migrated_rows"], e["rows_with_value"]) for e in target_cols],
           widths=[18, 30, 30, 26, 50, 60, 12, 12], status_col=3)

    _sheet(wb, "Issues summary", ["Severity", "Record", "Field", "Reason", "Count"],
           [(*k, n) for k, n in sorted(issue_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
           widths=[10, 18, 30, 80, 10])
    _sheet(wb, "Issues", ["Severity", "Record", "Odoo id", "Field", "Value", "Reason"],
           [(i["severity"], i["entity"], i["odoo_id"], i["field"], i["value"], i["reason"])
            for i in issues[:MAX_DETAIL_ROWS]], widths=[10, 18, 12, 30, 40, 80])
    total = sum(issue_counts.values())
    if total > len(issues):
        wb["Issues"].append([f"... {total - len(issues)} more in issues.csv"])
    _sheet(wb, "Batches", ["Batch", "Farmers", "First Odoo id", "Last Odoo id", "Seconds", "Result", "Added"],
           [(b["batch"], b["farmers"], b["first"], b["last"], b["seconds"], b["result"], b["added"]) for b in batches],
           widths=[8, 10, 14, 14, 10, 40, 80])
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(min_row=1, max_row=1):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


def verify_workbook(path, info: dict, checks: list, columns: list, mismatches: list):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 40
    result = collections.Counter(c["result"] for c in checks)
    rows = [("Farmer profile to Farmer registry: verification",), None]
    rows += [(k, v) for k, v in info.items()]
    rows += [None, ("Result",), ("Checks passed", result["PASS"]), ("Checks failed", result["FAIL"]),
             ("Warnings", result["WARN"]),
             ("Columns compared", len(columns)),
             ("Values compared", sum(c["compared"] for c in columns)),
             ("Values that differ", sum(c["differ"] for c in columns)),
             None, ("Verdict", "PASS" if not result["FAIL"] else "FAIL")]
    _pairs(ws, rows)
    _sheet(wb, "Checks", ["Group", "Check", "Expected", "Found", "Result", "Detail"],
           [(c["group"], c["check"], c["expected"], c["found"], c["result"], c["detail"]) for c in checks],
           widths=[16, 60, 14, 14, 8, 80], status_col=4)
    _sheet(wb, "Columns", ["Register", "Column", "Compared", "Same", "Differ", "Result", "Example"],
           [(c["register"], c["column"], c["compared"], c["compared"] - c["differ"], c["differ"],
             "PASS" if not c["differ"] else "FAIL", c["example"]) for c in columns],
           widths=[18, 30, 12, 12, 10, 8, 80], status_col=5)
    _sheet(wb, "Differences", ["Register", "Record id", "Odoo id", "Column", "Expected", "In Gen2"],
           [(m["register"], m["record_id"], m["odoo_id"], m["column"], m["expected"], m["found"])
            for m in mismatches[:MAX_DETAIL_ROWS]], widths=[18, 38, 12, 30, 50, 50])
    wb.save(path)
