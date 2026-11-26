-- The migration's audit and progress tables, in the registry's database but in a
-- schema of their own. migrate.py creates them when they are missing and it may;
-- otherwise a DBA runs this file once and grants the migration's user
-- USAGE on the schema and SELECT, INSERT, UPDATE, DELETE on its tables.
-- Running it again is safe: it also brings tables made by an earlier version up to date.
-- They hold personal data (ids, names in error messages, values left out): give
-- them the same access rules as the register tables.
CREATE SCHEMA IF NOT EXISTS migration;

-- One row per execution of migrate.py that can write (a dry run writes nothing here)
CREATE TABLE IF NOT EXISTS migration.run (
  run_id       text PRIMARY KEY,          -- the run's folder name
  mode         text NOT NULL,             -- load, sql-file, finalize
  arguments    text,
  source_uuid  text,                      -- Odoo's database.uuid
  status       text NOT NULL,             -- see run_status below
  host         text,
  started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at  timestamptz,
  counts       jsonb,
  error        text
);

-- How far each household (or farmer in none) got: what a rerun resumes from
CREATE TABLE IF NOT EXISTS migration.household_progress (
  household_key       text PRIMARY KEY,   -- household-<lowest Odoo group id> or solo-<Odoo partner id>
  status              text NOT NULL,      -- see household_progress_status below
  farmer_ids          bigint[],
  fingerprint         jsonb,              -- of farmer profile's values as they are in the registry
  fingerprint_version integer,
  seen_fingerprint    jsonb,              -- of its values when last seen
  adopted             boolean NOT NULL DEFAULT false,  -- loaded before these tables existed
  attempts            integer NOT NULL DEFAULT 0,
  error_class         text,
  error               text,
  first_run_id        text NOT NULL,
  last_run_id         text NOT NULL,
  updated_at          timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS household_progress_status ON migration.household_progress (status);

-- Every record that is in: its id in farmer profile (Odoo) and its id in the registry.
-- A farmer in no household is given one: those two records (solo_household, solo_member)
-- are in no Odoo table, and odoo_id is the farmer's. A member's odoo_id is the membership's.
CREATE TABLE IF NOT EXISTS migration.migrated_record (
  kind           text NOT NULL CHECK (kind IN ('farmer', 'household', 'member', 'phone', 'land', 'crop',
                                               'solo_household', 'solo_member')),
  odoo_id        bigint NOT NULL,
  gen2_id        text NOT NULL UNIQUE,    -- internal_record_id in the registry
  household_key  text NOT NULL,           -- the household it belongs to now
  PRIMARY KEY (kind, odoo_id)
);
-- orphaned: its household was updated, and no longer has it. Set inactive at the end of a
-- complete --all run, unless another household has it by then.
ALTER TABLE migration.migrated_record ADD COLUMN IF NOT EXISTS orphaned boolean NOT NULL DEFAULT false;
-- The run that set it INACTIVE because farmer profile no longer has it, or KEPT when a
-- person decided to keep it as it is in the registry (migrate.py --resolve).
ALTER TABLE migration.migrated_record ADD COLUMN IF NOT EXISTS removed_run_id text;
-- When a person had farmer profile written over the registry's edits of this household (migrate.py
-- --overwrite): edits in the registry before then no longer make it a conflict.
ALTER TABLE migration.household_progress ADD COLUMN IF NOT EXISTS edits_accepted_at timestamptz;
CREATE INDEX IF NOT EXISTS migrated_record_household ON migration.migrated_record (household_key);

-- Every problem, once, with whether it is still there
CREATE TABLE IF NOT EXISTS migration.issue (
  issue_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  household_key  text NOT NULL,
  severity       text NOT NULL,           -- failed, conflict, changed, skipped, dropped, check
  entity         text NOT NULL,
  odoo_id        text NOT NULL DEFAULT '',
  field          text NOT NULL DEFAULT '',
  value          text NOT NULL DEFAULT '',
  reason         text NOT NULL,
  status         text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED')),
  first_run_id   text NOT NULL,
  last_run_id    text NOT NULL,
  first_seen     timestamptz NOT NULL DEFAULT clock_timestamp(),
  last_seen      timestamptz NOT NULL DEFAULT clock_timestamp(),
  resolved_at    timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS issue_once ON migration.issue
  (household_key, severity, entity, odoo_id, field, md5(value), md5(reason));
CREATE INDEX IF NOT EXISTS issue_status ON migration.issue (status, severity);

-- What a run changed in records that were already in: one row per field updated, record
-- added to a household that was in, record set inactive or made active again
CREATE TABLE IF NOT EXISTS migration.change (
  change_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id         text NOT NULL,
  household_key  text NOT NULL,
  action         text NOT NULL CHECK (action IN ('UPDATED', 'OVERWRITTEN', 'ADDED', 'SET_INACTIVE', 'ACTIVE_AGAIN',
                                               'KEPT')),
  kind           text NOT NULL,
  odoo_id        bigint,
  gen2_id        text NOT NULL,
  field          text NOT NULL DEFAULT '',
  old_value      text,
  new_value      text,
  changed_at     timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS change_run ON migration.change (run_id, action);
CREATE INDEX IF NOT EXISTS change_household ON migration.change (household_key);

-- The statuses, as checks of their own (an earlier version had them inline)
ALTER TABLE migration.run DROP CONSTRAINT IF EXISTS run_status_check;
ALTER TABLE migration.run ADD CONSTRAINT run_status_check CHECK (status IN (
  'RUNNING', 'COMPLETED', 'COMPLETED_WITH_FAILURES', 'COMPLETED_WITH_CONFLICTS', 'STOPPED', 'FAILED', 'INTERRUPTED'));
-- LOADED: in, as farmer profile has it. FAILED: not in. CHANGED: in, but could not be compared
-- (unreadable, or partly in from before these tables). CONFLICT: changed in farmer profile and
-- edited in the registry: not touched. REMOVED: no longer in farmer profile; set inactive.
ALTER TABLE migration.household_progress DROP CONSTRAINT IF EXISTS household_progress_status_check;
ALTER TABLE migration.household_progress ADD CONSTRAINT household_progress_status_check CHECK (status IN (
  'LOADED', 'FAILED', 'CHANGED', 'CONFLICT', 'REMOVED'));
