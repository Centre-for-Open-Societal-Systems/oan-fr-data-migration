# Farmer Registry Migration — Local Presentation Runbook

Date: 13 November 2026
Migration repository: `anteneh1621/farmer-registry-migration`
Tested commit: `8d6e819` plus the local Gen1 compatibility fix described below

## Safety boundary

The scripted baseline demonstration is isolated:

- Source: `farmer_registry_migration_demo_20261113`, an isolated clone inside `farmer_registry_gen1-db-1`
- Target: `fr-migration-target`, a disposable PostgreSQL container
- Master Data: `fr-migration-mds`, a local stand-in loaded from the pinned country pack
- Network: `fr-migration`
- Installed Gen1 database: not modified by the baseline commands below
- Existing Gen2 database: not modified by the baseline commands below
- Production: not connected

The optional live UI demonstration uses the installed local Gen1 and Gen2 databases. That path is described separately under “Live Gen1 → Gen2 demo” and is only for the local presentation environment.

The fixture records use IDs beginning with `900000` and names beginning with `Presentation` or `PRESENTATION`.


## Presentation sequence

Run from this repository:

```bash
./run.sh setup
./run.sh test
./run.sh dry-run
./run.sh fresh
./run.sh summary
```

What each command demonstrates:

1. `setup` creates the isolated Master Data service and empty Gen2 target.
2. `test` runs the migration unit tests.
3. `dry-run` performs the full transformation and database load, then rolls back every target batch.
4. `fresh` resets only the disposable target, performs the local migration, and immediately runs verification.
5. `summary` displays the latest migration and verification results.

## Recreating the synthetic source fixture

The demo source database is a clone of the installed Gen1 database with clearly labelled synthetic records added. It is separate from the installed Gen1 database. To recreate it from scratch on the local Gen1 container:

```bash
docker exec farmer_registry_gen1-db-1 psql -U openg2p -d postgres \
  -c "DROP DATABASE IF EXISTS farmer_registry_migration_demo_20261113" \
  -c "CREATE DATABASE farmer_registry_migration_demo_20261113 TEMPLATE farmer_registry_gen1"

docker exec -i farmer_registry_gen1-db-1 psql -U openg2p \
  -d farmer_registry_migration_demo_20261113 -v ON_ERROR_STOP=1 \
  < dev/fixtures/presentation_fixture.sql
```

This drops and recreates only the demo database. The installed `farmer_registry_gen1` database is not modified.

## Results obtained

### Automated tests

- 16 passed
- 0 failed

### Full dry run

- 2 farmers selected
- 3 people read including household members
- 1 batch completed
- 0 failed batches
- 2 households prepared
- 3 farmers prepared
- 3 household-member records prepared
- 2 phone records prepared
- 2 land records prepared
- 2 crop records prepared
- All target writes rolled back

### Local final-move test

- 2 households loaded
- 3 farmers loaded
- 3 household-member records loaded
- 2 phone records loaded
- 2 land records loaded
- 2 crop records loaded
- 3 functional-ID requests queued
- 105 completion-score requests queued

### Verification

- Verdict: **PASS**
- 76 checks passed
- 0 checks failed
- 2 warnings
- 375 values compared across 148 columns
- 0 value differences

The two warnings are expected for this synthetic fixture: it intentionally has no Gen1 geographic P-codes, so migrated Farmer and Household records have no location.

### Abel and Yonatan demonstration

Two additional farmers were created in the Gen1 demo clone and migrated into the disposable Gen2 target:

- Abel Tesfaye (`PRES-FR-003`, Odoo id `900006`)
- Yonatan Bekele (`PRES-FR-004`, Odoo id `900007`)
- One shared household, one phone, one land parcel, and one crop each

Commands:

```bash
./run.sh dry-run --ids 900006 900007
./run.sh reset
./run.sh migrate --ids 900006 900007
./run.sh verify --ids 900006 900007
```

Results:

- 1 household, 2 farmers, 2 household members, 2 phones, 2 lands, 2 crops migrated
- Verification: **PASS**
- 69 checks passed, 0 failed, 2 expected warnings
- 275 values compared in 148 columns; 0 differ
- 1 issue: Yonatan's `renter` land ownership value has no matching Master Data code

The Gen2 target now contains exactly Abel Tesfaye and Yonatan Bekele. Their run reports are in `presentation-evidence/abel-yonatan/`.

### Showing the records in the local UIs

The local UIs use different databases from the migration test:

- Gen1 UI (`http://localhost:8075`) uses `farmer_registry_gen1`
- Gen2 UI (`http://localhost:3001`) uses `farmer_registry_db`

To make the demonstration visible:

- Abel and Yonatan were added to `farmer_registry_gen1`; refresh the Gen1 UI.
- Abel and Yonatan were migrated into `farmer_registry_db`; refresh the Gen2 UI.

The local Gen2 UI database is on an older schema than the migration image. The migration required the additive column changes in `presentation-evidence/ui-migration/gen2_schema_additions.sql`; existing data and columns were preserved. Verification was run against the exact-schema disposable target (`fr-migration-target`), which passed. The older UI database stores latitude/longitude as text, so the script's verification comparison is not compatible with it without a Gen2 upgrade.

## Live Gen1 → Gen2 demo

This is the presentation flow to use when the audience should see a farmer created in the live Gen1 UI and then migrated into the live Gen2 UI.

### The migration approach

Explain the migration in six steps:

1. **Read Gen1, read-only.** `farmer_profile/source.py` selects the chosen farmers and reads their whole households, memberships, phones, lands, and crops. The source connection is set read-only.
2. **Map and validate.** `fieldmap.py` says where every Gen1 field goes. `codes.py` maps old values to Gen2 codes, `geo.py` maps old locations to P-codes, and Master Data is checked before anything is written. Values that cannot be mapped become issues, not silent guesses.
3. **Transform and prepare.** `transform.py` builds the Gen2 rows. The registry’s own hooks run in memory so required values and defaults are applied before loading.
4. **Load transactionally in batches.** `load.py` uses temporary tables and `INSERT`/`COPY` into the Gen2 register tables. Each batch is committed only if its writes succeed. Existing records are detected by internal record ID, so rerunning is idempotent: it adds only what is missing and never duplicates.
5. **Queue generated work.** After the load, the registry queues any functional-ID generation it still needs and computes completion scores. Record history is not migrated; a migrated record’s history starts empty.
6. **Verify.** `verify.py` compares source values, target rows, and Master Data. The verification is a separate command so the audience can see that migration and checking are independent.

The key safety message: **read-only source, transactional batch loads, idempotent records, explicit issues, separate verification.**

### Live demo steps

Create the source farmer in the live Gen1 database only:

```bash
docker exec -i farmer_registry_gen1-db-1 psql -U openg2p \
  -d farmer_registry_gen1 -v ON_ERROR_STOP=1 \
  < dev/fixtures/abiyot_live_fixture.sql
```

The target database must be reachable from the migration container:

```bash
docker network connect fr-migration farmer-registry-postgres
```

Build the live source and target connection strings at runtime. Passwords are read from the containers and are not written to disk:

```bash
SRC_PASS=$(docker exec farmer_registry_gen1-db-1 printenv POSTGRES_PASSWORD)
TARGET_PASS=$(docker inspect farmer-registry-staff-api \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed -n 's/^REGISTRY_STAFF_PORTAL_API_DB_PASSWORD=//p' | head -1)

SOURCE_DSN=$(SRC_PASS="$SRC_PASS" python3 -c \
  'import os,urllib.parse; print("postgresql://openg2p:%s@farmer_registry_gen1-db-1:5432/farmer_registry_gen1" % urllib.parse.quote(os.environ["SRC_PASS"], safe=""))')
TARGET_DSN=$(TARGET_PASS="$TARGET_PASS" python3 -c \
  'import os,urllib.parse; print("postgresql+psycopg2://postgres:%s@farmer-registry-postgres:5432/farmer_registry_db" % urllib.parse.quote(os.environ["TARGET_PASS"], safe=""))')
```

Dry run first; every target write is rolled back:

```bash
SOURCE_DSN="$SOURCE_DSN" TARGET_DSN="$TARGET_DSN" \
  ./run.sh dry-run --ids 900011
```

Then perform the real migration:

```bash
SOURCE_DSN="$SOURCE_DSN" TARGET_DSN="$TARGET_DSN" \
  ./run.sh migrate --ids 900011
```

Clean up the temporary network attachment:

```bash
docker network disconnect fr-migration farmer-registry-postgres
```

### Live demo result

- Source: live Gen1 `farmer_registry_gen1`, Odoo id `900011`, `Abiyot Bekele`, `PRES-FR-006`
- Target: live Gen2 `farmer_registry_db`
- Dry run: `out/20261113-095429-migrate`, all writes rolled back
- Real run: `out/20261113-095452-migrate`
- Added: 1 household, 1 farmer, 1 household member, 1 phone, 1 land, 1 crop
- Gen2 result: `Abiyot Bekele Lemma`, `ACTIVE`, `PRES-FR-006`
- Reports and fixture: `presentation-evidence/live-demo/`

### What to say

“We create the farmer in Gen1, where the field team works. The migration reads that database read-only. It maps the Odoo fields and codes into the Gen2 model, validates them against Master Data, and writes the household in a transactional batch. Running it twice is safe because each record is matched by its internal ID. After the load, the registry queues any functional-ID generation it still needs and computes completion scores. Verification is a separate pass that compares the source and target, so the load is not marking its own homework.”

### Live demo limitation

The live Gen2 UI database is on an older schema than the migration image. It required the additive columns in `presentation-evidence/ui-migration/gen2_schema_additions.sql`, and its latitude/longitude columns are text. The migration load works and the records are visible, but `verify.py` cannot compare that older schema without a Gen2 upgrade. Verification still passes against the exact-schema disposable target.

## Issues correctly detected

The run reported five issues:

- Two crops were assigned to the farmer's first land because Gen1 does not identify their parcel.
- One standalone farmer was given a generated household.
- One crop was skipped because its farmer has no land.
- One land ownership value was dropped because the target Master Data has no matching code.

These are evidence that the exception reporting works. They are not approval to use the underlying rules in production.

## Blocking gaps before production approval

The current script does **not** implement the full approved final field mapping.

1. Livestock is not migrated.
2. Farm Inputs is not migrated.
3. Membership Details is not migrated.
4. Documents, farmer photos, and land-certificate files are not migrated.
5. Crops are assigned to the first land. The approved mapping requires evidence-based parcel assignment and quarantine when ambiguous.
6. Record history is not migrated.
7. The installed Gen1 database used initially contains no production farmer-profile data; an authorized production-like masked extract is required for volume and data-quality rehearsal.
8. Five source fields remain `Not reviewed` in `fieldmap.py`; production approval requires zero.
9. The report lists 38 Gen1 fields and 80 Gen2 columns as `Not migrated yet`; these must be reconciled against the approved mapping.

## Compatibility fix found during testing

The installed Gen1 schema has no `res_partner.is_duplicated` column, while the script queried it unconditionally. The local patch changes that select expression to:

```sql
NULL::boolean AS is_duplicated
```

After the patch, all 16 unit tests passed and the dry-run/final-move/verification sequence completed.

## Evidence folder

The `presentation-evidence/` directory contains:

- `dry-run/`: summary, JSON summary, issues CSV, and migration report
- `final-move/`: summary, JSON summary, issues CSV, and migration report
- `verification/`: summary, JSON summary, differences CSV, and verification report
- `abel-yonatan/`: the same reports for the two named farmers, plus their fixture SQL
- `ui-migration/`: the run that loaded Abel and Yonatan into the local Gen2 UI database, plus the additive schema SQL
- `live-demo/`: live Gen1 → live Gen2 dry-run and migration reports for Abiyot Bekele, plus the live fixture and checks
- `diagrams/`: editable `migration-flow.svg` plus deck-ready `migration-flow.png` (3200×1800) and `migration-flow-1600.png` (1600×900)
- `Gen1-to-Gen2-Data-Migration-Mapping_FINAL.xlsx`: approved field mapping
- `Farmer-Registry-Migration-Project-Plan_FINAL.xlsx`: project plan
- `dev/fixtures/presentation_fixture.sql`: synthetic source records used for this test
- `gen1-compatibility-fix.patch`: the `is_duplicated` schema compatibility fix
- `docs/presentation-runbook.md`: this document

The same contents are packaged as `Farmer-Registry-Migration-Presentation-Evidence.zip` in the repository root. Use the Excel reports for the meeting and the text summaries for command-line evidence.

## Final status

- Unit tests: 16 passed, 0 failed
- Full dry run: completed, every target write rolled back
- Local final-move test: completed against the disposable target only
- Verification: PASS, 76 checks passed, 0 failed, 2 expected warnings, 0 value differences
- Production: untouched
- Installed Gen1 and existing Gen2: modified only by the optional live UI demo described above; the baseline scripted runs use the demo clone and disposable target

The migration is **not approved for production** until the blocking gaps above are resolved and a production-like masked Gen1 extract has been rehearsed.

