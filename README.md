# Farmer profile to Farmer registry migration

Moves the farmer profile registry (Odoo, `g2p_ati`) into the Farmer registry
(OpenG2P Registry 1.2, `farmer-registry`): farmers, households and their
members, phone numbers, lands and crops. The migration reads farmer profile's
database read-only and writes the registry's register tables directly through
the registry's own models. It does not go through the intake forms, which need
two approvals per record.

This repository holds only the migration. It runs on the registry that is
already deployed: its image is built on the registry's staff-api image, which
has the Farmer extension installed. All it takes is addresses: farmer
profile's database, the registry's database, and the Master Data Service.

| Program | What it does |
|---|---|
| `migrate.py` | Migrates in batches, queues what the registry generates afterwards, writes the log and the Excel report |
| `verify.py` | Checks the registry against farmer profile and writes its own log and Excel report; exits 1 if a check fails |

## Master Data decides what is migrated

Code lists and locations belong to the Master Data Service. The registry
validates coded values against it and builds location hierarchies from it. So
before a run writes anything, it loads every code list and every location from
the Master Data Service, through the registry's own client
(`openg2p_registry_core.helpers.master_data`). Then:

- **Coded values.** A value is migrated only if Master Data has it in that
  column's code list. Which code list a column uses comes from the registry's
  own form metadata (`g2p_register_sections`). A value Master Data doesn't have
  is left empty, and reported as `dropped: not in Master Data (<LIST>)`. A list
  column, such as income sources, keeps the values Master Data has and drops
  the rest.
- **Locations.** A location is migrated only if its P-code is in Master Data,
  and its hierarchy is built from Master Data. If the kebele isn't there, the
  record is placed at its woreda, then zone, then region. A land's kebele that
  Master Data doesn't have is left empty.
- **Verify** checks every coded value and every location in the registry
  against Master Data again.

A record migrated while a value was missing keeps that field empty. A rerun
skips records that are already there, so if Master Data gains the value later,
the field isn't filled in.

The settings are the ones the chart's Jobs use:

| Setting | Value |
|---|---|
| `MDS_API_URL` | The Master Data Service, e.g. `http://commons-services-master-data-api` |
| `MDS_TOKEN_URL` | The Keycloak token endpoint |
| `MDS_CLIENT_ID` / `MDS_CLIENT_SECRET` | The registry's confidential client |

Without `MDS_API_URL`, a run refuses to start. The exception is `--pack-only`,
which checks against the country pack instead, for local tests only.
`dev/fake-mds.sh` starts a local stand-in that serves the pack, and it can
leave values out to show what happens to them:

```sh
dev/fake-mds.sh CROP_TEFF,ET04041110        # Master Data without teff and one kebele
MDS_API_URL=http://fr-migration-mds:8000 ./run.sh migrate --all
```

## What a run leaves behind

Every run writes a new folder under the report directory (`/out` in the image,
`out/` locally), named `<UTC time>-migrate` or `<UTC time>-verify`.
Nothing is overwritten, so the folders are the record of every run.

| File | Contents |
|---|---|
| `migrate.log` / `verify.log` | The log, also printed: settings (passwords masked), every batch with its counts and time, errors with their traceback, and the summary |
| `summary.txt` | The summary printed at the end of the run. For a migration: records read, added and already there; farmer profile fields per status, and how many hold data; Gen2 columns per status, and how many are filled; what was queued after the load; the fields holding data that didn't reach Gen2; the issues by kind. For a verification: the verdict and every check that didn't pass |
| `migration-report.xlsx` | Summary, Farmer profile fields, Gen2 columns, Issues summary, Issues, Batches |
| `issues.csv` | Every issue: a value left out, a record not migrated, or something worth a look |
| `verify-report.xlsx` | Summary with the verdict, Checks, Columns (values compared per column), Differences |
| `differences.csv` | Every value that differs |
| `summary.json` | The counts, for scripts |

### The field report

The script itself works out every number in `summary.txt` and in the workbook from the two
databases. A dry run reports the same, counted from the rows it would have
written.

`migration-report.xlsx` answers where each field went:

- **Farmer profile fields** lists every field of the farmer profile models
  read. The list is read from Odoo's own field table, so it shows what the
  database has, not what the code expects. For each field it gives its status
  and Gen2 column, and how many of the migrated records hold a value.

  | Status | Meaning |
  |---|---|
  | Migrated | The value is carried to a Gen2 column |
  | Recomputed in Gen2 | Gen2 computes the value again from migrated data |
  | Not migrated yet | Gen2 has a column for it, but this migration doesn't write it yet |
  | No Gen2 column | Gen2 has nowhere to put it, so it can't be added |
  | Not carried: Odoo workflow | Review, change-request, consent or data-sharing state of the old system |
  | Odoo technical | Odoo's own bookkeeping |
  | Not reviewed | A field the field map doesn't know yet. It should be 0: when a new field appears, add it to the map |

- **Gen2 columns** lists every column of the registers in scope, where its
  value comes from, and how many migrated records hold a value.

  | Status | Meaning |
  |---|---|
  | Filled from farmer profile | Taken from a farmer profile field |
  | Derived during migration | Computed by the migration, e.g. Ethiopian-calendar dates, land totals, locations |
  | Set by the registry | Filled by the registry's insert hooks, e.g. `record_name`, `search_text` |
  | Generated after the load | Generated by the registry's workers after the load (below) |
  | Not migrated yet | The column exists, but this migration doesn't write it yet |
  | Not in farmer profile | Farmer profile has no data for it, so it stays empty |

The statuses come from `farmer_profile/fieldmap.py`, which states what happens
to each field. `farmer_profile/transform.py` does the work, so keep the two in
step. `tests/test_fieldmap.py` checks that every Gen2 column the map names
exists.

### Generated after the load

When a record is approved, the registry queues work for its workers. At the
end of a run (not a dry run, and not one with a failed batch), the migration
queues the same work for every migrated record that doesn't have it yet:

- **Functional ids, Farmer and Household:** a row in
  `g2p_functional_id_generation_queue` and a `TEMP-` placeholder id, exactly
  as the registry's approval does. The ID worker then allocates the real id.
  A farmer that already has a farmer profile `farmer_id` keeps it.
- **Completion scores, Farmer:** one `g2p_completion_score_computation_queue`
  row per section, about 35 rows per farmer. Use `--no-completion-scores` to
  leave them out.

Record history (`g2p_register_history_*`) is not written: a migrated record's
history starts empty.

## How it works

1. **Select.** `source.py` picks the farmers in scope: `res_partner` rows that
   are registrants, are not groups, and are active. They are ordered by
   household, so a batch holds whole households. Archived partners are not
   migrated.
2. **Read.** For each batch, it reads those farmers with every member of
   their households, their ids, income sources, phone numbers, lands, crops
   and enumerators.
3. **Transform.** `transform.py` turns the rows into register rows:
   - **Codes.** Odoo values go through the registry's code lists from the
     country pack (`openg2p-data`, at the commit the registry's db-seed pins:
     `OPENG2P_DATA_REF` in the Dockerfile).
   - **Locations.** Old location codes become P-codes through the pack's
     `id_map.csv`, after restoring the leading zeros Odoo dropped. A location
     that doesn't map falls back to the next level up, and this is reported.
   - **Issues.** A value that can't be carried over is left empty and recorded
     as an issue. Nothing is guessed.
4. **Write.** `load.py` writes each batch in one transaction, through the
   registry's models, so the registry's insert hooks run.
   - **Record ids** are uuid5 of the Odoo record (`farmer-profile/<kind>/<odoo id>`).
     A record that is already there is left alone, so a rerun only adds what's
     missing.
   - **After a failed batch,** the batch is rolled back. Run the same command
     again: the earlier batches are found and skipped.
5. **Finalize.** `finalize.py` queues the functional ids and completion
   scores described above.
6. **Report.** `inventory.py` counts the values on both sides, and `report.py`
   writes the workbook.

### Decisions in the transform

These are reported per record, so each can be revisited:

- **Crops and lands.** A crop is linked to a farmer in farmer profile but to a
  land in Gen2. It goes on the farmer's first land, and this is reported as a
  "check" issue. A crop of a farmer with no land is not migrated: it is
  reported as "skipped".
- **Households.** A farmer in no household gets a household of their own, as
  its head.
- **Household head.** The head is taken from the `Head` membership. If there
  isn't exactly one, it is the member marked household head, else the first
  member.
- **Local names.** Gen2 keeps one set of local names. The Amharic names are
  kept, or else the names in the farmer's own language (`*_other`).
- **Record status.** Every Odoo state is migrated, kept in `legacy_state`. A
  disabled farmer is `INACTIVE`, every other one is `ACTIVE`.
- **Foundational id.** It is the UID (FIN), else the FAN.
- **Crop disease.** The registry's `INFESTATION_AGENT` list is coarser than
  farmer profile's diseases. A disease without an agent of its own becomes
  `AGENT_OTHER`, and its name is reported.

### Not migrated yet

These have Gen2 registers or columns:

- Livestock
- Farm inputs
- Membership details (cooperatives, clusters)
- Documents, the farmer's photo, and land certificates (files)

They show as "Not migrated yet" in the report, with how many records hold
data.

## Run it locally

You need:

- **The registry.** This repository doesn't contain it. Give one of these:
  - `REGISTRY_IMAGE`: a registry staff-api image with the Farmer extension
    installed, or
  - `REGISTRY_REPO`: a checkout of `farmer-registry`. The default is
    `~/farmer-registry-develop`. The scripts use the platform image it names,
    with its extension mounted. `dev/target-db.sh` also takes the registry's
    metadata from it, to build a local registry database.
- **Farmer profile.** The farmer profile copy in the `fp-db` container. Set
  `SOURCE_DB` to pick the database; the default is `odk_a`.
- **The country pack.** `~/openg2p-data` checked out at `OPENG2P_DATA_REF`
  (see the Dockerfile).
- **Settings, optional.** Copy `.env.example` to `.env`. `run.sh` and `dev/*.sh`
  read it; settings exported in the shell win. Without `SOURCE_DSN` and
  `TARGET_DSN`, the scripts use the local containers above.

```sh
dev/target-db.sh reset                    # an empty registry database (container fr-migration-target)
dev/fake-mds.sh                           # a local Master Data (or set MDS_API_URL to a real one)
export MDS_API_URL=http://fr-migration-mds:8000
./run.sh migrate --all --dry-run          # everything, rolled back: read summary.txt
./run.sh migrate --limit 10 --complete    # 10 farmers with a household, land and crop
./run.sh migrate --all --batch-size 500   # every farmer
./run.sh verify                           # check everything
dev/test.sh                               # the tests
# without any Master Data: add --pack-only to migrate and verify
```

`run.sh` mounts this code into the registry's image, so no image is built
locally. It installs `openpyxl` once into the `fr-migration-pydeps` volume.

## Deploy

Build the image on the staff-api image the target registry runs, so the
models match. It adds this code, nothing of the registry:

```sh
docker build --build-arg REGISTRY_IMAGE=<the registry's staff-api image:tag> \
  -t <registry>/farmer-profile-migration:<tag> .
```

Then run it as a one-off Job: `deploy/job.yaml` has the steps. Or run it
with Docker, using the `.env`:

```sh
docker run --rm --env-file .env -v "$PWD/out:/out" <name>:<tag> migrate.py --all --dry-run
docker run --rm --env-file .env -v "$PWD/out:/out" <name>:<tag> migrate.py --all
docker run --rm --env-file .env -v "$PWD/out:/out" <name>:<tag> verify.py
```

It needs these settings. `.env.example` lists them all; copy it to `.env` and
fill it in:

| Setting | Value |
|---|---|
| `SOURCE_DSN` | Farmer profile's Odoo database, in libpq form (`host=... dbname=... user=... password=...`). A read-only user is best. |
| `TARGET_DSN` | The registry's database, in SQLAlchemy form (`postgresql+psycopg2://user:password@host:5432/db`) |
| `MDS_API_URL`, `MDS_TOKEN_URL`, `MDS_CLIENT_ID`, `MDS_CLIENT_SECRET` | The Master Data Service the registry uses. See "Master Data decides what is migrated" above. |
| `/out` | A volume for the run folders |

Run these in order:

1. `migrate.py --limit 100 --dry-run`: writes each batch and rolls it back.
   Read the report and the issues.
2. `migrate.py --all`
3. `verify.py`
4. Start the registry's workers, so they allocate the functional ids and
   compute the scores.

Options:

| Option | Effect |
|---|---|
| `--batch-size N` | Farmers per transaction. The default is 500. |
| `--keep-going` | Logs a failed batch and continues. By default the run stops. |
| `--no-finalize` | Doesn't queue the functional ids and scores |
| `--finalize-only` | Only queues them |
| `--ids ...` | Migrates only these Odoo partner ids |
