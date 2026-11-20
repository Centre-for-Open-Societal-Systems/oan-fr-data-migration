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
- `ON CONFLICT DO NOTHING` will prevent duplicate insertion.
- Dry-run mode will execute the migration and roll back all changes.
- Invalid and unmapped values will be recorded in issue reports.
- Every run will produce logs, summaries, CSV details and formatted Excel reports using `openpyxl`.
- The pipeline will be tested with `pytest` before production execution.
