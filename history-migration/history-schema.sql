-- The history migration's tables, in the migration schema of the registry's database
-- (deploy/migration-schema.sql must have been run first). migrate_history.py apply runs
-- this file when it may; otherwise a DBA runs it once and grants the migration's user
-- SELECT, INSERT, UPDATE on these tables. Running it again is safe.
-- They hold personal data (old and new values of Gen1 fields): give them the same
-- access rules as the register tables.

-- Version 1 rows are the migration's, like every record it writes: each is in
-- migrated_record as history_<kind>, with its history_record_id as gen2_id, so the health
-- check and the delta do not count it as an edit made in the registry.
ALTER TABLE migration.migrated_record DROP CONSTRAINT IF EXISTS migrated_record_kind_check;
ALTER TABLE migration.migrated_record ADD CONSTRAINT migrated_record_kind_check CHECK (kind IN (
  'farmer', 'household', 'member', 'phone', 'land', 'crop', 'solo_household', 'solo_member',
  'history_farmer', 'history_household', 'history_member', 'history_phone', 'history_land', 'history_crop',
  'history_solo_household', 'history_solo_member'));

-- Every Gen1 change (the audit database's g2p_change_log), with the Gen2 record it is about.
-- status: linked (the record is in Gen2), not_migrated (its record is not), other_model
-- (a Gen1 model that has no register in Gen2).
CREATE TABLE IF NOT EXISTS migration.gen1_change_log (
  gen1_log_id    bigint PRIMARY KEY,      -- g2p_change_log.id
  model          text,                    -- Odoo model, e.g. res.partner
  model_name     text,
  res_id         bigint,                  -- the Odoo record's id
  name           text,
  method         text,                    -- create, write, unlink
  log_type       text,
  gen1_user_id   integer,
  user_login     text,                    -- res_users.login in Gen1
  changed_at     timestamp,
  kind           text,                    -- migrated_record kind of the record
  gen2_id        text,                    -- internal_record_id in the registry
  status         text NOT NULL CHECK (status IN ('linked', 'not_migrated', 'other_model')),
  run_id         text NOT NULL
);
CREATE INDEX IF NOT EXISTS gen1_change_log_gen2 ON migration.gen1_change_log (gen2_id);

-- Every field of every change: old and new value, as Gen1 stored and showed them
CREATE TABLE IF NOT EXISTS migration.gen1_change_log_line (
  gen1_line_id      bigint PRIMARY KEY,   -- g2p_change_log_line.id
  gen1_log_id       bigint,               -- migration.gen1_change_log.gen1_log_id
  field_id          integer,
  field_name        text,
  field_description text,
  old_value         text,
  new_value         text,
  old_value_text    text,
  new_value_text    text,
  changed_at        timestamp,
  run_id            text NOT NULL
);
CREATE INDEX IF NOT EXISTS gen1_change_log_line_log ON migration.gen1_change_log_line (gen1_log_id);

-- Every Gen1 update request (res_partner_change_request), with the Gen2 farmer or household
CREATE TABLE IF NOT EXISTS migration.gen1_change_request (
  gen1_request_id          bigint PRIMARY KEY,
  partner_id               bigint,
  name                     text,
  state                    text,          -- draft, pending, approved, rejected
  request_source           text,          -- odoo, portal, api
  requested_by             text,          -- logins in Gen1
  validator                text,
  new_values               jsonb,
  update_message           text,
  replace_related_records  boolean,
  validated_on             timestamp,
  requested_at             timestamp,
  kind                     text,
  gen2_id                  text,
  status                   text NOT NULL CHECK (status IN ('linked', 'not_migrated')),
  run_id                   text NOT NULL
);
CREATE INDEX IF NOT EXISTS gen1_change_request_gen2 ON migration.gen1_change_request (gen2_id);
