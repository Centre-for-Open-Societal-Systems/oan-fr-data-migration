-- The health report's results, in the registry's database but in a schema of their own.
-- Counts only: no names, numbers, ids or error messages, so the schema can be read by
-- people who have no access to the registry's data. health.py creates the tables when
-- they are missing and it may; otherwise a DBA runs this file once and grants the
-- migration's user USAGE on the schema and SELECT, INSERT on its tables.
CREATE SCHEMA IF NOT EXISTS migration_report;

-- One row per time the health was measured, or verify.py ran over everything
CREATE TABLE IF NOT EXISTS migration_report.snapshot (
  snapshot_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  taken_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  taken_by     text NOT NULL CHECK (taken_by IN ('migrate', 'health', 'verify')),
  run_id       text,                      -- the last load when it was taken
  overall      text NOT NULL
);

-- One row per metric (and per value it is split by)
CREATE TABLE IF NOT EXISTS migration_report.measure (
  snapshot_id  bigint NOT NULL REFERENCES migration_report.snapshot ON DELETE CASCADE,
  area         text NOT NULL,
  metric       text NOT NULL,
  record_type  text NOT NULL DEFAULT '',
  split_by     text NOT NULL DEFAULT '',  -- e.g. region
  split_value  text NOT NULL DEFAULT '',
  count        bigint,
  total        bigint,                    -- out of, when there is one
  target       text NOT NULL DEFAULT '',
  blocking     boolean NOT NULL DEFAULT false,
  result       text NOT NULL CHECK (result IN ('GREEN', 'AMBER', 'RED', 'INFO', 'NOT CHECKED')),
  PRIMARY KEY (snapshot_id, area, metric, record_type, split_by, split_value)
);
