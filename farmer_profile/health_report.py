"""health-report.xlsx, and the Health sheet of migration-report.xlsx. Counts only: see health.py."""
import collections

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from . import health as H

_FILLS = {H.GREEN: "D9EAD3", H.AMBER: "FFF2CC", H.RED: "F4CCCC", H.NOT_CHECKED: "EEEEEE"}
_HEAD = ["Metric", "Record", "Split by", "Value", "Count", "Out of", "%", "Target", "Blocks sign-off", "Result"]
_WIDTHS = [60, 18, 16, 46, 12, 12, 8, 12, 14, 14]
MEANING = [(H.GREEN, "as it should be"), (H.AMBER, "needs a look, or is not finished"),
           (H.RED, "blocks sign-off"), (H.NOT_CHECKED, "not measured yet: never counts as green"),
           (H.INFO, "a number to know, without a target")]


def _percent(m):
    return round(100 * m.count / m.total, 1) if m.total and m.count is not None else None


def _row(m):
    return [m.metric, m.record_type, m.split_by, m.split_value, m.count, m.total, _percent(m), m.target,
            "yes" if m.blocking else "", m.result]


def _colour(cell):
    if cell.value in _FILLS:
        cell.fill = PatternFill("solid", fgColor=_FILLS[cell.value])


def _table(ws, header, rows, widths, result_column=None):
    ws.append(header)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = Font(bold=True), PatternFill("solid", fgColor="DDE4EE")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in rows:
        ws.append(row)
        if result_column is not None:
            _colour(ws.cell(ws.max_row, result_column))
    from openpyxl.utils import get_column_letter
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def _taken(s):
    return f"{s['taken_at']:%Y-%m-%d %H:%M} ({s['taken_by']})"


def _overview(ws, data):
    measures = data["measures"]
    ws.append(["Health of the migration"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(["Last run", data["run_id"] or "-"])
    if data["history"]:
        ws.append(["Measured (database time)", _taken(data["history"][-1][0])])
    ws.append(["Overall", data["overall"]])
    _colour(ws.cell(ws.max_row, 2))
    ws.append([])
    rows = []
    for area in H.AREAS:
        mine = [m for m in measures if m.area == area]
        n = collections.Counter(m.result for m in mine)
        rows.append([area, H.worst(mine), n[H.RED], n[H.AMBER], n[H.NOT_CHECKED], n[H.GREEN]])
    _table(ws, ["Area", "Result", "Red", "Amber", "Not checked", "Green"], rows, [60, 18, 16, 16, 14, 12], 2)
    ws.append([])
    wrong = [m for m in measures if m.result in (H.RED, H.AMBER, H.NOT_CHECKED)]
    order = {H.RED: 0, H.NOT_CHECKED: 1, H.AMBER: 2}
    ws.append([f"Not green ({len(wrong)})"])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    _table(ws, ["Metric", "Area", "Record", "Value", "Count", "Out of", "Target", "Blocks sign-off", "Result"],
           [[m.metric, m.area, m.record_type, m.split_value, m.count, m.total, m.target, "yes" if m.blocking else "", m.result]
            for m in sorted(wrong, key=lambda m: order[m.result])], [60, 18, 16, 30, 12, 12, 12, 14, 14], 9)
    ws.append([])
    for result, meaning in MEANING:
        ws.append([result, meaning])
        _colour(ws.cell(ws.max_row, 1))


def _reconciliation(ws, measures):
    """A row per record type, a column per group: the groups add up to Gen1's records."""
    of = {(m.record_type, m.metric): m for m in measures if m.area == H.RECONCILIATION}
    groups = list(H.GROUPS.values())
    rows = []
    for kind in H.KINDS:
        total = of[(kind, "Gen1 records")].count
        counts = [of[(kind, g)].count for g in groups]
        scope = of[(kind, "In scope and loaded")]
        rows.append([kind, total, *counts, sum(counts) == total, scope.total, _percent(scope),
                     of[(kind, "Loaded, and no longer in Gen1")].count, of[(kind, H.MADE)].count,
                     H.worst([m for m in measures if m.area == H.RECONCILIATION and m.record_type == kind])])
    _table(ws, ["Record", "In Gen1", *groups, "Adds up", "In scope", "% of scope loaded", "Loaded, no longer in Gen1",
                "Made for lone farmers", "Result"],
           rows, [14, 10, 10, 14, 18, 18, 18, 12, 14, 10, 10, 12, 14, 14, 12], 8 + len(groups))
    ws.freeze_panes = "B2"


def _trend(ws, taken):
    if not taken:
        return
    keys = list(taken[-1][1])
    header = ["Area", "Metric", "Record", *[_taken(s) for s, _ in taken]]
    rows = [["", "Overall", "", *[s["overall"] for s, _ in taken]]]
    for key in keys:
        cells = []
        for _, measures in taken:
            count, total, result = measures.get(key, (None, None, None))
            cells.append(None if result is None else H.NOT_CHECKED if result == H.NOT_CHECKED
                         else f"{count} of {total}" if total is not None else count)
        rows.append([*key, *cells])
    _table(ws, header, rows, [16, 60, 18, *[24] * len(taken)])
    for cell in ws[2]:
        _colour(cell)
    ws.freeze_panes = "D2"


def workbook(path, data):
    wb = Workbook()
    ws = wb.active
    ws.title = "Overview"
    measures = data["measures"]
    _overview(ws, data)
    _reconciliation(wb.create_sheet("Reconciliation"), measures)
    for area in (H.RUNS, H.QUALITY, H.IDS):
        ws = wb.create_sheet(area)
        _table(ws, _HEAD, [_row(m) for m in measures if m.area == area], _WIDTHS, 10)
        ws.freeze_panes = "A2"
    ws = wb.create_sheet("By region, source and status")
    _table(ws, _HEAD, [_row(m) for m in measures if m.area == H.SPLITS], _WIDTHS, 10)
    ws.freeze_panes = "A2"
    _trend(wb.create_sheet("Trend"), data["history"])
    wb.save(path)


def add_sheet(wb, data, why_not):
    """The Health sheet, first in migration-report.xlsx: every metric. data: None when it was not
    measured, and why_not says why."""
    ws = wb.create_sheet("Health", 0)
    wb.active = 0
    ws.append(["Health of the migration"])
    ws["A1"].font = Font(bold=True, size=12)
    if data is None:
        ws.append([why_not])
        ws.column_dimensions["A"].width = 100
        return
    ws.append(["Overall", data["overall"]])
    _colour(ws.cell(2, 2))
    ws.append(["At the end of the load. After verify.py, run health.py: it fills in what is not checked yet."])
    ws.append([])
    _table(ws, ["Area", *_HEAD], [[m.area, *_row(m)] for area in (*H.AREAS, H.SPLITS) for m in data["measures"] if m.area == area],
           [18, *_WIDTHS], 11)


def lines(data) -> list[str]:
    """For the terminal and the log."""
    measures = data["measures"]
    out = [f"HEALTH: {data['overall']}   (last run {data['run_id'] or '-'})"]
    for area in H.AREAS:
        out.append(f"  {area:18}{H.worst([m for m in measures if m.area == area])}")
    wrong = [m for m in measures if m.result in (H.RED, H.AMBER, H.NOT_CHECKED)]
    for m in sorted(wrong, key=lambda m: (m.result != H.RED, m.result != H.NOT_CHECKED))[:30]:
        what = " ".join(x for x in (m.metric, f"[{m.record_type}]" if m.record_type else "", m.split_value) if x)
        number = "" if m.count is None else f": {m.count}" + (f" of {m.total}" if m.total is not None else "")
        out.append(f"    {m.result:12}{what}{number}")
    if len(wrong) > 30:
        out.append(f"    ... {len(wrong) - 30} more in the workbook")
    return out
