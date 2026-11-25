# Reading the reports

There are three workbooks. **Start with the health report. Open the others when it sends you there.**

| | Health report | Migration report | Verify report |
|---|---|---|---|
| File | `health-report.xlsx` | `migration-report.xlsx` | `verify-report.xlsx` |
| Made by | `./run.sh health` | `./run.sh migrate` | `./run.sh verify` |
| Answers | **Is it good enough to sign off?** | **Which household, which record, and why?** | **Which value differs from Gen1?** |
| Open it | First | When you need to know which farmer it is | When values don't match |
| Holds | Counts only | Names, numbers and IDs | Names, numbers and IDs |
| Folder | `out/<time>-health/` | `out/<time>-migrate/` | `out/<time>-verify/` |

[`examples/`](examples) has one of each, made from invented data: use them to follow along.

## In five minutes

1. Open `health-report.xlsx`. It opens on **Overview**.
2. Look at **Overall** (B2). Green: nothing to do. Amber: something to look at. Red: can't be signed off.
3. Below it, the line **Comparison of values (verify)** says whether the values were compared. If not, do that
   first.
4. Go down **What is not green**. For each row read **What it means** and **What to do**.
5. Click **Where** to see the number on its own sheet.
6. If you need to know which farmer, open `migration-report.xlsx`, sheets **Failed households**,
   **Changed in Gen1** or **Issues**.

## The colours

| Result | Meaning | Example |
|---|---|---|
| `GREEN` | As it should be | 0 households failed |
| `AMBER` | Needs a look, or is not finished | 97% of phones are in; the rest have a reason |
| `RED` | **Blocks sign-off** | A land is missing, and nothing says why |
| `NOT CHECKED` | Not measured yet. Never counts as green | `verify` has not run |
| `INFO` | A number to know, without a target | 18 draft farmers became `ACTIVE` |

**Overall** is red if anything that blocks sign-off is red; else amber if anything is amber or not
checked; else green. One red is enough: it isn't an average.

Amber is not a failure. Many loads end amber: somebody looks at each item and accepts it.

## Words used in the reports

| Word | What it means here |
|---|---|
| Gen1 | The old system, farmer profile (Odoo). The data comes from here. |
| Gen2 | The new system, the Farmer Registry. The data goes to here. |
| Load | One run of the migration that writes data into Gen2. |
| Number | The ID people use: FR-... for a farmer, HH-... for a household. A farmer who has one in Gen1 keeps it. The others, and all households, get one from Gen2 after the load. Until then Gen2 shows TEMP-... |
| Score | The completion score: how much of a farmer's form is filled in. It is not migrated: Gen2 calculates it after the load, because the migration asks it to. |
| Both IDs | The ID a record has in Gen1 and the ID it has in Gen2. They are saved side by side, so that one can be found from the other. |
| Recorded reason | When the migration leaves something out it writes down why. The reasons are in migration-report.xlsx, sheet Issues. |

## The health report, sheet by sheet

Open [`examples/health-report-example.xlsx`](examples/health-report-example.xlsx) and follow along. Its
data is invented, and problems were put in on purpose, so its overall result is red.

### Overview

Start here. From top to bottom:

| On the sheet | What it tells you |
|---|---|
| **Overall** | Green, amber or red: can the migration be signed off? Red means no |
| **Last load** | Which run of the migration these results are about. The name starts with its date and time |
| **Measured (database time)** | When these results were taken, and by which command |
| **Comparison of values (verify)** | Whether `verify` has compared every value in Gen2 with Gen1 since that load, and whether it passed. If it says that it has not run, run `verify` and then `health` before you go on. `verify` fails on anything that is missing, even when the migration recorded why; this report asks whether it is explained. So `verify` can fail while this report is amber |
| **The table of areas** | One row for each of the first four sheets: its result, and how many of its checks are red, amber, not checked and green. Click a name to go to the sheet. Each sheet is explained below |
| **What is not green** | Every problem, the worst first: how many records, what it means, what to do, and under **Where** a link to its number |
| **The colours** | What each result means |

### The areas, their metrics and their checks

A **metric** is one thing that is measured. A **check** is a metric with a target, so that it can be
green, amber or red. Some metrics are measured once for each kind of record (farmer, household, member,
phone, land, crop), and are then several checks: "Unexplained" is one metric and six checks. A metric
without a target is a number to know (INFO), and not a check.

| Area | What it is about | Metrics | Checks |
|---|---|---|---|
| Reconciliation | Is every Gen1 record accounted for? It counts where each one ended up. | 12 | 18 |
| Run health | Did the loads finish, what failed, and has Gen2 given out numbers and calculated scores? | 22 | 9 |
| Quality | Are the values in Gen2 right and complete, and are the records linked correctly? | 27 | 15 |
| IDs | Can every record be traced back to Gen1, and did the IDs people use come across? | 7 | 11 |
| By region, source and status | Is one group of farmers worse off than the others? | 1 | none |
| **Total** | | **69** | **53** |

The numbers are always the same. The colours on the Overview add up to the checks. The metrics of each
area are listed below, all of them, under the names they have in the workbook.

### Reconciliation

Is every Gen1 record accounted for? It counts where each one ended up.

One row for each kind of record. **In each row, columns D to J add up to column C, "In Gen1".** Example,
lands in the example workbook (row 6):

| C: In Gen1 | D: Loaded | E: Failed | F: Not added | G: Left out | H: Out of scope | I: Not reached yet | J: Unexplained | K: Adds up |
|---|---|---|---|---|---|---|---|---|
| 360 | 357 | 2 | 0 | 0 | 0 | 0 | **1** | yes |

Gen1 has 360 lands. 357 are in Gen2. 2 belong to a household that failed to load. 1 should be in Gen2 and
is not, and nothing says why: this makes the row red.

**Where do the reasons come from?** The migration script writes them, by itself, at the moment it leaves
something out. For example, it can't read the phone number `12ab`: it loads the farmer without it, and
writes "not a readable Ethiopian number" into its issues table. Nobody types a reason, and there is no way
to give one by hand. People only decide whether a reason is acceptable, and they record that decision
outside the script, at sign-off.

**So "Loaded" does not have to be 100%.** A record that was left out with a reason, or is out of scope, is
accounted for. What has to be 0 is "Unexplained".

**Left out or out of scope?** They are different:

| | Left out | Out of scope |
|---|---|---|
| Should it be in Gen2? | Yes, but the migration could not bring it | No, the migration is not meant to |
| Why | A problem with that record, e.g. a phone number that can't be read | A rule for all records like it, e.g. the farmer is archived |
| Where to see it | `migration-report.xlsx`, sheet Issues: one row for each, with its reason | Below the table on this sheet: how many, for each rule |

The rules for out of scope are:

| Kind of record | Not migrated when |
|---|---|
| Farmer | The farmer is archived in Gen1 |
| Household | No active farmer is in it |
| Member | The membership has ended, or no active farmer is in the household |
| Phone | The number is disabled, or the farmer is archived |
| Land, crop | The farmer is archived |

**Draft, rejected, update-requested and disabled farmers are in scope and are migrated.** Whether archived
farmers are migrated too is to be confirmed before production (issue 10); the report follows what the
migration does.

The other columns: "Should be loaded" is In Gen1 without what is out of scope. "Made for lone farmers" is
extra: households that Gen2 needs and Gen1 doesn't have.

| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |
|---|---|---|---|---|
| In Gen1 | none |  | How many of this kind of record Gen1 has, including archived ones. |  |
| Loaded | none |  | These records are in Gen2. |  |
| Failed | none |  | These records are not in Gen2. Something in their household could not be loaded, so nothing of that household was. | See 'Households that failed to load' on the sheet Run health. |
| Not added | none |  | These records are not in Gen2. They were added to Gen1 after their household was loaded, or their household has changed since. The migration does not add to a household it has already loaded. | Open migration-report.xlsx, sheet Changed in Gen1. Add the record in Gen2 if it is wanted. |
| Left out | none |  | These records are not in Gen2, because of a rule or a problem the migration met, and it wrote down the reason itself. For example, a phone number that cannot be read. | Open migration-report.xlsx, sheet Issues, to see the reason. Accept it, or correct the record in Gen1 before the production load. |
| Out of scope | none |  | The migration is not meant to take these records. The rules: the farmer is archived in Gen1; the record belongs to an archived farmer; the phone number is disabled; the membership has ended; no active farmer is in the household. Draft, rejected and disabled farmers are not out of scope: they are migrated. |  |
| Out of scope, by reason | none |  | How many of the out-of-scope records each rule applies to. Listed below the table. |  |
| Not reached yet | 0 |  | No load has come to these records yet, because the last one stopped early or because they are new in Gen1. | Run migrate again. |
| Unexplained | 0 | **yes** | These records should be in Gen2 and are not, and nothing says why. They may have been deleted in Gen2, or never loaded. | Find out why before signing off. Start by asking whether anyone deleted records in Gen2. |
| Loaded, of what should be | 100% |  | How many of the records that should be in Gen2 are there. | Look at the other columns of the same row on the sheet Reconciliation. They show where the rest are. |
| Loaded, and no longer in Gen1 | none |  | These records are in Gen2, but were deleted from Gen1 after the load. | Nothing, if it was right to delete them. |
| Made for lone farmers | none |  | In Gen2 every farmer needs a household. The migration makes one for a farmer who has none in Gen1. |  |

### Run health

Did the loads finish, what failed, and has Gen2 given out numbers and calculated scores?

It has 9 checks: whether the last load completed; households that failed, that changed, and that were left
out because a number is taken; farmer and household numbers that are not queued or failed; and scores that
failed.

| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |
|---|---|---|---|---|
| Last run completed | Yes | **yes** | Whether the last load ran to its end. | Run migrate again. It goes on where it stopped. |
| Last run: seconds | none |  | How many seconds the last load took. |  |
| Last run: farmers loaded | none |  | How many farmers the last load put into Gen2. Farmers already there are not counted. |  |
| Last run: farmers per minute | none |  | How fast the last load was. |  |
| Runs by how they ended | none |  | How many loads there have been, and how each ended. COMPLETED: ran to the end. COMPLETED_WITH_FAILURES: ran to the end, with some households left out. STOPPED: someone stopped it. FAILED: it could not go on. INTERRUPTED: it was killed. |  |
| Households that failed to load | 0 | **yes** | Something in these households could not be loaded, so nothing of them is in Gen2. | Open migration-report.xlsx, sheet Failed households. Correct the record in Gen1, then run migrate again. |
| Failed households by kind of error | none |  | How many of the failed households had each kind of error. |  |
| Failed households by age | none |  | How long ago the failed households first failed. |  |
| Households left out because a farmer's number is taken | 0 |  | A farmer in this household has a number (FR-...) that another farmer already has in Gen2. | Decide whose number it is, correct the other one, and run migrate again. |
| Households changed in Gen1 since they were migrated | Reviewed |  | Someone changed these households in Gen1 after they were loaded. Gen2 still has what was loaded. | Open migration-report.xlsx, sheet Changed in Gen1. Make the same change in Gen2. |
| Farmer numbers copied from Gen1 | none |  | These farmers had a number (FR-...) in Gen1 and have the same one in Gen2. |  |
| Farmer numbers generated by Gen2 | none |  | These farmers had no number in Gen1. Gen2 has given them one. |  |
| Farmer numbers waiting | none |  | These farmers are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Farmer numbers not queued | 0 |  | These farmers have no number, and Gen2 has not been asked for one. | Run migrate --finalize-only. |
| Farmer numbers failed | 0 |  | Gen2 tried to give these farmers a number and gave up. Gen2 shows TEMP-... | Ask the registry team: the error is in Gen2's queue. |
| Household numbers generated by Gen2 | none |  | Gen2 has given these households a number (HH-...). |  |
| Household numbers waiting | none |  | These households are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Household numbers not queued | 0 |  | These households have no number, and Gen2 has not been asked for one. | Run migrate --finalize-only. |
| Household numbers failed | 0 |  | Gen2 tried to give these households a number and gave up. Gen2 shows TEMP-... | Ask the registry team: the error is in Gen2's queue. |
| Completion scores done | none |  | Gen2 calculates how much of each farmer's form is filled in, section by section. This is how many sections are done. |  |
| Completion scores waiting | none |  | These sections are waiting for Gen2 to calculate their score. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Completion scores failed | 0 |  | Gen2 tried to calculate these scores and gave up. | Ask the registry team: the error is in Gen2's queue. |

### Quality

Are the values in Gen2 right and complete, and are the records linked correctly?

It has 15 checks: 2 that come from `verify`; values lost without a reason, for farmers, phones, lands and
crops; 7 rules about links, heads and primary phones; and 2 about shared Fayda IDs.

What needs attention comes first. The sheet can be filtered by **Result** or **Metric**.

| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |
|---|---|---|---|---|
| Values matching Gen1 (verify) | 100% | **yes** | verify compares every value in Gen2 with what it should be from Gen1. This is how many match. | If not checked: run verify over everything, then health. If red: open verify-report.xlsx, sheet Differences. |
| Loaded codes and locations still in Master Data (verify) | 100% |  | Master Data is Gen2's list of allowed values, such as crops and kebeles. This is how many of the values in Gen2 are on it. | If not checked: run verify, then health. If amber: open verify-report.xlsx, sheet Checks. |
| Values that arrived | none |  | For each field: of the records that have a value in Gen1, how many have one in Gen2. For example, 44 of 47 for marital status means 3 are empty in Gen2. | If amber, some are empty without a recorded reason: ask the migration team. If below 100% and not amber, each has a reason. |
| Values lost without a reason | 0 |  | These values are in Gen1, are empty in Gen2, and no reason was recorded. | Ask the migration team to find out why. |
| Left empty: not in Master Data | none |  | The value in Gen1 is not on Gen2's list of allowed values, so the field is empty in Gen2. | Before the production load: add the value to Master Data, or accept that it is left empty. |
| Left empty: no Gen2 code for the value | none |  | The migration does not know which Gen2 value this Gen1 value corresponds to, so the field is empty in Gen2. | Before the production load: add the value to the migration's mapping, or accept that it is left empty. |
| Locations placed at a higher level | none |  | The kebele is not in Master Data, so the record is placed at its woreda, zone or region. | Before the production load: add the kebele to Master Data, or accept it. |
| Locations left empty | none |  | No part of the location is in Master Data, so the record has no location in Gen2. | Before the production load: add the location to Master Data, or accept it. |
| Phone numbers left out: not readable | none |  | These are not valid Ethiopian phone numbers, so they are not in Gen2. | Correct them in Gen1 before the production load, or accept it. |
| Phone numbers left out: the farmer has it already | none |  | A farmer had the same number twice in Gen1. It is in Gen2 once. |  |
| Map shapes left out | none |  | The map shape of these lands could not be used, so the land is in Gen2 without it. | Correct it in Gen1 before the production load, or accept it. |
| Crops left out: the farmer has no land | none |  | In Gen2 a crop belongs to a land. These crops belong to a farmer who has no land, so they are not in Gen2. | Add the land in Gen1 before the production load, or accept it. |
| Lands over 100 ha, kept as they are | none |  | These lands are very large, perhaps because of a wrong unit in Gen1. They are in Gen2 as Gen1 has them. |  |
| Farmers without their household | 0 | **yes** | These farmers are linked to a household that is not in Gen2. | Ask the migration team to find out why. |
| Members without their household | 0 | **yes** | These household members are linked to a household that is not in Gen2. | Ask the migration team to find out why. |
| Phones without their farmer | 0 | **yes** | These phone numbers are linked to a farmer who is not in Gen2. | Ask the migration team to find out why. |
| Lands without their farmer | 0 | **yes** | These lands are linked to a farmer who is not in Gen2. | Ask the migration team to find out why. |
| Crops without their land | 0 | **yes** | These crops are linked to a land that is not in Gen2. | Ask the migration team to find out why. |
| Households without exactly one head | 0 | **yes** | A household must have exactly one head. These have none, or more than one. | Ask the registry team to correct the head in Gen2. |
| Farmers with phones, and not exactly one primary | 0 | **yes** | One of a farmer's phone numbers must be marked as the primary one. These farmers have none marked, or more than one. | Ask the registry team to correct it in Gen2. |
| Required by Gen2's forms, and empty | none |  | Gen2's forms require this field, and it is empty. Staff will have to fill it in when they next edit the record. Often Gen1 never asked for it. |  |
| Farmers sharing a Fayda ID with another migrated farmer | 0 |  | Two or more migrated farmers have the same Fayda ID. They may be the same person. | Decide which farmer keeps the ID. |
| Farmers sharing a Fayda ID with a farmer already in Gen2 | 0 |  | A migrated farmer has the same Fayda ID as a farmer who was registered in Gen2 directly. They may be the same person. | Decide which farmer keeps the ID. |
| Farmers sharing an RID with another migrated farmer | none |  | Two or more migrated farmers have the same Fayda registration number (RID). They may be the same person. |  |
| Farmers sharing an ODK farmer ID with another migrated farmer | none |  | Two or more migrated farmers have the same ODK form number. The form may have been entered twice in Gen1. |  |
| Gen1 status to Gen2 status | none |  | What status farmers had in Gen1, and what status they have in Gen2. |  |
| Edited in Gen2 since (not compared) | none |  | Staff changed these records in Gen2 after the load, so they are expected to differ from Gen1 and are not compared. |  |

### IDs

Can every record be traced back to Gen1, and did the IDs people use come across?

It has 11 checks: both IDs saved, for each of the six kinds of record; and five kinds of Gen1 ID that should
be in Gen2 (Farmer ID, Fayda ID, RID, ODK farmer ID, land ID).

| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |
|---|---|---|---|---|
| Migrated records with both IDs saved | 100% | **yes** | The record's Gen1 ID and its Gen2 ID are saved side by side, so that one can be found from the other. | Ask the migration team: a record without them cannot be traced back to Gen1. |
| Gen1 Farmer IDs that arrived unchanged | 100% | **yes** | Of the farmers who had a number (FR-...) in Gen1, how many have the same number in Gen2. | Ask the migration team to find out why. |
| Fayda IDs (UID or FAN) that arrived | 100% |  | Of the farmers who had a Fayda ID in Gen1, how many have it in Gen2. Spaces in the ID do not matter. | Open migration-report.xlsx, sheet Issues, to see whether a reason was recorded. |
| RIDs that arrived | 100% |  | Of the farmers who had a Fayda registration number (RID) in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |
| ODK farmer IDs that arrived | 100% |  | Of the farmers who had an ODK form number in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |
| FANs not carried: the farmer has a UID too | none |  | These farmers have two Fayda IDs in Gen1, a UID and a FAN. Gen2 keeps one, the UID. The FAN is in Gen1 only. |  |
| Land IDs that arrived | 100% |  | Of the lands that had a land ID in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |

### By region, source and status

Is one group of farmers worse off than the others? An overall figure can hide a group with a problem of its own.

| Metric | Target | Blocks sign-off | What it means | What to do when it is not green |
|---|---|---|---|---|
| Farmers loaded | none |  | Of the farmers who should be in Gen2, how many are, for each region, import source and Gen1 status. | If one group is far below the others, look for a cause they share, such as a region missing from Master Data. |

### Trend

A column for each earlier measurement. Use it to compare a rehearsal with the next one, or the
figures right after the load with those when numbers and scores are done.

### Guide

The tables above, in the workbook.

## The migration report, sheet by sheet

| Sheet | Open it when | What is in it |
|---|---|---|
| **Health** | You want the result without another file | Every health metric at the end of the load. What `verify` finds is "not checked" here |
| **Summary** | You want the figures of this run | Run details; households loaded, failed and left; records per register; issues by kind; fields with data that has nowhere to go in Gen2 |
| **Failed households** | The health report says households failed | One row per household: its farmers' Gen1 IDs, the kind of error, what it said, how often it was tried |
| **Changed in Gen1** | The health report says households changed | One row per household: its farmers, and what changed since it was loaded. Gen2 was not touched |
| **Issues summary** | You want to know what is most common | Issues grouped by reason, the most frequent first |
| **Issues** | You want to know what happened to one farmer | One row per issue: see below |
| **Runs** | You want to know what was run | Every load: when, how it ended, what it loaded, why it stopped |
| **Batches** | Somebody looks into speed or an error | Each batch of this run: its households, time and result |
| **Mapping - Gen1 fields** | You want to know where a Gen1 field goes | Each Gen1 field, its Gen2 column, and how many records hold it |
| **Mapping - Gen2 columns** | You want to know where a Gen2 value comes from | Each Gen2 column, its source, and how many records hold it |
| **Mapping - key** | A status in the two sheets above is unclear | What each status means |

The mapping sheets say what the migration covers. They are the same in every run, but for the counts.

### The Issues sheet

| Column | What it is |
|---|---|
| Status | `OPEN`: still so. `RESOLVED`: a later run found it gone |
| Severity | See below |
| Household | The household key: `household-7001`, or `solo-12` for farmer 12 in no household. **Filter by this to find everything about a farmer** |
| Record, Odoo id | Which kind of record, and its Gen1 ID. A phone's is the phone's, not the farmer's |
| Field, Value | Which field, and its value in Gen1 |
| Reason | Why |
| First run, Last run | When it was first and last seen |

| Severity | Meaning | In Gen2? |
|---|---|---|
| `failed` | The household could not be loaded | Nothing of it |
| `changed` | It changed in Gen1 after it was loaded | As it was loaded |
| `skipped` | A record could not be loaded, e.g. a crop without a land | All but that record |
| `dropped` | A value could not be carried over | All but that value |
| `check` | Loaded, with something worth a look | Everything |

## The verify report, sheet by sheet

| Sheet | What is in it |
|---|---|
| **Summary** | Pass or fail, and how many checks and values |
| **Checks** | Each check, what was expected and found. Filter Result to `FAIL` |
| **Columns** | For each column: how many values were compared, and how many differ |
| **Differences** | Each value that differs: the record, its Gen1 ID, what was expected, what Gen2 has |

## What do I do when...

| The health report says | Do this |
|---|---|
| **Households that failed to load** | `migration-report.xlsx`, sheet Failed households. Correct the record in Gen1. Run `migrate` again: only they are tried again. Then `verify` and `health` |
| **Unexplained** | Look for the record in Gen2. Deleted? Who, and why? Never there? Report it to the migration team |
| **Last run completed: no** | Run `migrate` again. It goes on where it stopped |
| **Values matching Gen1: not checked** | Run `verify`, then `health` |
| **Values matching Gen1: red** | `verify-report.xlsx`, sheet Differences |
| **Loaded, of what should be: amber** | Read the same row of Reconciliation: the other columns say where the rest is |
| **Values left empty** | Before the load: add the value to Master Data or the mapping. After it: correct it in Gen2 |
| **Numbers waiting** | Wait, then run `health` again |
| **Numbers failed** | The registry team |
| **Shared Fayda ID** | Decide which farmer keeps it |

## Looking up one farmer

You need the farmer's Gen1 ID, e.g. 12.

| Question | Where |
|---|---|
| Is the farmer in Gen2, and under which ID? | Database: `SELECT gen2_id, household_key FROM migration.migrated_record WHERE kind = 'farmer' AND odoo_id = 12` |
| Why not? | `migration-report.xlsx`, sheet Failed households: search for 12 in the farmers column |
| What happened to this farmer's data? | Sheet Issues: filter Household by the household key |
| Has the farmer changed in Gen1 since? | Sheet Changed in Gen1 |

## Good to know

- **`health` changes nothing in the farmer data.** It can be run as often as you like.
- **`verify` and `health` compare Gen2 with Gen1,** so they are run before staff start to edit Gen2.
- **A dry run measures no health:** nothing was loaded.
- **The report doesn't judge Gen1's data.** A wrong age that arrives unchanged is a correct migration.
- **The Issues sheet holds the first 100,000 issues,** open ones first. `issues.csv` holds them all.
