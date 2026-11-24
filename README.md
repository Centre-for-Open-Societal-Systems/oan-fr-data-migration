# Farmer Profile to Farmer Registry Migration

Moves the farmer profile registry (Odoo, `g2p_ati`) into the Farmer registry
(OpenG2P Registry 1.2, `farmer-registry`): farmers, households and their
members, phone numbers, lands and crops. The migration reads farmer profile's
database read-only and writes the registry's register tables directly through
the registry's own models. It does not go through the intake forms, which need
two approvals per record.

> **Safety model:** the source connection is explicitly read-only, target writes
> are transactional and idempotent, dry runs are rolled back, and an independent
> verification command compares migrated records with the source.

This repository holds only the migration. It runs on the registry that is
already deployed: its image is built on the registry's staff-api image, which
has the Farmer extension installed. All it takes is addresses: farmer
profile's database, the registry's database, and the Master Data Service.

| Program | What it does |
|---|---|
| `migrate.py` | Migrates in batches: Python prepares the rows, SQL loads them, or `--sql-out` writes them to a file to review and run with psql. Queues what the registry generates afterwards. Writes the log, summary and Excel report. |
| `verify.py` | Checks the registry against farmer profile and writes its own log and Excel report; exits 1 if a check fails |

## Quick start (local)

```sh
cd ~/farmer-registry-migration-db-to-db

./run.sh setup        # once: starts the local Master Data and an empty registry database
./run.sh dry-run      # migrate everything, then roll back: nothing is kept
./run.sh migrate      # migrate everything for real
./run.sh verify       # check the result
```

The other steps:

```sh
./run.sh sql          # write migration.sql instead of loading
./run.sh apply        # run the latest migration.sql on the registry database
./run.sh fresh        # reset + migrate + verify in one go
./run.sh status       # how far the migration is, and what is open
./run.sh summary      # show the latest migrate and verify summaries again
./run.sh report       # open the latest Excel report
./run.sh reset        # empty the registry database
./run.sh test         # run the tests
./run.sh help         # list all of these
```

- **Picking farmers:** every farmer is migrated unless you pick some, e.g.
  `./run.sh dry-run --limit 10` or `./run.sh migrate --ids 12 40`. Options of
  `migrate.py`, such as `--workers 2` or `--batch-size 200`, pass straight
  through.
- **No exports needed:** if `MDS_API_URL` isn't set, `run.sh` uses the local
  Master Data that `setup` starts. Settings in `.env` (see `.env.example`) are
  also read.
- **Latest run:** `apply` and `summary` pick the latest run folder for you.
- **Low-level runner:** `dev/py.sh` runs `migrate.py` or `verify.py` with any
  arguments, e.g. `dev/py.sh migrate --all --dry-run`.

What you need on the machine is under "Run it locally" below. For a server,
see "Deploy".

## Files

### What's in this repository

```
run.sh                    the local commands: setup, dry-run, migrate, sql, apply, verify, ...
migrate.py                the migration: reads, transforms, checks, loads (or writes migration.sql), reports
verify.py                 the verification: checks the registry against farmer profile and Master Data
farmer_profile/           the migration's code
  source.py                 reads farmer profile (Odoo) read-only: which farmers, and all their data
  transform.py              Odoo rows -> registry rows; every value it can't carry over becomes an issue
  codes.py                  Odoo values -> registry codes (gender, crops, income, land, ...)
  geo.py                    old location codes -> P-codes, and their hierarchy
  masterdata.py             loads Master Data's code lists and locations; only values it has are kept
  load.py                   runs the registry's hooks in memory, then COPY + INSERT, or writes migration.sql
  finalize.py               queues the functional ids and completion scores the registry generates
  fieldmap.py               what happens to every farmer profile field, where every registry column comes from
  inventory.py              counts, on both sides, how many records hold each field (for the report)
  report.py                 writes the Excel reports
  summary.py                writes summary.txt
  runlog.py                 the run folder and the log
  verification.py           the checks verify.py runs
  tracking.py               the audit and progress tables: what a rerun resumes from
tests/                    tests (./run.sh test)
Dockerfile                the job image, built on the registry's own staff-api image
deploy/job.yaml           runs the image as a one-off Kubernetes Job
deploy/migration-schema.sql  the audit and progress tables
docs/                     technical migration approach
.env.example              every setting, to copy to .env (.env is never committed)
dev/                      local helpers, used by run.sh
  py.sh                     runs migrate.py or verify.py in the registry's image
  env.sh                    shared settings: which registry, which pack, .env
  target-db.sh              a local, empty registry database (container fr-migration-target)
  create_schema.py          creates the registry's tables in it
  fake-mds.sh, fake_mds.py  a local stand-in for the Master Data Service (container fr-migration-mds)
  test.sh                   runs the tests in the registry's image
```

### What it creates

**A folder per run,** in `out/` locally (`/out` in the image). It's named
`<UTC time>-migrate` or `<UTC time>-verify`, and nothing is overwritten, so
the folders are the record of every run. `out/` is not committed.

| File | Run | Contents |
|---|---|---|
| `summary.txt` | both | The summary printed at the end of the run. For a migration: records read, added and already there; farmer profile fields per status, and how many hold data; registry columns per status, and how many are filled; what was queued after the load; the data that didn't reach the registry; the issues by kind. For a verification: the verdict and every check that didn't pass. |
| `migrate.log` / `verify.log` | both | The full log, also printed: settings (passwords masked), every batch with its counts and time, errors with their traceback, and the summary |
| `summary.json` | both | The same counts, for scripts |
| `migration-report.xlsx` | migrate | Sheets: Summary, Failed households, Changed in Gen1, Issues summary, Issues, Runs, Batches, and the mapping (see "Reports" below) |
| `issues.csv` | migrate | Every issue, of every run so far: a household that failed or has changed, a value left out, a record not migrated, or something worth a look. A dry run lists its own only |
| `migration.sql` | migrate with `sql` / `--sql-out` | The load as one SQL transaction, to review and run with psql (`./run.sh apply` locally) |
| `verify-report.xlsx` | verify | Sheets: Summary with the verdict, Checks, Columns (values compared per column), Differences |
| `differences.csv` | verify | Every value that differs |

**In the registry database,** written by `migrate` or `apply`, never by a dry
run, `sql` or `verify`:

- **The records:** households, farmers, household members, phone numbers,
  lands and crops in their `g2p_register_*` tables. Each one is marked
  `created_by = 'farmer-profile-migration'`, and its id comes from its Odoo
  record.
- **Progress and issues:** the tables of the `migration` schema. See "Stopping, resuming
  and fixing" below.
- **Queued work for the registry's workers:** rows in
  `g2p_functional_id_generation_queue` (farmer and household ids) and
  `g2p_completion_score_computation_queue` (farmer completion scores).

Farmer profile is only ever read.

**Locally, in Docker,** set up by `./run.sh setup`:

| What | Name | For |
|---|---|---|
| Container | `fr-migration-target` | The local registry database (Postgres, port 55440). `./run.sh reset` empties it. |
| Container | `fr-migration-mds` | The local Master Data stand-in |
| Network | `fr-migration` | Joins them. The `fp-db` farmer profile container is attached to it. |
| Volume | `fr-migration-pydeps` | `openpyxl` and `pytest`, installed once |

To remove all of it:

```sh
docker rm -f fr-migration-target fr-migration-mds
docker network disconnect fr-migration fp-db
docker network rm fr-migration
docker volume rm fr-migration-pydeps
```

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
skips households that are already there, so if Master Data gains the value
later, the field isn't filled in.

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
./run.sh migrate
```

## Stopping, resuming and fixing

**The household is migrated whole or not at all:** the household, its members, and
their phones, lands and crops. A farmer in no household is one of their own.
Households that share a member go together. Batches are a matter of speed only.

**To go on after a stop, a crash or a fix, run the same command again.** What is
already in is skipped. Progress is written in the transaction that writes the
records, so the two can't disagree, whenever the run is killed.

| It ended with | What to do |
|---|---|
| Exit 0 | Everything loaded. Run `verify` |
| Exit 3: some households failed | The rest is in. Fix them in farmer profile (sheet "Failed households") and run again: only they are tried again |
| Exit 1: stopped early | Read why at the top of the summary, then run again |
| Killed | Run again |
| "another migration run is active" | Only one run works at a time. Wait for it |

What happens to each household:

| On a run, it is | Then |
|---|---|
| new, or failed before | migrated |
| already in, the same in farmer profile | skipped, without preparing it again |
| already in, **changed** in farmer profile since | **reported, not touched.** Correct it in the registry |
| in the registry from before these tables existed | adopted, if all its records are there; reported if only some are |

> **Fix what a dry run reports before the real load.** Once a household is in, a
> fix in farmer profile, a new land or a new member does not reach the registry:
> the household is reported as changed. Completely new households still load.

Kinds of issue: `failed` (household left out), `changed` (not touched), `skipped`
(a record not migrated), `dropped` (a value left out), `check` (migrated, worth a
look). Each is kept once, `OPEN` until a run finds it gone, then `RESOLVED`.

What stops a run: a database that stays away after three more tries, a table or
column that is missing, a worker process that dies twice, `--max-failures`
households failing in one run (100, in case they all have one cause), or
`SIGTERM`/Ctrl-C (it finishes its batch first). A database that is away never
marks a household as failed.

**Another source is refused.** The run remembers farmer profile's own
`database.uuid`. Another database may use the same Odoo ids for other people. If
it really is the same data (Odoo gives a copy a new uuid), confirm with
`--accept-source <uuid>`.

**The tables** are in the schema `migration` of the registry's database
(`deploy/migration-schema.sql`): `run`, `household_progress`, `migrated_record`,
`issue`. A run creates them if it may; otherwise a DBA runs the file. They hold
personal data: give them the access rules of the register tables. A dry run
doesn't write them. For example, what is open:

```sql
SELECT severity, entity, odoo_id, field, value, reason
  FROM migration.issue WHERE status = 'OPEN' ORDER BY severity;
```

`TARGET_DSN` must reach Postgres directly, not through PgBouncer in transaction
mode: the lock that allows one run at a time is a session lock.

**Not covered:** the same person as two records (twice in farmer profile, or in
the registry already through intake). The migration doesn't compare people.

## Reports

The files themselves are listed under "What it creates" above.

### The field report

The script itself works out every number in `summary.txt` and in the workbook from the two
databases. A dry run reports the same, counted from the rows it would have
written.

The workbook starts with what happened: Summary, Failed households, Changed in
Gen1, Issues and Runs. The last sheets are the mapping, which is the same in every
run but for the counts. They say what the migration covers, not how a run went.
The Summary lists only its exceptions: fields that hold data and don't reach Gen2.

- **Mapping - Gen1 fields** lists every field of the farmer profile models
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

- **Mapping - Gen2 columns** lists every column of the registers in scope, where its
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
end of a run (not a dry run, and not one that stopped early), the migration
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
   household. `units()` groups them into whole households, which are never split
   between batches. Archived partners are not migrated.
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
4. **Finish the rows.** `load.prepare` makes each row the registry's own
   model object and runs the registry's insert hooks on it, in memory:
   `search_text`, `record_name`, and the extension's readable names. These
   are the hooks the registry runs when it saves a record, and they only read
   the record, so no database is needed. This is the slow part, so batches are
   prepared in parallel worker processes (`--workers`).
5. **Load with SQL.** One writer loads the batches in order. Each batch is
   `COPY`'d into a temporary table, then inserted with
   `INSERT … SELECT … ON CONFLICT (internal_record_id) DO NOTHING`, in one
   transaction per batch. This is how the SQL speed and the Python checks go
   together: everything is decided in Python, and only the finished rows go to
   SQL. With `--sql-out`, the same statements go to a file instead (below).
   - **Same result as the registry:** loaded rows match rows saved through the
     registry's models value for value. This was checked on all 4,966 rows of
     the local data, computed columns included.
   - **Record ids** are uuid5 of the Odoo record (`farmer-profile/<kind>/<odoo id>`).
     A record that is already there is left alone.
   - **Progress and issues** are written in the same transaction (`tracking.py`).
   - **A value the registry refuses** rolls the batch back. It is split in half
     until the household at fault is alone: the rest loads, and that one is
     recorded as failed.
6. **Finalize.** `finalize.py` queues the functional ids and completion
   scores described above.
7. **Report.** `inventory.py` counts the values on both sides, and `report.py`
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

The commands are under "Quick start" at the top. To check against the country
pack instead of Master Data, add `--pack-only`.

`run.sh` (through `dev/py.sh`) mounts this code into the registry's image, so
no image is built locally. It installs `openpyxl` once into the
`fr-migration-pydeps` volume.

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

### Two ways to load

- **Direct (default):** each batch is loaded into the registry as soon as it's
  ready.
- **A SQL file to review first:** `migrate.py --all --sql-out` writes
  `migration.sql` in the run folder and only reads the registry. Python does
  everything as in a direct run: transform, Master Data check, hooks, and the
  report with every issue. Then:

  1. **Review it.** The header says what it is. Each table's finished rows are
     `COPY` data into a temporary table. The changes come at the end, readable:
     one `INSERT … ON CONFLICT DO NOTHING` per table, then the functional-id
     and completion-score queueing.
  2. **Run it** in one transaction. If any statement fails, nothing is kept:
     ```sh
     psql -v ON_ERROR_STOP=1 -f migration.sql "<registry database>"
     ```
     psql prints the rows each table got. It refuses to run a second time, beside
     another migration run, or on a registry that has been migrated into since the
     file was written. Unlike a direct run, one value the registry refuses rolls back
     the whole file.
  3. **Run `verify.py`**, as after a direct run.

  The file is a snapshot. Generate it close to when you run it, because
  records changed in farmer profile or Master Data afterwards aren't in it.
  Locally it's about 4.5 KB per farmer.

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
| `--batch-size N` | Farmers per transaction, in whole households. The default is 500. |
| `--workers N` | Processes preparing batches in parallel. The default is up to 4. |
| `--sql-out` | Writes `migration.sql` instead of loading. See "Two ways to load". |
| `--max-failures N` | Stops when N households failed in this run. The default is 100. |
| `--stop-on-error` | Stops after the first household that fails. By default it is recorded and the run goes on. |
| `--accept-source UUID` | Goes on although the registry was migrated from another farmer profile database |
| `--status` | Shows how far the migration is and what is open |
| `--no-finalize` | Doesn't queue the functional ids and scores |
| `--finalize-only` | Only queues them |
| `--ids ...` | Migrates only these Odoo partner ids |
