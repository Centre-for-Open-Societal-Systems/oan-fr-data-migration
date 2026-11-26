# Sample check

People compare the same farmers in Gen1 and Gen2. **It is done by hand,** because it is the
check that doesn't depend on the migration's own rules: it asks whether what a person sees
in Gen2 is what they see in Gen1.

> **To do:** name the checkers, agree the sample size and the critical fields, and make the
> spreadsheet for the results.

## How many, and why

The sample is **drawn at random**, and its size is agreed before the check. A larger sample finds rarer differences and takes more time: time the first few
farmers to plan it. One critical difference means: find the cause, fix it, and draw a new
sample.

## Who

Two people who know the Gen1 screens and did not build the migration. Each checks half. They
both check some of the same farmers, separately: if they disagree, agree on what counts before
going on.

## Drawing the sample

Drawn, not picked, and repeatable: the same seed gives the same farmers. Agree the seed and
the sample size, and write both in the results.

```sql
SELECT row_number() OVER () AS no, m.odoo_id AS gen1_id, m.gen2_id, f.functional_record_id AS farmer_number,
       m.household_key
  FROM migration.migrated_record m
  JOIN g2p_register_farmers f ON f.internal_record_id = m.gen2_id
 WHERE m.kind = 'farmer'
 ORDER BY md5(m.odoo_id::text || 'agreed-seed')
 LIMIT :sample_size;
```

**Chosen cases, besides the random sample:** several of each that exists. Count them separately:
they are not random and say nothing about how often something happens.

| Case | Why |
|---|---|
| Households of several members; a farmer in two households; a farmer in none | Heads and links are worked out |
| Several lands; lands with a map shape; crops of a farmer with several lands | Gen1 doesn't say which land a crop is on |
| Draft, rejected and disabled farmers | Their status in Gen2 |
| Local-language names; farmers with UID, FAN and RID | Gen2 keeps one set of names, one Fayda ID |
| Each region and each import source | Differences by origin |
| Farmers with an issue recorded ("dropped", "check", "skipped") | Is the reason right? |
| Lands with a certificate; farmers with a photo or documents | Once documents are linked |

## What to compare

| Critical: any difference fails | Minor: recorded |
|---|---|
| The same person: name, birth date, gender | Spelling or spacing of free text |
| Farmer ID and Fayda ID | A location shown at a higher level, with a recorded reason |
| Household, and who its head is | A value left empty, with a recorded reason |
| Number and size of lands, and their crops | Order, labels |
| Phone numbers | |
| Status (`ACTIVE` or not), as agreed | |
| Documents, once they are linked: the same file as in Gen1 shows in Gen2 | |

A difference whose reason is recorded **and accepted** is not a failure.

## Finding the recorded reason

Look by the farmer's **household key**, which the sample query gives: e.g. `household-7001`, or
`solo-12` for a farmer in no household. The reason may be about the farmer's phone, land or crop,
or about another member, and those carry their own Gen1 IDs, not the farmer's.

**In the report.** Open `migration-report.xlsx` from the latest `migrate` run, sheet **Issues**:

1. Filter **Household** to the farmer's household key.
2. Filter **Status** to `OPEN`.
3. Read **Record**, **Field**, **Value** and **Reason**. **Odoo id** is the Gen1 ID of that record:
   for a phone, the phone's; for a land, the land's.

| Severity | What it means for the check |
|---|---|
| `dropped` | A value was left out: a likely reason for something empty or missing |
| `skipped` | A record was left out: a likely reason for a missing crop or member |
| `check` | Migrated, with something worth a look: e.g. who the head is, or a location at a higher level |
| `changed` | The household could not be compared with Gen1, so it was not updated: the two may differ. Also in the sheet **Not compared** |
| `conflict` | Gen1 changed after the household was migrated, and staff edited it in Gen2 too: the two are expected to differ. Also in the sheet **Conflicts** |
| `failed` | The household isn't in Gen2, so it can't be in the sample. Also in the sheet **Failed households** |

Example (made up), filtered to `solo-12`:

| Status | Severity | Household | Record | Odoo id | Field | Value | Reason |
|---|---|---|---|---|---|---|---|
| OPEN | dropped | solo-12 | phone | 900 | phone_no | 12ab | not a readable Ethiopian number |
| OPEN | check | solo-12 | farmer | 12 | household | | in no household in farmer profile: given a household of their own, as its head |

No row for what differs means **no recorded reason**: write "none". The sheet holds the first
100,000 issues, open ones first; `issues.csv` in the same folder holds them all. A dry run's
report doesn't count: use the report of the load.

**In the database,** the same:

```sql
SELECT severity, entity, odoo_id, field, value, reason
  FROM migration.issue
 WHERE household_key = 'solo-12' AND status = 'OPEN';
```

## Steps

1. Draw the sample and the chosen cases. Load, `verify` and `health` must have run before.
2. Both check the first few together, to agree on the method and time it.
3. For each farmer: open the Gen1 record, open the Gen2 record, compare, look up the
   recorded reason of what differs, record the result.
4. Report critical differences the same day. Don't wait for the end.
5. At the end: totals, differences by kind, and both names and the date.

## Recording the results

The checkers record what they find in a spreadsheet, **one row per farmer**. It doesn't exist
yet: make it from the columns below, before the check.

| Column | Filled with |
|---|---|
| No | From the query above |
| Gen1 ID | From the query: to open the farmer in Gen1 |
| Gen2 ID | From the query: the record in Gen2 |
| Farmer number | From the query: to find the farmer in Gen2 |
| Household key | From the query: to find recorded reasons |
| Sample | "Random", or which chosen case it is |
| Person, IDs, Household, Lands and crops, Phones, Status, Documents | For each: pass, fail, minor, or n/a (not applicable) |
| What differs | The field, its value in Gen1, its value in Gen2 |
| Recorded reason | What the Issues sheet says (see "Finding the recorded reason"), or "none" |
| Reason accepted? | Yes or no |
| Result | Fail if any critical difference has no accepted reason; else pass |
| Checked by, Date | |

It holds personal data: keep it where only the checkers and the migration team can open it.

### Example

Made up, and without the Gen2 ID and household key columns to fit the page.

| No | Gen1 ID | Farmer number | Sample | Person | IDs | House-hold | Lands and crops | Phones | Status | Docu-ments | What differs | Recorded reason | Accepted? | Result | Checked by | Date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 101 | FR-0000000101 | Random | Pass | Pass | Pass | Pass | Pass | Pass | Pass | | | | **Pass** | Checker A | 1 Mar |
| 2 | 102 | FR-0000000102 | Random | Pass | Pass | Pass | Minor | Pass | Pass | n/a | Land's kebele: filled in Gen1, empty in Gen2 | Not in Master Data | Yes | **Pass** | Checker A | 1 Mar |
| 3 | 103 | FR-0000000103 | Random | Pass | Pass | Pass | Pass | Fail | Pass | Pass | Second phone: in Gen1, missing in Gen2 | Not a readable Ethiopian number | Yes | **Pass** | Checker B | 1 Mar |
| 4 | 104 | FR-0000000104 | Random | Pass | Pass | Pass | Fail | Pass | Pass | Pass | Lands: 3 in Gen1, 2 in Gen2 | None | No | **Fail** | Checker B | 2 Mar |
| 5 | 105 | FR-0000000105 | Random | Fail | Pass | Pass | Pass | Pass | Pass | n/a | Birth date: 1 Jan 1980 in Gen1, 1 Jan 1970 in Gen2 | None | No | **Fail** | Checker A | 2 Mar |
| 6 | 106 | FR-0000000106 | Chosen: no household in Gen1 | Pass | Pass | Pass | Pass | Pass | Pass | Pass | None in Gen1, one of their own in Gen2 | Given a household of their own | Yes | **Pass** | Checker B | 2 Mar |
| 7 | 107 | FR-0000000107 | Chosen: rejected in Gen1 | Pass | Pass | Pass | Pass | Pass | Fail | n/a | Rejected in Gen1, `ACTIVE` in Gen2 | None | No | **Fail** | Checker A | 3 Mar |

How to read it:

- **Row 3** has a critical difference, with a recorded reason that was accepted: a pass.
- **Rows 4 and 5** have critical differences without a reason. They are in the random sample, so
  the check is not passed: find the cause, fix it, draw a new sample.
- **Row 7** is a chosen case. It doesn't fail the random sample: find out how many farmers are like
  it and decide what to do.

## Deciding

| Found | Then |
|---|---|
| No critical difference in the random sample | Passed |
| A critical difference in the random sample | Not passed. Cause, fix, new sample with a new seed |
| A critical difference in a chosen case only | How many farmers are like this? Decide what to do about them |
| The same minor difference again and again | It is accepted, or fixed |
