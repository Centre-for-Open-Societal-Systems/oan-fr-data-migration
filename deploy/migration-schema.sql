-- The migration's audit and progress tables, in the registry's database but in a
-- schema of their own. migrate.py creates them when they are missing and it may;
-- otherwise a DBA runs this file once and grants the migration's user
-- USAGE on the schema and SELECT, INSERT, UPDATE on its tables.
-- They hold personal data (ids, names in error messages, values left out): give
-- them the same access rules as the register tables.
CREATE SCHEMA IF NOT EXISTS migration;

-- One row per execution of migrate.py that can write (a dry run writes nothing here)
CREATE TABLE IF NOT EXISTS migration.run (
  run_id       text PRIMARY KEY,          -- the run's folder name
  mode         text NOT NULL,             -- load, sql-file, finalize
  arguments    text,
  source_uuid  text,                      -- Odoo's database.uuid
  status       text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'COMPLETED_WITH_FAILURES',
                                               'STOPPED', 'FAILED', 'INTERRUPTED')),
  host         text,
  started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  finished_at  timestamptz,
  counts       jsonb,
  error        text
);

-- How far each household (or farmer in none) got: what a rerun resumes from
CREATE TABLE IF NOT EXISTS migration.household_progress (
  household_key       text PRIMARY KEY,   -- household-<lowest Odoo group id> or solo-<Odoo partner id>
  status              text NOT NULL CHECK (status IN ('LOADED', 'FAILED', 'CHANGED')),
  farmer_ids          bigint[],
  fingerprint         jsonb,              -- of farmer profile's values when loaded
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

-- Which farmers and households of farmer profile are in, and with which entry above
CREATE TABLE IF NOT EXISTS migration.migrated_record (
  kind           text NOT NULL CHECK (kind IN ('farmer', 'household')),
  odoo_id        bigint NOT NULL,
  household_key  text NOT NULL,
  PRIMARY KEY (kind, odoo_id)
);
CREATE INDEX IF NOT EXISTS migrated_record_household ON migration.migrated_record (household_key);

-- Every problem, once, with whether it is still there
CREATE TABLE IF NOT EXISTS migration.issue (
  issue_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  household_key  text NOT NULL,
  severity       text NOT NULL,           -- failed, changed, skipped, dropped, check
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
