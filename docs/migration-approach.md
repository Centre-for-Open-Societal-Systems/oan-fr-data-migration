# Gen1-to-Gen2 Data Migration Proposed Approach

## Approach

We propose using a controlled ETL pipeline to migrate data from the Gen1 Odoo Farmer Profile database to the Gen2 Farmer Registry.

1. **Extract — Python, psycopg2 and PostgreSQL**
   The pipeline will read Gen1 in read-only mode and extract farmers together with their households, members, IDs, phones, lands and crops.

2. **Transform — Python**
   It will convert Gen1 records into the Gen2 structure, map reference codes, normalize names and dates, convert yes/no values to Boolean, build JSON values and generate deterministic UUID5 identifiers.

3. **Validate — Master Data Service**
   Governed values and geographic codes will be checked against Gen2 Master Data. Invalid or unsupported values will be reported instead of being silently loaded.

4. **Prepare — SQLAlchemy and Gen2 models**
   The pipeline will run the installed Gen2 model hooks in memory to apply defaults and derive fields such as record names and search text.

5. **Load — PostgreSQL COPY and SQL transactions**
   Prepared records will be copied into temporary tables and inserted into Gen2 in parent-before-child order. Each batch will run in a transaction and will be rolled back if it fails.

6. **Verify — Python and PostgreSQL SQL**
   A separate verification process will compare Gen1 and Gen2 record counts, identifiers, field values, relationships and calculated totals.

## Proposed safety controls

- Gen1 will remain read-only.
- Deterministic IDs will make reruns consistent.
- The household is migrated whole or not at all; one that fails is recorded and left out, and the rest go on.
- Progress and issues are kept in audit tables in the Gen2 database, written with the records, so a stopped run resumes where it left off.
- Running the migration again after the full load brings Gen1's changes (see "Changes in Gen1 after the migration" below).
- Only one run works at a time, and a different Gen1 database is refused.
- `ON CONFLICT DO NOTHING` will prevent duplicate insertion.
- Dry-run mode will execute the migration and roll back all changes.
- Invalid and unmapped values will be recorded in issue reports.
- Every run will produce logs, summaries, CSV details and formatted Excel reports using `openpyxl`.
- The pipeline will be tested with `pytest` before production execution.

## Changes in Gen1 after the migration

If Gen1 is still used after the full migration, the same command, `migrate.py --all`, is run again. It compares every household with what was migrated (estimated at about 15 minutes for 600,000 farmers, scaled from a 20,000-farmer test on a laptop; a rehearsal will give the real figure) and brings only what changed:

| In Gen1 since the household was migrated | In Gen2, if staff have not edited the household | If staff have edited it in Gen2 |
|---|---|---|
| New farmer or household | Added | — |
| Values changed | Written over with Gen1's | **Conflict**: not touched |
| New phone, land, crop or member | Added | Conflict |
| Members moved, left, or a new head | Memberships rebuilt | Conflict |
| Archived or deleted | Set INACTIVE, never deleted | Conflict |

**Gen1 overwrites Gen2, unless Gen2 has been edited.** A household that staff have edited in Gen2 since it was migrated is not overwritten by a run. It is listed as a conflict, for a person to decide, household by household. Both commands take one or more households:

- `migrate.py --resolve <household> ...` keeps Gen2 as it is.
- `migrate.py --overwrite <household> ...` writes Gen1 over the edits made in Gen2. The values Gen2 had are kept in the audit table.

- Kept on every update: the farmer and household numbers, who created the record and when, and what Gen2's own workers fill in.
- Every change is recorded in the audit table `migration.change` and in the report.
- Only a run over every farmer (`--all`) sets records inactive.
- `verify` and `health` are run again after each such run.
