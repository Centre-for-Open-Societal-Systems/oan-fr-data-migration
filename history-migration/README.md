# History migration

Brings the farmer profile's (Gen1) record history into the Farmer registry (Gen2).
Runs after the database migration (it reads `migration.migrated_record`). Gen1 and
its audit database are only read.

Gen1 keeps history as field changes (old value → new value) in a separate audit
database. Gen2 keeps a full copy of the record for every approved version. The
migration does not rebuild every past version from the changes: each record gets
**one version in Gen2, the record as migrated**, and **the full Gen1 history is
archived** next to it, linked to the record.

| Gen1 | Gen2 |
|---|---|
| The migrated record | One row in its register's history table (`g2p_register_history_farmers`, `_households`, `_household_members`, `_farmer_phones`, `_lands`, `_crops`): version 1 |
| Audit database `g2p_change_log` (one row per change: model, record, method, user, date) | `migration.gen1_change_log`, with the Gen2 record it is about |
| Audit database `g2p_change_log_line` (one row per field: old and new value) | `migration.gen1_change_log_line` |
| `res_partner_change_request` (update requests: new values, requested by, validator, state) | `migration.gen1_change_request`, with the Gen2 farmer or household |

## Version 1

Written the way the registry writes history when it approves an intake form:

- the record's own values, copied from its register table;
- `created_by` / `created_at`: the record's (from Gen1); `approved_by` / `approved_at`:
  who last approved it (the migration's `last_approved_by` / `last_approved_at`);
- `change_request_source` `PARTNER` (`HISTORY_SOURCE` to change it), no change request;
- the section and tab that show the record in the Staff Portal: its register's own
  section on a tab first, then by tab and section order. `plan` prints them:

  | Register | Tab / section | Subject |
  |---|---|---|
  | Farmer | `farmer_farmer_tab` / `farmer_header` | the farmer |
  | Household | `household_household_tab` / household header | the household |
  | HouseholdMember | `household_household_tab` / household members | the household |
  | FarmerPhone | `farmer_farmer_tab` / `farmer_phones` | the farmer |
  | Land | `farmer_land_tab` / `farmer_lands` | the farmer |
  | Crop | `farmer_crop_tab` / `farmer_crops` | the farmer (through the land) |

Each version 1 row is in `migration.migrated_record` as `history_<kind>` (for example
`history_farmer`, odoo_id = the farmer's Odoo id, gen2_id = the history row's id), so
the migration's health check and delta count it as the migration's, not as an edit
made in Gen2. `history-schema.sql` adds these kinds to `migrated_record`'s kind check.

A record that already has history in Gen2 (edited in Gen2 before this ran) gets no
version 1: its history stays as Gen2 has it, and it is listed (`has_gen2_history`).
Its Gen1 history is still archived.

## Set up

1. Python 3.10 or later with `psycopg2`.
2. `cp .env.example .env`, fill in, `chmod 600 .env`. `.env` and `logs/` are git-ignored.
3. `history-schema.sql` (in the registry's database, after `deploy/migration-schema.sql`):
   `apply` runs it when its user may; otherwise a DBA runs it once.

## Use

```
python migrate_history.py plan                    # what would be written, per register and per Gen1 model; writes nothing
python migrate_history.py apply                   # version 1, then the Gen1 changes, then the update requests (safe to run again)
python migrate_history.py apply --only version1   # one part: version1, audit or requests
python migrate_history.py validate                # every migrated record and every Gen1 change against Gen2
python migrate_history.py evidence FR-...         # one farmer's history, Gen1 and Gen2
```

Order: database migration → `plan` → resolve what it lists → `apply` → `validate`
(must pass) → `evidence` for a sample farmer. Run it right after the database
migration, before users edit records in Gen2. After a delta run of the database
migration, run `apply` again: new records get their version 1, and new Gen1 changes
are archived.

`validate` checks:
- every migrated record has its version 1, in the history table, for that record;
- version 1 has the record's values, unless the record has been approved again since;
- the archive has every Gen1 change, field line and update request (counts against Gen1);
- every archived change linked to a record points at a migrated record.

Statuses:

| Where | Status | Meaning |
|---|---|---|
| Version 1 | `to_write` / `done` | Not yet written / written |
| | `has_gen2_history` | Edited in Gen2 before this ran: no version 1 (listed, exit 1) |
| | `no_gen2_record` | In `migrated_record`, not in its register table |
| Gen1 changes | `linked` | About a migrated record |
| | `not_migrated` | About a record that is not migrated: archived, not linked |
| | `other_model` | A Gen1 model that has no register in Gen2 (for example `g2p.reg.id`): archived, not linked |

Each run writes a folder under `logs/`: `summary.csv` and `to-resolve.csv` (plan),
`skipped.csv` (apply), `validate.csv` (validate); `evidence` writes
`logs/<time>-history-evidence-<FR id>.txt`.

Exit code: 0 = clean, 1 = something to resolve or a check failed, 2 = setup error.

## Not migrated

- Odoo's chatter (`mail_message`): notes on records, as in the database migration's field map.
- Gen1's `request` model (edit suggestions): a transient model, which Odoo deletes.
- Every past version as a Gen2 history row: the Gen1 changes are in the archive instead.

## Tests

Need Docker.

```
PYTHON=<python with psycopg2> ./test_history.sh       # 27 checks, Postgres 16, invented data
REGISTRY_REPO=<farmer-registry checkout> PYTHON=<python with psycopg2> ./test_gen2_read.sh
```

`test_history.sh` uses the registry's real register tables and metadata
(`fixtures/gen2_schema.sql`), the migration's schema (`deploy/migration-schema.sql`) and
the audit tables as `g2p_ati_change_tracking` creates them.

`test_gen2_read.sh` builds a real registry database (`dev/target-db.sh`), writes version 1,
and reads it back with the registry's own `get_record_history` (what the Staff Portal's
history tab calls), for each of the six registers.

`fixtures/gen2_schema.sql` is generated from such a database: `dev/target-db.sh`, then
`pg_dump -s` of the six registers' live and history tables, and the register, section
and tab rows (`register_id`, `register_mnemonic`, `master_register_id`; `section_id`,
`register_id`, `section_register_id`; tabs and tab sections with their order).
