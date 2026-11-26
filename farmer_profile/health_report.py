"""health-report.xlsx, and the Health sheet of migration-report.xlsx. Counts only: see health.py."""
import collections

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import health as H
from .health_guide import AREA, CHECKS, GUIDE, WORDS

_FILLS = {H.GREEN: "D9EAD3", H.AMBER: "FFF2CC", H.RED: "F4CCCC", H.NOT_CHECKED: "EEEEEE"}
_ORDER = {H.RED: 0, H.NOT_CHECKED: 1, H.AMBER: 2, H.INFO: 3, H.GREEN: 4}
_HEAD = ["Result", "Metric", "Record", "Split by", "Value", "Count", "Out of", "%", "Target", "Blocks sign-off"]
_WIDTHS = [14, 60, 14, 16, 46, 10, 10, 8, 10, 12]
MEANING = [(H.GREEN, "As it should be"), (H.AMBER, "Needs a look, or is not finished"),
           (H.RED, "Blocks sign-off"), (H.NOT_CHECKED, "Not measured yet: never counts as green"),
           (H.INFO, "A number to know, without a target")]
SHEETS = [("Overview", "Start here. Shows the overall result and everything that is not green."),
          ("Reconciliation", "Shows what happened to every Gen1 record: how many were loaded, failed, were left out, and so on. In each row, these counts add up to column C, In Gen1, which is how many there are in Gen1."),
          ("Run health", "Shows whether the loads finished and what failed, whether farmers and households have their ID numbers (FR-... and HH-...), and whether Gen2 has calculated the farmers' completion scores."),
          ("Quality", "Shows whether the values in Gen1 are now in Gen2, what was left out and why, and whether records are linked correctly."),
          ("IDs", "Shows whether every record can be traced back to Gen1."),
          ("By region, source and status", "Shows whether any region, import source or Gen1 status has many farmers missing. Use it to find a problem that affects one group only."),
          ("Trend", "Compares these results with earlier ones, for example from rehearsals."),
          ("Guide", "Explains the sheets, the colours and every metric.")]


def _percent(m):
    return round(100 * m.count / m.total, 1) if m.total and m.count is not None else None


def _row(m):
    return [m.result, m.metric, m.record_type, m.split_by, m.split_value, m.count, m.total, _percent(m), m.target,
            "yes" if m.blocking else ""]


def _first(m):
    """What needs attention first; then what is furthest from all; then as measured."""
    return _ORDER[m.result], (_percent(m) if m.metric == "Values that arrived" and _percent(m) is not None else 100)


def _colour(cell):
    if cell.value in _FILLS:
        cell.fill = PatternFill("solid", fgColor=_FILLS[cell.value])


def _wrapped(ws, columns):
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=cell.column in columns, vertical="top")


def _table(ws, header, rows, widths, result_column=None) -> list[int]:
    """The rows' numbers."""
    ws.append(header)
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = Font(bold=True), PatternFill("solid", fgColor="DDE4EE")
    numbers = []
    for row in rows:
        ws.append(row)
        numbers.append(ws.max_row)
        if result_column is not None:
            _colour(ws.cell(ws.max_row, result_column))
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    return numbers


def _taken(s):
    return f"{s['taken_at']:%Y-%m-%d %H:%M} ({s['taken_by']})"


def _verify_line(data):
    if data.get("verify") is None:
        return "verify has not run over everything since the last load: run it, then health again"
    failed, checks = data["verify"]
    if not failed:
        return f"verify passed ({checks} checks)"
    return (f"verify failed: {failed} of {checks} checks. It fails on anything that is missing, also when the reason is "
            "recorded. This report asks whether it is explained. See verify-report.xlsx, sheet Checks")


def _overview(ws, data, where):
    measures = data["measures"]
    ws.append(["Health of the migration"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Overall", data["overall"]])
    ws["A2"].font = Font(bold=True, size=12)
    _colour(ws["B2"])
    ws.append(["Last load", data["run_id"] or "-"])
    if data["history"]:
        ws.append(["Measured (database time)", _taken(data["history"][-1][0])])
    ws.append(["Comparison of values (verify)", _verify_line(data)])
    ws.append([])
    rows = []
    for area in H.AREAS:
        mine = [m for m in measures if m.area == area]
        n = collections.Counter(m.result for m in mine)
        colours = [n[H.RED], n[H.AMBER], n[H.NOT_CHECKED], n[H.GREEN]]
        rows.append([area, H.worst(mine), *colours, sum(colours)])
    rows.append(["Total", data["overall"], *(sum(r[i] for r in rows) for i in range(2, 7))])
    ws.append(["How many checks of each area have each result (checks, not records)"])
    for number, row in zip(_table(ws, ["Area", "Result", "Red", "Amber", "Not checked", "Green", "Checks"], rows, []), rows):
        _colour(ws.cell(number, 2))
        if row[0] == "Total":
            for cell in ws[number]:
                cell.font = Font(bold=True)
            continue
        ws.cell(number, 1).hyperlink = f"#'{row[0]}'!A1"
        ws.cell(number, 1).font = Font(color="0563C1", underline="single")
    ws.append([])
    wrong = sorted((m for m in measures if m.result in (H.RED, H.AMBER, H.NOT_CHECKED)), key=lambda m: _ORDER[m.result])
    ws.append([f"What is not green ({len(wrong)})" if wrong else "Everything with a target is green"])
    ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
    if wrong:
        numbers = _table(ws, ["Metric", "Result", "Record", "Count", "Out of", "Blocks sign-off", "Where", "What it means",
                              "What to do"],
                         [[m.metric, m.result, m.record_type, m.count, m.total, "yes" if m.blocking else "", "",
                           *GUIDE.get(m.metric, ("", ""))] for m in wrong], [])
        for number, m in zip(numbers, wrong):
            _colour(ws.cell(number, 2))
            sheet, cell = where[id(m)]
            link = ws.cell(number, 7)
            link.value = f"{sheet}, {cell}"
            link.hyperlink = f"#'{sheet}'!{cell}"
            link.font = Font(color="0563C1", underline="single")
    ws.append([])
    for result, meaning in MEANING:
        ws.append([result, meaning])
        _colour(ws.cell(ws.max_row, 1))
    ws.append([])
    ws.append(["Counts only. Which farmer it is: migration-report.xlsx, sheets Failed households, Conflicts, Updated, "
               "Set inactive and Issues"])
    for column, width in zip("ABCDEFGHI", (52, 16, 12, 10, 12, 14, 24, 60, 60)):
        ws.column_dimensions[column].width = width
    _wrapped(ws, {8, 9})


# The columns after the groups: records that are not among Gen1's any more, and records Gen1 never had
_AFTER = ["Deleted from Gen1 since, set inactive", "Deleted from Gen1 since, still active", H.MADE]


def _reconciliation(ws, measures, where):
    """A row per record type, a column per group: the groups add up to Gen1's records."""
    of = {(m.record_type, m.metric): m for m in measures if m.area == H.RECONCILIATION}
    groups = list(H.GROUPS.values())
    rows = []
    for kind in H.KINDS:
        total = of[(kind, "In Gen1")].count
        counts = [of[(kind, g)].count for g in groups]
        scope = of[(kind, "Loaded, of what should be")]
        rows.append([kind, H.worst([m for m in measures if m.area == H.RECONCILIATION and m.record_type == kind]), total,
                     *counts, "yes" if sum(counts) == total else "NO", scope.total, _percent(scope),
                     *(of[(kind, metric)].count for metric in _AFTER)])
    header = ["Record", "Result", "In Gen1", *groups, "Adds up", "Should be loaded", "Loaded, of what should be", *_AFTER]
    numbers = _table(ws, header, rows, [14, 12, 10, *([12] * len(groups)), 10, 12, 14, 16, 16, 14], 2)
    for number in numbers:
        ws.cell(number, 6 + len(groups)).number_format = '0.0"%"'

    column = {**{g: get_column_letter(4 + i) for i, g in enumerate(groups)}, "In Gen1": "C",
              "Loaded, of what should be": get_column_letter(6 + len(groups)),
              **{metric: get_column_letter(7 + len(groups) + i) for i, metric in enumerate(_AFTER)}}
    for kind, number in zip(H.KINDS, numbers):
        for metric, letter in column.items():
            m = of[(kind, metric)]
            where[id(m)] = ("Reconciliation", f"{letter}{number}")
            if m.result in (H.RED, H.AMBER):
                ws[f"{letter}{number}"].fill = PatternFill("solid", fgColor=_FILLS[m.result])
    ws.append([])
    reasons = [m for m in measures if m.metric == "Out of scope, by reason"]
    ws.append(["Out of scope, by reason" if reasons else "Nothing is out of scope"])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for m in reasons:
        ws.append([m.record_type, None, m.count, m.split_value])
        where[id(m)] = ("Reconciliation", f"C{ws.max_row}")
    ws.append(["Draft, rejected and disabled farmers are in scope: they are migrated"])
    _wrapped(ws, set(range(1, 20)))
    for row in ws.iter_rows(min_row=len(rows) + 2):  # the lines below the table run on
        for cell in row:
            cell.alignment = Alignment(wrap_text=False)
    ws.freeze_panes = "C2"


def _metrics(ws, name, measures, where):
    measures = sorted(measures, key=_first)
    for number, m in zip(_table(ws, _HEAD, [_row(m) for m in measures], _WIDTHS, 1), measures):
        where[id(m)] = (name, f"F{number}")
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def _trend(ws, taken):
    if not taken:
        return
    header = ["Area", "Metric", "Record", *[_taken(s) for s, _ in taken]]
    rows = [["", "Overall", "", *[s["overall"] for s, _ in taken]]]
    for key in taken[-1][1]:
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


def _guide(ws):
    ws.append(["How to read this workbook"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([])
    _table(ws, ["Sheet", "What is in it"], SHEETS, [])
    ws.append([])
    for number in _table(ws, ["Result", "Meaning"], MEANING, []):
        _colour(ws.cell(number, 1))
    ws.append([])
    _table(ws, ["Word", "What it means here"], WORDS, [])
    ws.append([])
    rows = [[metric, AREA[metric], *(lambda c: (c[0], "yes" if c[1] else ""))(CHECKS.get(metric, ("none", False))), meaning, todo]
            for metric, (meaning, todo) in GUIDE.items()]
    _table(ws, ["Metric", "Sheet", "Target", "Blocks sign-off", "What it means", "What to do when it is not green"], rows, [])
    for column, width in zip("ABCDEF", (56, 28, 10, 14, 80, 70)):
        ws.column_dimensions[column].width = width
    _wrapped(ws, {1, 5, 6})


def workbook(path, data):
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    measures, where = data["measures"], {}
    _reconciliation(wb.create_sheet("Reconciliation"), measures, where)
    for area in (H.RUNS, H.QUALITY, H.IDS):
        _metrics(wb.create_sheet(area), area, [m for m in measures if m.area == area], where)
    name = "By region, source and status"
    _metrics(wb.create_sheet(name), name, [m for m in measures if m.area == H.SPLITS], where)
    _trend(wb.create_sheet("Trend"), data["history"])
    _guide(wb.create_sheet("Guide"))
    _overview(overview, data, where)
    wb.save(path)


def add_sheet(wb, data, why_not):
    """The Health sheet, first in migration-report.xlsx: every metric. data: None when it was not
    measured, and why_not says why."""
    ws = wb.create_sheet("Health", 0)
    wb.active = 0
    ws.append(["Health of the migration"])
    ws["A1"].font = Font(bold=True, size=14)
    if data is None:
        ws.append([why_not])
        ws.column_dimensions["A"].width = 100
        return
    ws.append(["Overall", data["overall"]])
    _colour(ws.cell(2, 2))
    ws.append(["At the end of the load. After verify, run health: it fills in what is not checked yet, and health-report.xlsx "
               "has a Guide"])
    ws.append([])
    rows = [[area, *_row(m), *GUIDE.get(m.metric, ("", ""))] for area in (*H.AREAS, H.SPLITS)
            for m in sorted((m for m in data["measures"] if m.area == area), key=_first)]
    _table(ws, ["Area", *_HEAD, "What it means", "What to do"], rows, [18, *_WIDTHS, 70, 70], 2)
    ws.freeze_panes = "A6"


def lines(data) -> list[str]:
    """For the terminal and the log."""
    measures = data["measures"]
    out = [f"HEALTH: {data['overall']}   (last run {data['run_id'] or '-'})"]
    for area in H.AREAS:
        out.append(f"  {area:18}{H.worst([m for m in measures if m.area == area])}")
    wrong = sorted((m for m in measures if m.result in (H.RED, H.AMBER, H.NOT_CHECKED)), key=lambda m: _ORDER[m.result])
    for m in wrong[:30]:
        what = " ".join(x for x in (m.metric, f"[{m.record_type}]" if m.record_type else "", m.split_value) if x)
        number = "" if m.count is None else f": {m.count}" + (f" of {m.total}" if m.total is not None else "")
        out.append(f"    {m.result:12}{what}{number}")
    if len(wrong) > 30:
        out.append(f"    ... {len(wrong) - 30} more in the workbook")
    return out
