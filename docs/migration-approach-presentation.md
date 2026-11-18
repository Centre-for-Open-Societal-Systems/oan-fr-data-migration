# Gen 1 to Gen 2 Migration Approach

## 10-Minute Technical Presentation

## Slide 1 — Objective and scope

**Time: 1 minute**

### Key points

- Migrate Farmer Profile data from Gen1 Odoo to the Gen2 Farmer Registry.
- Preserve identities, relationships and important business data.
- Make the migration safe, repeatable and auditable.
- Apply Gen2 validation and business rules instead of copying tables directly.

### Speaker notes

Our objective is to migrate Farmer Profile data from the Gen1 Odoo PostgreSQL database into the Gen2 Farmer Registry. The systems have different schemas, identifiers, relationships and reference values, so we propose using a controlled extract-transform-load pipeline rather than a direct table copy.

---

## Slide 2 — High-level architecture

**Time: 1 minute**

```text
Gen1 Odoo/PostgreSQL
        │ Read-only SQL
        ▼
Python extraction
        ▼
Transformation and mapping
        ├── Master Data validation
        ├── Deterministic UUID generation
        └── Relationship reconstruction
        ▼
Gen2 model preparation
        ▼
PostgreSQL temporary tables
        ▼
Gen2 register tables
        ▼
Independent verification and reports
```

### Speaker notes

The pipeline reads Gen1 using parameterized PostgreSQL queries. Python transforms the records into the Gen2 structure and validates controlled values against Master Data. The records are then prepared through the installed Gen2 models and loaded transactionally. A separate process verifies the result.

---

## Slide 3 — Extract and transform

**Time: 1.5 minutes**

### Tools

- Python
- `psycopg2`
- PostgreSQL
- Controlled mapping dictionaries

### Process

- Read Gen1 without updating or deleting source records.
- Extract farmers with complete household and related records.
- Normalize names and dates.
- Convert yes/no selections into Boolean values.
- Convert multi-value data into JSON where supported.
- Recalculate derived values.
- Report unsupported or ambiguous values.

### Speaker notes

Gen1 is treated as read-only. We extract farmers together with their households, members, registration IDs, phones, lands and crops. Python then applies explicit field and code mappings. Values that cannot be mapped are recorded as issues instead of being silently discarded.

---

## Slide 4 — IDs and relationships

**Time: 1 minute**

### Key points

- Generate deterministic UUID5 identifiers.
- The same Gen1 record always receives the same Gen2 ID.
- Rebuild relationships using `link_internal_record_id`.
- Prepare parents before their child records.
- Keep reruns consistent and prevent duplicate identities.

### Speaker notes

Gen1 mainly uses integer Odoo IDs, while Gen2 uses UUID-formatted internal identifiers. We generate deterministic UUID5 values from the source model and record ID. These stable identifiers let us reconstruct Household, Farmer and child-record relationships consistently across repeated runs.

---

## Slide 5 — Master Data and Gen2 validation

**Time: 1 minute**

### Tools

- Gen2 Master Data Service
- Ethiopia country pack for isolated local testing
- SQLAlchemy
- Installed Gen2 models

### Validation

- Check governed codes and geographic values.
- Reject or report unknown reference values.
- Run Gen2 model hooks in memory.
- Apply defaults and derive record names and search text.

### Speaker notes

Gen2 expects controlled codes rather than arbitrary display labels. The migration validates crops, seasons, languages, geographic locations and other governed values against Master Data. It also runs the installed Gen2 model hooks so migrated records receive the same defaults and derived fields as records created through Gen2.

---

## Slide 6 — Transactional loading

**Time: 1.5 minutes**

### Tools

- PostgreSQL `COPY`
- Temporary staging tables
- SQL transactions
- `INSERT ... ON CONFLICT DO NOTHING`

```sql
COPY temporary_table FROM STDIN;

INSERT INTO target_table
SELECT ... FROM temporary_table
ON CONFLICT (internal_record_id) DO NOTHING;
```

### Safety behaviour

- Load records in parent-before-child order.
- Commit only when the complete batch succeeds.
- Roll back a failed batch.
- Use the same process for dry runs, followed by rollback.
- Allow safe reruns without duplicate insertion.

### Speaker notes

Prepared rows are copied into temporary PostgreSQL tables and inserted into the final Gen2 tables. Each batch runs in one transaction. Deterministic identifiers and conflict handling make the migration idempotent, so rerunning a batch does not create duplicate records.

---

## Slide 7 — Verification and evidence

**Time: 1 minute**

### Tools

- Python
- PostgreSQL and SQLAlchemy
- `openpyxl`
- `pytest`

### Verification checks

- Record counts
- Important field values
- Source and target identifiers
- Parent-child relationships
- Household-head consistency
- Calculated land totals

### Outputs

- Execution logs
- Summary files
- CSV issue details
- Excel migration reports
- Excel verification reports

### Speaker notes

Verification runs separately from migration so the loader is not marking its own work. It reconciles source and target records and produces auditable reports. Automated tests cover transformation rules, deterministic IDs and SQL-loading behaviour.

---

## Slide 8 — Current coverage and remaining work

**Time: 1 minute**

### Current pipeline coverage

- Household
- Farmer
- HouseholdMember
- FarmerPhone
- Land
- Crop

### Remaining work

- Align the Crop parent relationship with the current Gen2 configuration.
- Implement or formally exclude Livestock.
- Implement or formally exclude FarmInputs.
- Implement or formally exclude MembershipDetails.
- Approve the remaining reference-code and exception rules.
- Perform a complete staging migration using representative Gen1 data.

### Speaker notes

The core migration flow is operational. One known correction remains: the live Gen2 configuration defines Crop as a child of Farmer, while the current transformer still links Crop through Land. The remaining domains must also be completed or formally excluded before production approval.

---

## Slide 9 — Conclusion and requested review

**Time: 1 minute**

### Summary

- Read-only access to Gen1
- Explicit transformation rules
- Master Data validation
- Deterministic relationship reconstruction
- Transactional and idempotent loading
- Independent verification
- Auditable reports

### Review requested from the technical team

- Confirm field mappings and parent-child relationships.
- Approve reference-code mappings.
- Confirm exception and quarantine rules.
- Agree on the remaining migration scope.
- Approve a full staging rehearsal before production cutover.

### Closing statement

The proposed approach provides a controlled and repeatable migration rather than a direct database copy. Before production cutover, we need technical approval of the mappings and remaining scope, followed by a successful full staging migration and independent verification.
