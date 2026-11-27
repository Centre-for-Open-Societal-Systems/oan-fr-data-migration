"""What every metric of the health report means, and what to do about it: the Guide sheet, and
the Overview's last columns. tests/db/test_health.py checks that no metric is missing.

Written for someone who did not build the migration: each text stands on its own."""

# The words the report uses
WORDS = [
    ("Gen1", "The old system, farmer profile (Odoo). The data comes from here."),
    ("Gen2", "The new system, the Farmer Registry. The data goes to here."),
    ("Load", "One run of the migration that writes data into Gen2."),
    ("Number", "The ID people use: FR-... for a farmer, HH-... for a household. A farmer who has one in Gen1 keeps it. "
               "The others, and all households, get one from Gen2 after the load. Until then Gen2 shows TEMP-..."),
    ("Score", "The completion score: how much of a farmer's form is filled in. It is not migrated: Gen2 calculates it after the "
              "load, because the migration asks it to."),
    ("Both IDs", "The ID a record has in Gen1 and the ID it has in Gen2. They are saved side by side, so that one can be found "
                 "from the other."),
    ("Recorded reason", "When the migration leaves something out it writes down why. The reasons are in migration-report.xlsx, "
                        "sheet Issues."),
    ("Update", "A later load writes Gen1's changes over the Gen2 records it loaded before, unless staff have edited the "
               "household in Gen2 since. Each value it changed is in migration-report.xlsx, sheet Updated."),
    ("Conflict", "A household that changed in Gen1 and was also edited by staff in Gen2. The migration does not touch it: a "
                 "person decides. They are in migration-report.xlsx, sheet Conflicts."),
    ("Set inactive", "A record that is no longer in Gen1 (archived, deleted, or no longer part of its household) gets the "
                     "status INACTIVE in Gen2. Nothing is deleted from Gen2."),
]

_WORKER = "Wait, and run health again. If it does not go down, ask the registry team whether the worker is running."
_REGISTRY = "Ask the registry team: the error is in Gen2's queue."
_BROKEN = "Ask the migration team to find out why."

# metric -> (what it means, what to do when it is not green)
GUIDE = {
    # -- Reconciliation
    "In Gen1": ("How many of this kind of record Gen1 has, including archived ones.", ""),
    "Loaded": ("These records are in Gen2.", ""),
    "Failed": (
        "These records are not in Gen2. Something in their household could not be loaded, so nothing of that household was.",
        "See 'Households that failed to load' on the sheet Run health."),
    "Not added": (
        "These records are not in Gen2. They were added to Gen1 after their household was loaded, and no load has updated the "
        "household since, or the household is a conflict.",
        "Run migrate with --all again: it adds them. For a conflict, see 'Conflicts not settled' on the sheet Run health."),
    "Left out": (
        "These records are not in Gen2, because of a rule or a problem the migration met, and it wrote down the reason itself. For "
        "example, a phone number that cannot be read.",
        "Open migration-report.xlsx, sheet Issues, to see the reason. Accept it, or correct the record in Gen1 before the "
        "production load."),
    "Out of scope": (
        "The migration is not meant to take these records. The rules: the farmer is archived in Gen1; the record belongs to an "
        "archived farmer; the phone number is disabled; the membership has ended; no active farmer is in the household. Draft, "
        "rejected and disabled farmers are not out of scope: they are migrated.", ""),
    "Out of scope, by reason": ("How many of the out-of-scope records each rule applies to. Listed below the table.", ""),
    "Out of scope since, set inactive": (
        "These records were loaded, and are out of scope now: for example, the farmer was archived in Gen1 afterwards. A later "
        "load gave them the status INACTIVE in Gen2, or a person decided to keep them as they are.", ""),
    "Out of scope since, still active": (
        "These records were loaded, and are out of scope now, but are still active in Gen2.",
        "Run migrate with --all: at its end it sets them inactive. If they stay, see 'Conflicts not settled' on the sheet Run "
        "health."),
    "Not reached yet": (
        "No load has come to these records yet, because the last one stopped early or because they are new in Gen1.",
        "Run migrate again."),
    "Unexplained": (
        "These records should be in Gen2 and are not, and nothing says why. They may have been deleted in Gen2, or never loaded.",
        "Find out why before signing off. Start by asking whether anyone deleted records in Gen2."),
    "Loaded, of what should be": (
        "How many of the records that should be in Gen2 are there.",
        "Look at the other columns of the same row on the sheet Reconciliation. They show where the rest are."),
    "Deleted from Gen1 since, set inactive": (
        "These records were loaded, and deleted from Gen1 afterwards. A later load gave them the status INACTIVE in Gen2, or a "
        "person decided to keep them as they are.", ""),
    "Deleted from Gen1 since, still active": (
        "These records were loaded, and deleted from Gen1 afterwards, but are still active in Gen2.",
        "Run migrate with --all: at its end it sets them inactive. If they stay, see 'Conflicts not settled' on the sheet Run "
        "health."),
    "Made for lone farmers": (
        "In Gen2 every farmer needs a household. The migration makes one for a farmer who has none in Gen1.", ""),
    # -- Run health
    "Last run completed": ("Whether the last load ran to its end.", "Run migrate again. It goes on where it stopped."),
    "Last run: seconds": ("How many seconds the last load took.", ""),
    "Last run: farmers loaded": ("How many farmers the last load put into Gen2. Farmers already there are not counted.", ""),
    "Last run: farmers per minute": ("How fast the last load was.", ""),
    "Runs by how they ended": (
        "How many loads there have been, and how each ended. COMPLETED: ran to the end. COMPLETED_WITH_FAILURES: ran to the end, "
        "with some households left out. COMPLETED_WITH_CONFLICTS: ran to the end, and left conflicts for a person to decide. "
        "STOPPED: someone stopped it. FAILED: it could not go on. INTERRUPTED: it was killed.", ""),
    "Households that failed to load": (
        "Something in these households could not be loaded, so nothing of them is in Gen2.",
        "Open migration-report.xlsx, sheet Failed households. Correct the record in Gen1, then run migrate again."),
    "Failed households by kind of error": ("How many of the failed households had each kind of error.", ""),
    "Failed households by age": ("How long ago the failed households first failed.", ""),
    "Households left out because a farmer's number is taken": (
        "A farmer in this household has a number (FR-...) that another farmer already has in Gen2.",
        "Decide whose number it is, correct the other one, and run migrate again."),
    "Households not compared with Gen1": (
        "These households are in Gen2, but could not be compared with Gen1: Gen1 could not be read for them, or part of them was "
        "in Gen2 from before the migration kept its records. They are not updated.",
        "Open migration-report.xlsx, sheet Not compared. Ask the migration team."),
    "Conflicts not settled": (
        "These households changed in Gen1, and staff have also edited them in Gen2 since they were loaded. The migration has not "
        "touched them: Gen2 does not show Gen1's change.",
        "Open migration-report.xlsx, sheet Conflicts, and decide for each household. To keep Gen2 as it is, run migrate with "
        "--resolve and the household. To write Gen1 over the edits made in Gen2, run migrate with --overwrite and the "
        "household."),
    "Values updated from Gen1 since the first load": (
        "How many values later loads wrote over in Gen2, because they changed in Gen1.", ""),
    "Values written over edits in Gen2 by a person's decision": (
        "How many values were written over with Gen1's in households staff had edited in Gen2, because a person decided so "
        "(migrate --overwrite). The value staff had entered is in migration-report.xlsx, sheet Updated, column Before.", ""),
    "Records added to households that were in": (
        "How many records later loads added to households already in Gen2, such as a new phone or land.", ""),
    "Records kept in Gen2 by a person's decision": (
        "Records that are no longer in Gen1, which a person decided to keep as they are in Gen2 (migrate --resolve).", ""),
    "Farmer numbers copied from Gen1": ("These farmers had a number (FR-...) in Gen1 and have the same one in Gen2.", ""),
    "Farmer numbers generated by Gen2": ("These farmers had no number in Gen1. Gen2 has given them one.", ""),
    "Farmer numbers waiting": ("These farmers are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then.", _WORKER),
    "Farmer numbers not queued": ("These farmers have no number, and Gen2 has not been asked for one.", "Run migrate --finalize-only."),
    "Farmer numbers failed": ("Gen2 tried to give these farmers a number and gave up. Gen2 shows TEMP-...", _REGISTRY),
    "Household numbers generated by Gen2": ("Gen2 has given these households a number (HH-...).", ""),
    "Household numbers waiting": ("These households are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then.", _WORKER),
    "Household numbers not queued": ("These households have no number, and Gen2 has not been asked for one.", "Run migrate --finalize-only."),
    "Household numbers failed": ("Gen2 tried to give these households a number and gave up. Gen2 shows TEMP-...", _REGISTRY),
    "Completion scores done": (
        "Gen2 calculates how much of each farmer's form is filled in, section by section. This is how many sections are done.", ""),
    "Completion scores waiting": ("These sections are waiting for Gen2 to calculate their score.", _WORKER),
    "Completion scores failed": ("Gen2 tried to calculate these scores and gave up.", _REGISTRY),
    # -- Quality
    "Values matching Gen1 (verify)": (
        "verify compares every value in Gen2 with what it should be from Gen1. This is how many match.",
        "If not checked: run verify over everything, then health. If red: open verify-report.xlsx, sheet Differences."),
    "Loaded codes and locations still in Master Data (verify)": (
        "Master Data is Gen2's list of allowed values, such as crops and kebeles. This is how many of the values in Gen2 are on it.",
        "If not checked: run verify, then health. If amber: open verify-report.xlsx, sheet Checks."),
    "Values that arrived": (
        "For each field: of the records that have a value in Gen1, how many have one in Gen2. For example, 44 of 47 for marital "
        "status means 3 are empty in Gen2.",
        "If amber, some are empty without a recorded reason: ask the migration team. If below 100% and not amber, each has a reason."),
    "Values lost without a reason": ("These values are in Gen1, are empty in Gen2, and no reason was recorded.", _BROKEN),
    "Left empty: not in Master Data": (
        "The value in Gen1 is not on Gen2's list of allowed values, so the field is empty in Gen2.",
        "Before the production load: add the value to Master Data, or accept that it is left empty."),
    "Left empty: no Gen2 code for the value": (
        "The migration does not know which Gen2 value this Gen1 value corresponds to, so the field is empty in Gen2.",
        "Before the production load: add the value to the migration's mapping, or accept that it is left empty."),
    "Locations placed at a higher level": (
        "The kebele is not in Master Data, so the record is placed at its woreda, zone or region.",
        "Before the production load: add the kebele to Master Data, or accept it."),
    "Locations left empty": (
        "No part of the location is in Master Data, so the record has no location in Gen2.",
        "Before the production load: add the location to Master Data, or accept it."),
    "Phone numbers left out: not readable": (
        "These are not valid Ethiopian phone numbers, so they are not in Gen2.",
        "Correct them in Gen1 before the production load, or accept it."),
    "Phone numbers left out: the farmer has it already": ("A farmer had the same number twice in Gen1. It is in Gen2 once.", ""),
    "Map shapes left out": (
        "The map shape of these lands could not be used, so the land is in Gen2 without it.",
        "Correct it in Gen1 before the production load, or accept it."),
    "Crops left out: the farmer has no land": (
        "In Gen2 a crop belongs to a land. These crops belong to a farmer who has no land, so they are not in Gen2.",
        "Add the land in Gen1 before the production load, or accept it."),
    "Lands over 100 ha, kept as they are": ("These lands are very large, perhaps because of a wrong unit in Gen1. They are in Gen2 as Gen1 "
                                            "has them.", ""),
    "Farmers without their household": ("These farmers are linked to a household that is not in Gen2.", _BROKEN),
    "Members without their household": ("These household members are linked to a household that is not in Gen2.", _BROKEN),
    "Phones without their farmer": ("These phone numbers are linked to a farmer who is not in Gen2.", _BROKEN),
    "Lands without their farmer": ("These lands are linked to a farmer who is not in Gen2.", _BROKEN),
    "Crops without their land": ("These crops are linked to a land that is not in Gen2.", _BROKEN),
    "Households without exactly one head": ("A household must have exactly one head. These have none, or more than one.",
                                            "Ask the registry team to correct the head in Gen2."),
    "Farmers with phones, and not exactly one primary": (
        "One of a farmer's phone numbers must be marked as the primary one. These farmers have none marked, or more than one.",
        "Ask the registry team to correct it in Gen2."),
    "Required by Gen2's forms, and empty": (
        "Gen2's forms require this field, and it is empty. Staff will have to fill it in when they next edit the record. Often Gen1 "
        "never asked for it.", ""),
    "Farmers sharing a Fayda ID with another migrated farmer": (
        "Two or more migrated farmers have the same Fayda ID. They may be the same person.",
        "Decide which farmer keeps the ID."),
    "Farmers sharing a Fayda ID with a farmer already in Gen2": (
        "A migrated farmer has the same Fayda ID as a farmer who was registered in Gen2 directly. They may be the same person.",
        "Decide which farmer keeps the ID."),
    "Farmers sharing an RID with another migrated farmer": (
        "Two or more migrated farmers have the same Fayda registration number (RID). They may be the same person.", ""),
    "Farmers sharing an ODK farmer ID with another migrated farmer": (
        "Two or more migrated farmers have the same ODK form number. The form may have been entered twice in Gen1.", ""),
    "Gen1 status to Gen2 status": ("What status farmers had in Gen1, and what status they have in Gen2.", ""),
    "Edited in Gen2 since (not compared)": (
        "Staff changed these records in Gen2 after the load, so they are expected to differ from Gen1 and are not compared.", ""),
    # -- IDs
    "Migrated records with both IDs saved": (
        "The record's Gen1 ID and its Gen2 ID are saved side by side, so that one can be found from the other.",
        "Ask the migration team: a record without them cannot be traced back to Gen1."),
    "Gen1 Farmer IDs that arrived unchanged": (
        "Of the farmers who had a number (FR-...) in Gen1, how many have the same number in Gen2.", _BROKEN),
    "Fayda IDs (UID or FAN) that arrived": (
        "Of the farmers who had a Fayda ID in Gen1, how many have it in Gen2. Spaces in the ID do not matter.",
        "Open migration-report.xlsx, sheet Issues, to see whether a reason was recorded."),
    "RIDs that arrived": ("Of the farmers who had a Fayda registration number (RID) in Gen1, how many have it in Gen2.", _BROKEN),
    "ODK farmer IDs that arrived": ("Of the farmers who had an ODK form number in Gen1, how many have it in Gen2.", _BROKEN),
    "FANs not carried: the farmer has a UID too": (
        "These farmers have two Fayda IDs in Gen1, a UID and a FAN. Gen2 keeps one, the UID. The FAN is in Gen1 only.", ""),
    "Land IDs that arrived": ("Of the lands that had a land ID in Gen1, how many have it in Gen2.", _BROKEN),
    # -- By region, source and status
    "Farmers loaded": (
        "Of the farmers who should be in Gen2, how many are, for each region, import source and Gen1 status.",
        "If one group is far below the others, look for a cause they share, such as a region missing from Master Data."),
}

# The first metric of each area, in the order above
_FIRST = {"In Gen1": "Reconciliation", "Last run completed": "Run health", "Values matching Gen1 (verify)": "Quality",
          "Migrated records with both IDs saved": "IDs", "Farmers loaded": "By region, source and status"}
AREA = {}
for _metric in GUIDE:
    _area = _FIRST.get(_metric) or _area
    AREA[_metric] = _area

# What each area is about
ABOUT = {
    "Reconciliation": "Is every Gen1 record accounted for? It counts where each one ended up.",
    "Run health": "Did the loads finish, what failed, and has Gen2 given out numbers and calculated scores?",
    "Quality": "Are the values in Gen2 right and complete, and are the records linked correctly?",
    "IDs": "Can every record be traced back to Gen1, and did the IDs people use come across?",
    "By region, source and status": "Is one group of farmers worse off than the others?",
}

# The metrics that have a target: (target, whether missing it blocks sign-off, how many checks it is: one for each kind of record it is
# measured for). The others are numbers to know (INFO).
_RULES = ("Farmers without their household", "Members without their household", "Phones without their farmer",
          "Lands without their farmer", "Crops without their land", "Households without exactly one head",
          "Farmers with phones, and not exactly one primary")
CHECKS = {
    "Out of scope since, still active": ("0", True, 6), "Deleted from Gen1 since, still active": ("0", True, 6),
    "Not reached yet": ("0", False, 6), "Unexplained": ("0", True, 6), "Loaded, of what should be": ("100%", False, 6),
    "Last run completed": ("Yes", True, 1), "Households that failed to load": ("0", True, 1),
    "Households left out because a farmer's number is taken": ("0", False, 1),
    "Households not compared with Gen1": ("Reviewed", False, 1), "Conflicts not settled": ("0", True, 1),
    "Farmer numbers not queued": ("0", False, 1), "Farmer numbers failed": ("0", False, 1),
    "Household numbers not queued": ("0", False, 1), "Household numbers failed": ("0", False, 1),
    "Completion scores failed": ("0", False, 1),
    "Values matching Gen1 (verify)": ("100%", True, 1),
    "Loaded codes and locations still in Master Data (verify)": ("100%", False, 1),
    "Values lost without a reason": ("0", False, 4), **{rule: ("0", True, 1) for rule in _RULES},
    "Farmers sharing a Fayda ID with another migrated farmer": ("0", False, 1),
    "Farmers sharing a Fayda ID with a farmer already in Gen2": ("0", False, 1),
    "Migrated records with both IDs saved": ("100%", True, 6), "Gen1 Farmer IDs that arrived unchanged": ("100%", True, 1),
    "Fayda IDs (UID or FAN) that arrived": ("100%", False, 1), "RIDs that arrived": ("100%", False, 1),
    "ODK farmer IDs that arrived": ("100%", False, 1), "Land IDs that arrived": ("100%", False, 1),
}


def markdown(area) -> str:
    """The area's metrics, as the document has them."""
    out = ["| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |", "|---|---|---|---|---|"]
    for metric, (meaning, todo) in GUIDE.items():
        if AREA[metric] == area:
            target, blocks, _ = CHECKS.get(metric, ("none", False, 0))
            out.append(f"| {metric} | {target} | {'**yes**' if blocks else ''} | {meaning} | {todo} |")
    return "\n".join(out) + "\n"


def areas_markdown() -> str:
    out = ["| Area | What it is about | Metrics | Checks |", "|---|---|---|---|"]
    metrics = checks = 0
    for area, about in ABOUT.items():
        n = sum(1 for m in GUIDE if AREA[m] == area)
        c = sum(CHECKS[m][2] for m in GUIDE if AREA[m] == area and m in CHECKS)
        out.append(f"| {area} | {about} | {n} | {c or 'none'} |")
        metrics, checks = metrics + n, checks + c
    return "\n".join([*out, f"| **Total** | | **{metrics}** | **{checks}** |"]) + "\n"
