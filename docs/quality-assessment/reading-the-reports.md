# Reading the reports

There are two workbooks. **Start with the health report. Go to the migration report when you need
to know which farmer it is.**

| | Health report | Migration report |
|---|---|---|
| File | `health-report.xlsx` | `migration-report.xlsx` |
| Made by | `./run.sh health` | `./run.sh migrate` |
| Answers | **Is it good enough to sign off?** | **Which household, which record, and why?** |
| Holds | Counts only | Names, numbers and IDs |
| Share with | Everyone involved | The migration and data teams only |
| Folder | `out/<time>-health/` | `out/<time>-migrate/` |

A third, `verify-report.xlsx`, is made by `./run.sh verify`, which compares every value. Open it when
the health report says values don't match, or that `verify` failed. It holds names, numbers and IDs.

## In five minutes

1. Open `health-report.xlsx`. It opens on **Overview**.
2. Look at **Overall** (B2). Green: nothing to do. Amber: something to look at. Red: can't be signed off.
3. Below it, the line **verify** says whether the values were compared. If not, do that first.
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

### Overview

| Part | What it tells you |
|---|---|
| Overall, last load, when it was measured | The answer, and what it is about |
| verify | Whether every value was compared since the last load, and what it found. `verify` fails on anything missing, also when the reason is recorded; this report asks whether it is explained. So `verify` can fail while this is amber |
| The four areas | The result of each, and how many of its **checks** (not records) are red, amber, not checked and green. Click one to go to its sheet. The colours add up to the number of checks, which is always the same: see below |
| What is not green | Every problem, the worst first, with its meaning, what to do, and a link to its number |

The numbers of the areas:

| Area | Checks | What they are |
|---|---|---|
| Reconciliation | 18 | 3 for each of the 6 kinds of record: unexplained, not reached yet, loaded of what should be |
| Run health | 9 | Last run completed; households failed, changed, and left out because a number is taken; farmer and household numbers not queued and failed; scores failed |
| Quality | 15 | 2 from `verify`; values lost, for 4 kinds of record; 7 rules about links, heads and phones; 2 about shared Fayda IDs |
| IDs | 11 | Both IDs saved, for 6 kinds of record; and 5 kinds of Gen1 ID that arrived |
| **Total** | **53** | |

Metrics marked INFO have no target, so they aren't checks and aren't counted here.

### Reconciliation: where did every Gen1 record go?

One row for each kind of record. It shows what happened to every one of them: how many were
loaded, failed, were left out, and so on. **In each row, these counts add up to the column "In Gen1",
which is how many there are in Gen1.**

Example (made up), for lands:

| In Gen1 | Loaded | Failed | Not added | Left out | Out of scope | Not reached | Unexplained | Adds up |
|---|---|---|---|---|---|---|---|---|
| 360 | 357 | 2 | 0 | 0 | 0 | 0 | **1** | yes |

"Of 360 lands, 357 are in Gen2. 2 belong to a household that failed. **1 should be there and is not,
and nothing says why.**" The last one is what makes it red.

- **The column that matters most is Unexplained.** It must be 0.
- **Loaded doesn't have to be 100%.** A phone that can't be read is "Left out", with a reason.
- **Out of scope** is not the same as not active. These are in scope and migrated: draft, rejected,
  update-requested and disabled farmers. These are not migrated, by rule, and are listed under the table
  with their number: farmers archived in Gen1 and what is theirs, disabled phone numbers, ended
  memberships, and households without an active farmer. Whether archived farmers are migrated is to
  be confirmed before production (issue 10); the report follows what the migration does.
- **Made for lone farmers** is extra: households Gen2 needs and Gen1 doesn't have.

| Metric | What it means | What to do when it is not green |
|---|---|---|
| Gen1 records | How many of this kind of record Gen1 has, including archived ones. |  |
| Loaded | These records are in Gen2. |  |
| Failed: its household failed | These records are not in Gen2. Something in their household could not be loaded, so nothing of that household was. | See 'Households that failed to load' on the sheet Run health. |
| Not added: its household changed after it was migrated | These records are not in Gen2. They were added to Gen1 after their household was loaded, or their household has changed since. The migration does not add to a household it has already loaded. | Open migration-report.xlsx, sheet Changed in Gen1. Add the record in Gen2 if it is wanted. |
| Left out: skipped or dropped, with a recorded reason | These records are not in Gen2, and the migration recorded why. For example, a phone number that cannot be read. | Open migration-report.xlsx, sheet Issues. Accept the reason, or correct the record in Gen1 before the production load. |
| Out of scope: not migrated, by rule (see below) | The migration does not take these: archived farmers and what belongs to them, disabled phone numbers, ended memberships, and households without an active farmer. Draft, rejected and disabled farmers are in scope and are migrated. |  |
| Out of scope, by reason | The out-of-scope records again, with the rule that applies to them. |  |
| Not reached yet | No load has come to these records yet, because the last one stopped early or because they are new in Gen1. | Run migrate again. |
| Unexplained | These records should be in Gen2 and are not, and nothing says why. They may have been deleted in Gen2, or never loaded. | Find out why before signing off. Start by asking whether anyone deleted records in Gen2. |
| Loaded, of what should be | How many of the records that should be in Gen2 are there. | Look at the other columns of the same row on the sheet Reconciliation. They show where the rest are. |
| Loaded, and no longer in Gen1 | These records are in Gen2, but were deleted from Gen1 after the load. | Nothing, if it was right to delete them. |
| Made by the migration for a farmer in no household (not in Gen1) | In Gen2 every farmer needs a household. The migration makes one for a farmer who has none in Gen1. |  |

### Run health: how did the loads go?

| Metric | What it means | What to do when it is not green |
|---|---|---|
| Last run completed | Whether the last load ran to its end. | Run migrate again. It goes on where it stopped. |
| Last run: seconds | How many seconds the last load took. |  |
| Last run: farmers loaded | How many farmers the last load put into Gen2. Farmers already there are not counted. |  |
| Last run: farmers per minute | How fast the last load was. |  |
| Runs by how they ended | How many loads there have been, and how each ended. COMPLETED: ran to the end. COMPLETED_WITH_FAILURES: ran to the end, with some households left out. STOPPED: someone stopped it. FAILED: it could not go on. INTERRUPTED: it was killed. |  |
| Households that failed to load | Something in these households could not be loaded, so nothing of them is in Gen2. | Open migration-report.xlsx, sheet Failed households. Correct the record in Gen1, then run migrate again. |
| Failed households by kind of error | How many of the failed households had each kind of error. |  |
| Failed households by age | How long ago the failed households first failed. |  |
| Households left out because a farmer's number is taken | A farmer in this household has a number (FR-...) that another farmer already has in Gen2. | Decide whose number it is, correct the other one, and run migrate again. |
| Households changed in Gen1 since they were migrated | Someone changed these households in Gen1 after they were loaded. Gen2 still has what was loaded. | Open migration-report.xlsx, sheet Changed in Gen1. Make the same change in Gen2. |
| Farmer numbers copied from Gen1 | These farmers had a number (FR-...) in Gen1 and have the same one in Gen2. |  |
| Farmer numbers generated by Gen2 | These farmers had no number in Gen1. Gen2 has given them one. |  |
| Farmer numbers waiting | These farmers are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Farmer numbers not queued | These farmers have no number, and Gen2 has not been asked for one. | Run migrate --finalize-only. |
| Farmer numbers failed | Gen2 tried to give these farmers a number and gave up. Gen2 shows TEMP-... | Ask the registry team: the error is in Gen2's queue. |
| Household numbers generated by Gen2 | Gen2 has given these households a number (HH-...). |  |
| Household numbers waiting | These households are waiting for Gen2 to give them a number. Gen2 shows TEMP-... until then. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Household numbers not queued | These households have no number, and Gen2 has not been asked for one. | Run migrate --finalize-only. |
| Household numbers failed | Gen2 tried to give these households a number and gave up. Gen2 shows TEMP-... | Ask the registry team: the error is in Gen2's queue. |
| Completion scores done | Gen2 calculates how much of each farmer's form is filled in, section by section. This is how many sections are done. |  |
| Completion scores waiting | These sections are waiting for Gen2 to calculate their score. | Wait, and run health again. If it does not go down, ask the registry team whether the worker is running. |
| Completion scores failed | Gen2 tried to calculate these scores and gave up. | Ask the registry team: the error is in Gen2's queue. |

### Quality: did the data arrive?

What needs attention comes first. Each sheet can be filtered by **Result** or **Metric**.

How to read "Values that arrived": *marital_status, 44 of 47, 93.6%* means that of 47 farmers with a
marital status in Gen1, 44 have one in Gen2. The other 3 are under "Left empty", with the reason. It
would be amber if they had none.

| Metric | What it means | What to do when it is not green |
|---|---|---|
| Values matching Gen1 (verify) | verify compares every value in Gen2 with what it should be from Gen1. This is how many match. | If not checked: run verify over everything, then health. If red: open verify-report.xlsx, sheet Differences. |
| Loaded codes and locations still in Master Data (verify) | Master Data is Gen2's list of allowed values, such as crops and kebeles. This is how many of the values in Gen2 are on it. | If not checked: run verify, then health. If amber: open verify-report.xlsx, sheet Checks. |
| Values that arrived | For each field: of the records that have a value in Gen1, how many have one in Gen2. For example, 44 of 47 for marital status means 3 are empty in Gen2. | If amber, some are empty without a recorded reason: ask the migration team. If below 100% and not amber, each has a reason. |
| Values lost without a reason | These values are in Gen1, are empty in Gen2, and no reason was recorded. | Ask the migration team to find out why. |
| Left empty: not in Master Data | The value in Gen1 is not on Gen2's list of allowed values, so the field is empty in Gen2. | Before the production load: add the value to Master Data, or accept that it is left empty. |
| Left empty: no Gen2 code for the value | The migration does not know which Gen2 value this Gen1 value corresponds to, so the field is empty in Gen2. | Before the production load: add the value to the migration's mapping, or accept that it is left empty. |
| Locations placed at a higher level | The kebele is not in Master Data, so the record is placed at its woreda, zone or region. | Before the production load: add the kebele to Master Data, or accept it. |
| Locations left empty | No part of the location is in Master Data, so the record has no location in Gen2. | Before the production load: add the location to Master Data, or accept it. |
| Phone numbers left out: not readable | These are not valid Ethiopian phone numbers, so they are not in Gen2. | Correct them in Gen1 before the production load, or accept it. |
| Phone numbers left out: the farmer has it already | A farmer had the same number twice in Gen1. It is in Gen2 once. |  |
| Map shapes left out | The map shape of these lands could not be used, so the land is in Gen2 without it. | Correct it in Gen1 before the production load, or accept it. |
| Crops left out: the farmer has no land | In Gen2 a crop belongs to a land. These crops belong to a farmer who has no land, so they are not in Gen2. | Add the land in Gen1 before the production load, or accept it. |
| Lands over 100 ha, kept as they are | These lands are very large, perhaps because of a wrong unit in Gen1. They are in Gen2 as Gen1 has them. |  |
| Farmers without their household | These farmers are linked to a household that is not in Gen2. | Ask the migration team to find out why. |
| Members without their household | These household members are linked to a household that is not in Gen2. | Ask the migration team to find out why. |
| Phones without their farmer | These phone numbers are linked to a farmer who is not in Gen2. | Ask the migration team to find out why. |
| Lands without their farmer | These lands are linked to a farmer who is not in Gen2. | Ask the migration team to find out why. |
| Crops without their land | These crops are linked to a land that is not in Gen2. | Ask the migration team to find out why. |
| Households without exactly one head | A household must have exactly one head. These have none, or more than one. | Ask the registry team to correct the head in Gen2. |
| Farmers with phones, and not exactly one primary | One of a farmer's phone numbers must be marked as the primary one. These farmers have none marked, or more than one. | Ask the registry team to correct it in Gen2. |
| Required by Gen2's forms, and empty | Gen2's forms require this field, and it is empty. Staff will have to fill it in when they next edit the record. Often Gen1 never asked for it. |  |
| Farmers sharing a Fayda ID with another migrated farmer | Two or more migrated farmers have the same Fayda ID. They may be the same person. | The data owner decides which farmer keeps the ID. |
| Farmers sharing a Fayda ID with a farmer already in Gen2 | A migrated farmer has the same Fayda ID as a farmer who was registered in Gen2 directly. They may be the same person. | The data owner decides which farmer keeps the ID. |
| Farmers sharing an RID with another migrated farmer | Two or more migrated farmers have the same Fayda registration number (RID). They may be the same person. |  |
| Farmers sharing an ODK farmer ID with another migrated farmer | Two or more migrated farmers have the same ODK form number. The form may have been entered twice in Gen1. |  |
| Gen1 status to Gen2 status | What status farmers had in Gen1, and what status they have in Gen2. |  |
| Edited in Gen2 since (not compared) | Staff changed these records in Gen2 after the load, so they are expected to differ from Gen1 and are not compared. |  |

### IDs: can every record be traced?

| Metric | What it means | What to do when it is not green |
|---|---|---|
| Migrated records with both IDs saved | The record's Gen1 ID and its Gen2 ID are saved side by side, so that one can be found from the other. | Ask the migration team: a record without them cannot be traced back to Gen1. |
| Gen1 Farmer IDs that arrived unchanged | Of the farmers who had a number (FR-...) in Gen1, how many have the same number in Gen2. | Ask the migration team to find out why. |
| Fayda IDs (UID or FAN) that arrived | Of the farmers who had a Fayda ID in Gen1, how many have it in Gen2. Spaces in the ID do not matter. | Open migration-report.xlsx, sheet Issues, to see whether a reason was recorded. |
| RIDs that arrived | Of the farmers who had a Fayda registration number (RID) in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |
| ODK farmer IDs that arrived | Of the farmers who had an ODK form number in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |
| FANs not carried: the farmer has a UID too | These farmers have two Fayda IDs in Gen1, a UID and a FAN. Gen2 keeps one, the UID. The FAN is in Gen1 only. |  |
| Land IDs that arrived | Of the lands that had a land ID in Gen1, how many have it in Gen2. | Ask the migration team to find out why. |

### By region, source and status

| Metric | What it means | What to do when it is not green |
|---|---|---|
| Farmers loaded | Of the farmers who should be in Gen2, how many are, for each region, import source and Gen1 status. | If one group is far below the others, look for a cause they share, such as a region missing from Master Data. |

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
| **Shared Fayda ID** | The data owner decides |

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
