#!/usr/bin/env bash
# Test of migrate_history.py against Postgres in a container: a Gen1 database (users,
# update requests), the Gen1 audit database (its tables as g2p_ati_change_tracking
# creates them), and a Gen2 registry with the real register tables (fixtures/gen2_schema.sql)
# and the migration's schema (deploy/migration-schema.sql). Invented data only.
# Usage: PYTHON=<python with psycopg2> ./test_history.sh   (removes its container at the end)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
PG_IMG=postgres:16
NAME=fphist-pg
pass=0; fail=0
ok()  { echo "PASS: $*"; pass=$((pass+1)); }
bad() { echo "FAIL: $*"; fail=$((fail+1)); }
W="$(mktemp -d)"

cleanup() { docker rm -f $NAME >/dev/null 2>&1 || true; rm -rf "$W"; }
trap cleanup EXIT
cleanup; W="$(mktemp -d)"
PGP=$(openssl rand -hex 12)
docker run -d --name $NAME -e POSTGRES_PASSWORD=$PGP -p 127.0.0.1::5432 $PG_IMG >/dev/null
for _ in $(seq 1 60); do docker exec $NAME pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
sleep 1
PORT=$(docker port $NAME 5432/tcp | head -1 | sed 's/.*://')
Q() { docker exec -i $NAME psql -X -q -U postgres -d "$1" -v ON_ERROR_STOP=1 "${@:2}"; }
V() { docker exec $NAME psql -X -U postgres -d "$1" -Atc "$2"; }
for db in gen1 audit registry; do V postgres "CREATE DATABASE $db" >/dev/null; done

# --- Gen2: the real register tables and metadata, and the migration's schema
Q registry < "$HERE/fixtures/gen2_schema.sql"
Q registry < "$HERE/../deploy/migration-schema.sql"

# --- Gen2 records, as the database migration wrote them. Gen1 ids: farmers 11, 12, 13 (13 in no
# household: solo household and member), household 21, membership 31, phone 41, land 51, crop 61.
Q registry <<'SQL'
INSERT INTO g2p_register_households (internal_record_id, record_name, created_by, created_at, last_approved_at, last_approved_by, record_status)
VALUES ('h21', 'Household of Abebe', 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE'),
       ('hs13', 'Household of Chaltu', 'enumerator1', '2025-04-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE');
INSERT INTO g2p_register_farmers (internal_record_id, functional_record_id, link_internal_record_id, record_name, first_name, last_name, gender,
       income_sources, created_by, created_at, last_approved_at, last_approved_by, record_status, authentication_expiry_notified)
VALUES ('f11', 'FR-0001', 'h21', 'Abebe Kebede', 'Abebe', 'Kebede', 'male', '["crop"]', 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE', false),
       ('f12', 'FR-0002', NULL, 'Bekele Alemu', 'Bekele', 'Alemu', 'male', NULL, 'enumerator1', '2025-03-02 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE', false),
       ('f13', 'FR-0003', 'hs13', 'Chaltu Tola', 'Chaltu', 'Tola', 'female', '["livestock"]', 'enumerator1', '2025-04-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE', false);
INSERT INTO g2p_register_household_members (internal_record_id, link_internal_record_id, first_name, created_by, created_at, last_approved_at, last_approved_by, record_status)
VALUES ('m31', 'h21', 'Abebe', 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE'),
       ('ms13', 'hs13', 'Chaltu', 'enumerator1', '2025-04-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE');
INSERT INTO g2p_register_farmer_phones (internal_record_id, link_internal_record_id, phone_number, created_by, created_at, last_approved_at, last_approved_by, record_status)
VALUES ('p41', 'f11', '0911000000', 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE');
INSERT INTO g2p_register_lands (internal_record_id, link_internal_record_id, land_size, created_by, created_at, last_approved_at, last_approved_by, record_status)
VALUES ('l51', 'f11', 1.5, 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE');
INSERT INTO g2p_register_crops (internal_record_id, link_internal_record_id, commodity, water_sources, created_by, created_at, last_approved_at, last_approved_by, record_status)
VALUES ('c61', 'l51', 'teff', '["rain"]', 'enumerator1', '2025-03-01 09:00', '2026-11-20 10:00', 'farmer-profile-migration', 'ACTIVE');
INSERT INTO migration.migrated_record (kind, odoo_id, gen2_id, household_key) VALUES
  ('farmer', 11, 'f11', 'household-21'), ('farmer', 12, 'f12', 'solo-12'), ('farmer', 13, 'f13', 'solo-13'),
  ('household', 21, 'h21', 'household-21'), ('solo_household', 13, 'hs13', 'solo-13'),
  ('member', 31, 'm31', 'household-21'), ('solo_member', 13, 'ms13', 'solo-13'),
  ('phone', 41, 'p41', 'household-21'), ('land', 51, 'l51', 'household-21'), ('crop', 61, 'c61', 'household-21');
-- FR-0002 was edited in Gen2 (Staff Portal) before the history migration ran
INSERT INTO g2p_register_history_farmers (history_record_id, internal_record_id, tab_id, section_id, change_request_source,
       is_primary_section, first_name, created_by, created_at, approved_by, approved_at, record_status)
VALUES ('gen2-edit-1', 'f12', 'farmer_farmer_tab', 'farmer_header', 'STAFF_PORTAL', true, 'Bekele', 'staff1', '2026-11-21 08:00', 'staff2', '2026-11-21 09:00', 'ACTIVE');
SQL

# --- Gen1 audit database, as g2p_ati_change_tracking creates it
Q audit <<'SQL'
CREATE TABLE g2p_change_log (id SERIAL PRIMARY KEY, name TEXT, model_id INTEGER, model_name VARCHAR(255), model_model VARCHAR(255),
  res_id INTEGER, user_id INTEGER, method VARCHAR(64), log_type VARCHAR(10), http_session_id INTEGER, http_request_id INTEGER,
  create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, write_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, create_uid INTEGER, write_uid INTEGER);
CREATE TABLE g2p_change_log_line (id SERIAL PRIMARY KEY, log_id INTEGER REFERENCES g2p_change_log(id) ON DELETE CASCADE,
  field_id INTEGER, field_name VARCHAR(255), field_description VARCHAR(255), old_value TEXT, new_value TEXT,
  old_value_text TEXT, new_value_text TEXT, create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  write_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, create_uid INTEGER, write_uid INTEGER);
INSERT INTO g2p_change_log (id, name, model_name, model_model, res_id, user_id, method, log_type, create_date) VALUES
  (1, 'Abebe Kebede', 'Contact', 'res.partner', 11, 2, 'create', 'full', '2025-03-01 09:00'),
  (2, 'Abebe Kebede', 'Contact', 'res.partner', 11, 3, 'write', 'full', '2025-06-10 14:30'),
  (3, 'Land 51', 'Land Information', 'g2p.land.information', 51, 2, 'write', 'full', '2025-07-01 11:00'),
  (4, 'Household of Abebe', 'Contact', 'res.partner', 21, 2, 'write', 'full', '2025-08-01 11:00'),
  (5, 'Someone not migrated', 'Contact', 'res.partner', 99, 2, 'write', 'full', '2025-08-02 11:00'),
  (6, 'ID 7', 'Registrant ID', 'g2p.reg.id', 7, 2, 'write', 'full', '2025-08-03 11:00');
INSERT INTO g2p_change_log_line (id, log_id, field_name, field_description, old_value, new_value, old_value_text, new_value_text, create_date) VALUES
  (1, 1, 'name', 'Name', NULL, 'Abebe Kebede', NULL, 'Abebe Kebede', '2025-03-01 09:00'),
  (2, 2, 'given_name', 'First Name', 'Abebe K', 'Abebe', 'Abebe K', 'Abebe', '2025-06-10 14:30'),
  (3, 2, 'gender', 'Gender', '1', '2', 'Female', 'Male', '2025-06-10 14:30'),
  (4, 3, 'land_size', 'Land Size', '1.0', '1.5', '1.0', '1.5', '2025-07-01 11:00'),
  (5, 4, 'name', 'Name', 'Abebe HH', 'Household of Abebe', 'Abebe HH', 'Household of Abebe', '2025-08-01 11:00'),
  (6, 5, 'name', 'Name', 'X', 'Y', 'X', 'Y', '2025-08-02 11:00');
SQL

# --- Gen1 farmer profile: users and update requests
Q gen1 <<'SQL'
CREATE TABLE res_users (id integer PRIMARY KEY, login varchar NOT NULL);
INSERT INTO res_users VALUES (1, 'admin'), (2, 'enumerator1'), (3, 'validator1');
CREATE TABLE res_partner_change_request (id serial PRIMARY KEY, partner_id integer NOT NULL, name varchar, requested_by integer,
  validator integer, new_values jsonb NOT NULL, update_message varchar, request_source varchar, import_source_id integer,
  enumerator_id integer, replace_related_records boolean, validated_on timestamp, state varchar,
  create_date timestamp, write_date timestamp, create_uid integer, write_uid integer);
INSERT INTO res_partner_change_request (id, partner_id, name, requested_by, validator, new_values, request_source, replace_related_records, validated_on, state, create_date) VALUES
  (1, 11, 'Update FR-0001', 2, 3, '{"given_name": "Abebe"}', 'portal', true, '2025-06-10 14:30', 'approved', '2025-06-09 10:00'),
  (2, 99, 'Update not migrated', 2, NULL, '{"name": "Y"}', 'api', false, NULL, 'pending', '2025-08-02 10:00');
SQL

export TARGET_DSN="postgresql+psycopg2://postgres:$PGP@127.0.0.1:$PORT/registry"
export AUDIT_DSN="host=127.0.0.1 port=$PORT dbname=audit user=postgres password=$PGP"
export SOURCE_DSN="host=127.0.0.1 port=$PORT dbname=gen1 user=postgres password=$PGP"
export LOG_DIR="$W/logs"
H() { "$PY" "$HERE/migrate_history.py" "$@"; }
R() { V registry "$1"; }
state() {   # everything the script writes, as one hash
  R "SELECT md5(string_agg(t, '|' ORDER BY t)) FROM (
       SELECT x::text AS t FROM g2p_register_history_farmers x UNION ALL SELECT x::text FROM g2p_register_history_households x
       UNION ALL SELECT x::text FROM g2p_register_history_household_members x UNION ALL SELECT x::text FROM g2p_register_history_farmer_phones x
       UNION ALL SELECT x::text FROM g2p_register_history_lands x UNION ALL SELECT x::text FROM g2p_register_history_crops x
       UNION ALL SELECT x::text FROM migration.migrated_record x
       UNION ALL SELECT x::text FROM migration.gen1_change_log x UNION ALL SELECT x::text FROM migration.gen1_change_log_line x
       UNION ALL SELECT x::text FROM migration.gen1_change_request x) s"
}
hist_rows() { R "SELECT (SELECT count(*) FROM g2p_register_history_farmers) + (SELECT count(*) FROM g2p_register_history_households)
  + (SELECT count(*) FROM g2p_register_history_household_members) + (SELECT count(*) FROM g2p_register_history_farmer_phones)
  + (SELECT count(*) FROM g2p_register_history_lands) + (SELECT count(*) FROM g2p_register_history_crops)"; }

# 1. settings errors exit 2
code=0; TARGET_DSN= H plan >/dev/null 2>&1 || code=$?
[ "$code" -eq 2 ] && ok "no TARGET_DSN: exit 2" || bad "no TARGET_DSN: exit $code"
code=0; AUDIT_DSN= H apply --only audit >/dev/null 2>&1 || code=$?
[ "$code" -eq 2 ] && ok "apply --only audit without AUDIT_DSN: exit 2" || bad "apply --only audit without AUDIT_DSN: exit $code"

# 2. plan: what would be written, nothing written
code=0; H plan > "$W/plan.txt" 2>&1 || code=$?
[ "$code" -eq 1 ] && ok "plan exits 1: FR-0002 needs a decision" || bad "plan exit $code"
grep -q "Crop .*tab farmer_crop_tab, section farmer_crops, subject Farmer" "$W/plan.txt" && ok "plan places crops under the farmer's crop tab" || bad "crop section in plan"
grep -q "has_gen2_history 1" "$W/plan.txt" && ok "plan finds the farmer edited in Gen2" || bad "has_gen2_history in plan"
grep -q "res.partner .*not_migrated *1" "$W/plan.txt" && grep -q "g2p.reg.id .*other_model *1" "$W/plan.txt" && ok "plan sorts the Gen1 changes" || bad "Gen1 changes in plan"
[ "$(hist_rows)" -eq 1 ] && [ "$(R "SELECT count(*) FROM information_schema.tables WHERE table_name = 'gen1_change_log'")" -eq 0 ] \
  && ok "plan wrote nothing" || bad "plan wrote something"

# 3. apply
code=0; H apply > "$W/apply.txt" 2>&1 || code=$?
[ "$code" -eq 1 ] && ok "apply exits 1: one record skipped" || { bad "apply exit $code"; cat "$W/apply.txt"; }
[ "$(hist_rows)" -eq 10 ] && ok "9 version 1 rows written (and Gen2's own row kept)" || bad "history rows: $(hist_rows)"
[ "$(R "SELECT count(*) FROM migration.migrated_record WHERE kind LIKE 'history_%'")" -eq 9 ] && ok "each version 1 is in migrated_record" || bad "history_* in migrated_record"
[ "$(R "SELECT count(*) FROM migration.migrated_record h JOIN g2p_register_history_farmers e ON e.history_record_id = h.gen2_id WHERE h.kind = 'history_farmer' AND h.odoo_id = 11 AND e.internal_record_id = 'f11'")" -eq 1 ] \
  && ok "FR-0001's version 1 is registered as history_farmer 11" || bad "history_farmer 11"
row=$(R "SELECT concat_ws('|', first_name, income_sources::text, approved_by, approved_at, created_by, created_at, change_request_source, tab_id, section_id, is_primary_section, subject_internal_record_id, coalesce(change_request_id, 'none')) FROM g2p_register_history_farmers WHERE internal_record_id = 'f11'")
[ "$row" = 'Abebe|["crop"]|farmer-profile-migration|2026-11-20 10:00:00|enumerator1|2025-03-01 09:00:00|PARTNER|farmer_farmer_tab|farmer_header|t|f11|none' ] \
  && ok "version 1 is the record as migrated, approved at the migration" || bad "version 1 of f11: $row"
subj=$(R "SELECT string_agg(r, ',' ORDER BY r) FROM (
  SELECT internal_record_id || '>' || subject_internal_record_id AS r FROM g2p_register_history_lands UNION ALL
  SELECT internal_record_id || '>' || subject_internal_record_id FROM g2p_register_history_crops UNION ALL
  SELECT internal_record_id || '>' || subject_internal_record_id FROM g2p_register_history_farmer_phones UNION ALL
  SELECT internal_record_id || '>' || subject_internal_record_id FROM g2p_register_history_household_members) s")
[ "$subj" = "c61>f11,l51>f11,m31>h21,ms13>hs13,p41>f11" ] && ok "subjects: crop, land and phone under the farmer, members under the household" || bad "subjects: $subj"
[ "$(R "SELECT water_sources::text FROM g2p_register_history_crops WHERE internal_record_id = 'c61'")" = '["rain"]' ] && ok "a json value is copied" || bad "crop json"
[ "$(R "SELECT string_agg(history_record_id, ',') FROM g2p_register_history_farmers WHERE internal_record_id = 'f12'")" = "gen2-edit-1" ] \
  && ok "the farmer edited in Gen2 keeps its history, nothing added" || bad "f12 history"
[ "$(R "SELECT count(*) FROM (SELECT change_request_source FROM g2p_register_history_farmers UNION ALL SELECT change_request_source FROM g2p_register_history_crops UNION ALL SELECT change_request_source FROM g2p_register_history_lands) s WHERE change_request_source NOT IN ('PARTNER','INTAKE_FORM','STAFF_PORTAL','BENEFICIARY_PORTAL','AGENT_PORTAL')")" -eq 0 ] \
  && ok "every source is one Gen2 knows" || bad "unknown change_request_source"

# 4. the Gen1 history, archived
[ "$(R "SELECT string_agg(gen1_log_id || ':' || status || ':' || coalesce(gen2_id, '-'), ',' ORDER BY gen1_log_id) FROM migration.gen1_change_log")" = \
  "1:linked:f11,2:linked:f11,3:linked:l51,4:linked:h21,5:not_migrated:-,6:other_model:-" ] && ok "every Gen1 change archived, with its Gen2 record" || bad "gen1_change_log: $(R "SELECT string_agg(gen1_log_id || ':' || status || ':' || coalesce(gen2_id, '-'), ',' ORDER BY gen1_log_id) FROM migration.gen1_change_log")"
[ "$(R "SELECT count(*) FROM migration.gen1_change_log_line")" -eq 6 ] && ok "every field line archived" || bad "lines"
[ "$(R "SELECT user_login || '|' || old_value_text || '>' || new_value_text FROM migration.gen1_change_log c JOIN migration.gen1_change_log_line l USING (gen1_log_id) WHERE l.gen1_line_id = 2")" = "validator1|Abebe K>Abebe" ] \
  && ok "who changed it, and old and new value, are kept" || bad "line 2"
[ "$(R "SELECT string_agg(gen1_request_id || ':' || status || ':' || coalesce(gen2_id, '-') || ':' || coalesce(validator, '-') || ':' || (new_values->>'given_name' IS NOT NULL)::text, ',' ORDER BY 1) FROM migration.gen1_change_request")" = \
  "1:linked:f11:validator1:true,2:not_migrated:-:-:false" ] && ok "update requests archived, with logins" || bad "gen1_change_request"

# 5. safe to run again
before=$(state); H apply >/dev/null 2>&1 || true
[ "$(state)" = "$before" ] && ok "apply again changes nothing" || bad "second apply changed something"

# 6. validate
code=0; H validate > "$W/validate1.txt" 2>&1 || code=$?
[ "$code" -eq 1 ] && grep -q "has_gen2_history: 1" "$W/validate1.txt" && ok "validate reports the farmer edited in Gen2" || { bad "validate with f12: exit $code"; cat "$W/validate1.txt"; }
R "DELETE FROM g2p_register_history_farmers WHERE history_record_id = 'gen2-edit-1'" >/dev/null   # as if never edited
H apply >/dev/null 2>&1 || true
code=0; H validate > "$W/validate2.txt" 2>&1 || code=$?
[ "$code" -eq 0 ] && ok "validate passes" || { bad "validate exit $code"; cat "$W/validate2.txt"; }
R "UPDATE g2p_register_history_lands SET land_size = 9 WHERE internal_record_id = 'l51'" >/dev/null
R "DELETE FROM g2p_register_history_crops WHERE internal_record_id = 'c61'" >/dev/null
R "DELETE FROM migration.gen1_change_log_line WHERE gen1_line_id = 6" >/dev/null
code=0; H validate > "$W/validate3.txt" 2>&1 || code=$?
[ "$code" -eq 1 ] && grep -q "differs_from_record: 1" "$W/validate3.txt" && grep -q "history_row_missing: 1" "$W/validate3.txt" \
  && grep -q "gen1_change_log_line" "$W/validate3.txt" && ok "validate catches a changed row, a missing row and a missing Gen1 line" || { bad "validate damage: exit $code"; cat "$W/validate3.txt"; }

# 7. evidence
H apply >/dev/null 2>&1 || true
[ "$(R "SELECT count(*) FROM g2p_register_history_crops e JOIN migration.migrated_record h ON h.gen2_id = e.history_record_id WHERE e.internal_record_id = 'c61'")" -eq 1 ] \
  && ok "apply puts back a missing version 1, under the same id" || bad "missing crop row not repaired"
H evidence FR-0001 > "$W/evidence.txt" 2>&1 || true
grep -q "Farmer .*record f11 .*migration (history_farmer)" "$W/evidence.txt" && grep -q "Crop .*record c61" "$W/evidence.txt" \
  && grep -q "given_name: Abebe K -> Abebe" "$W/evidence.txt" && grep -q "request 1 .*approved (portal)" "$W/evidence.txt" \
  && ls "$LOG_DIR"/*-history-evidence-FR-0001.txt >/dev/null 2>&1 && ok "evidence traces FR-0001 from Gen1 to Gen2" || { bad "evidence"; cat "$W/evidence.txt"; }

# 8. no password in the reports
if grep -rq -- "$PGP" "$LOG_DIR"; then bad "a password appears in the reports"; else ok "no password in the reports"; fi

echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
