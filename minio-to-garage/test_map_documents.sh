#!/usr/bin/env bash
# Local test of map_documents.py (Part B): Postgres with a small Gen1 and Gen2 database,
# MinIO and Garage in containers, a handful of invented files covering every status.
# Usage: PYTHON=<python with boto3 and psycopg2> ./test_map_documents.sh [workdir]
#   MINIO_IMG=minio/minio:latest   to use another MinIO image (as test_local.sh)
# Removes its containers and network at the end.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W="${1:-$(mktemp -d)}"; mkdir -p "$W"; W="$(cd "$W" && pwd)"
PY="${PYTHON:-python3}"
NET=fpmap-test
RC_IMG=rclone/rclone:1.68.2
MINIO_IMG="${MINIO_IMG:-minio/minio:RELEASE.2025-04-22T22-12-26Z}"
GARAGE_IMG=dxflrs/garage:v2.1.0
PG_IMG=postgres:16
"$PY" -c "import boto3, psycopg2" 2>/dev/null || { echo "test_map_documents: $PY needs boto3 and psycopg2 (set PYTHON)" >&2; exit 2; }
if ! docker image inspect "$MINIO_IMG" >/dev/null 2>&1 && ! docker pull -q "$MINIO_IMG" >/dev/null 2>&1; then
  echo "test_map_documents: MinIO image $MINIO_IMG is not available. Use one you have: MINIO_IMG=minio/minio:latest $0" >&2
  exit 2
fi
pass=0; fail=0
ok()  { echo "PASS: $*"; pass=$((pass+1)); }
bad() { echo "FAIL: $*"; fail=$((fail+1)); }
cleanup() { docker rm -f fpmap-minio fpmap-garage fpmap-pg >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker network create $NET >/dev/null

# --- Postgres, MinIO and Garage (ports on 127.0.0.1 for the Python tool)
PGP=$(openssl rand -hex 12)
docker run -d --name fpmap-pg --network $NET -e POSTGRES_PASSWORD=$PGP -p 127.0.0.1::5432 $PG_IMG >/dev/null
MU=testadmin; MP=$(openssl rand -hex 16)
docker run -d --name fpmap-minio --network $NET -e MINIO_ROOT_USER=$MU -e MINIO_ROOT_PASSWORD=$MP \
  -p 127.0.0.1::9000 $MINIO_IMG server /data >/dev/null
cat > "$W/garage.toml" <<EOF
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "$(openssl rand -hex 32)"
[s3_api]
s3_region = "us-east-1"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"
[admin]
api_bind_addr = "[::]:3903"
admin_token = "$(openssl rand -base64 32)"
EOF
docker run -d --name fpmap-garage --network $NET -p 127.0.0.1::3900 -v "$W/garage.toml:/etc/garage.toml:ro" $GARAGE_IMG >/dev/null
sleep 5
G() { docker exec fpmap-garage /garage "$@" 2>/dev/null; }
NODE=$(G status 2>/dev/null | awk '/^[0-9a-f]{16}/{print $1; exit}')
G layout assign -z dc1 -c 1G "$NODE" >/dev/null
G layout apply --version 1 >/dev/null
G bucket create documents >/dev/null
KEYOUT=$(G key create map-test)
GK=$(echo "$KEYOUT" | awk -F': *' '/Key ID/{print $2}' | tr -d ' ')
GS=$(echo "$KEYOUT" | awk -F': *' '/Secret key/{print $2}' | tr -d ' ')
G bucket allow --read --write --owner documents --key map-test >/dev/null
port() { docker port "$1" "$2" | head -1 | sed 's/.*://'; }
PG_PORT=$(port fpmap-pg 5432); MINIO_PORT=$(port fpmap-minio 9000); GARAGE_PORT=$(port fpmap-garage 3900)

# Two rclone configs: container names for rclone in its container, local ports for the Python tool
remotes() {  # $1 = MinIO endpoint, $2 = Garage endpoint
  printf '[old]\ntype = s3\nprovider = Minio\nendpoint = %s\naccess_key_id = %s\nsecret_access_key = %s\nregion = us-east-1\n\n' "$1" "$MU" "$MP"
  printf '[garage]\ntype = s3\nprovider = Other\nendpoint = %s\naccess_key_id = %s\nsecret_access_key = %s\nregion = us-east-1\nforce_path_style = true\n' "$2" "$GK" "$GS"
}
remotes http://fpmap-minio:9000 http://fpmap-garage:3900 > "$W/rclone.conf"
remotes "http://127.0.0.1:$MINIO_PORT" "http://127.0.0.1:$GARAGE_PORT" > "$W/rclone-local.conf"
chmod 600 "$W"/rclone*.conf
RCLONE="docker run --rm --network $NET -u $(id -u):$(id -g) -v $W:$W $RC_IMG"
rc() { $RCLONE --config "$W/rclone.conf" "$@"; }

for i in $(seq 1 30); do docker exec fpmap-pg pg_isready -U postgres -q && break; sleep 1; done
sleep 2
SQL() { docker exec -i fpmap-pg psql -q -v ON_ERROR_STOP=1 -U postgres -d "$1"; }
VAL() { docker exec -i fpmap-pg psql -qtA -U postgres -d gen2 -c "$1"; }
echo "CREATE DATABASE gen1; CREATE DATABASE gen2;" | SQL postgres

# --- invented files: key <name>-<storage_file id>.<ext>, as Odoo's name_with_id
mkdir -p "$W/files"
mk() { head -c "$2" /dev/urandom > "$W/files/$1"; }
mk 1754211609235-101.jpg 40000; mk 1754211609300-102.webp 30000; mk 1724754653267-103.jpg 20000
mk 1754211609400-104.jpg 10000; mk 1754211609500-105.pdf 15000; mk 1754211609600-106.jpg 25000
mk 1754211609700-107.jpg 12000; mk 1754211609800-108.jpg 18000; mk 1754211609900-109.jpg 22000
mk orphan-999.jpg 5000
meta() { local f="$W/files/$1"; echo "$(stat -c %s "$f"), '$(sha1sum "$f" | cut -d' ' -f1)'"; }

# --- Gen1: only the tables and columns the tool reads
SQL gen1 <<EOF
CREATE TABLE res_users (id int PRIMARY KEY, login text);
CREATE TABLE storage_backend (id int PRIMARY KEY, directory_path text);
CREATE TABLE storage_file (id int PRIMARY KEY, name text, relative_path text, file_size int, checksum text,
  mimetype text, active boolean, to_delete boolean, registrant_id int, create_date timestamp, create_uid int, backend_id int);
CREATE TABLE g2p_document_tag (id int PRIMARY KEY, name text);
CREATE TABLE g2p_document_tag_storage_file_rel (storage_file_id int, g2p_document_tag_id int);
CREATE TABLE g2p_land_information (id int PRIMARY KEY, partner_id int, land_certificate int, certficate_provided boolean);
INSERT INTO res_users VALUES (2, 'enumerator1');
INSERT INTO storage_backend VALUES (1, NULL);
INSERT INTO g2p_document_tag VALUES (1, 'Land Certificate');
INSERT INTO storage_file VALUES
 (101, '1754211609235.jpg', '1754211609235-101.jpg', $(meta 1754211609235-101.jpg), 'image/jpeg', true, false, 1, '2025-09-24 10:00', 2, 1),
 (102, '1754211609300.webp', '1754211609300-102.webp', $(meta 1754211609300-102.webp), 'image/webp', true, false, 1, '2025-09-24 10:01', 2, 1),
 (103, '1724754653267.jpg', '1724754653267-103.jpg', $(meta 1724754653267-103.jpg), 'image/jpeg', true, false, NULL, '2024-08-28 09:00', 2, 1),
 (104, '1754211609400.jpg', '1754211609400-104.jpg', $(meta 1754211609400-104.jpg), 'image/jpeg', false, false, 1, '2025-09-24 10:02', 2, 1),
 (105, '1754211609500.pdf', '1754211609500-105.pdf', $(meta 1754211609500-105.pdf), 'application/pdf', true, false, 1, '2025-09-24 10:03', 2, 1),
 (106, '1754211609600.jpg', '1754211609600-106.jpg', $(meta 1754211609600-106.jpg), 'image/jpeg', true, false, 1, '2025-09-24 10:04', NULL, 1),
 (107, '1754211609700.jpg', '1754211609700-107.jpg', $(meta 1754211609700-107.jpg), 'image/jpeg', true, false, 2, '2025-09-24 10:05', 2, 1),
 (108, '1754211609800.jpg', '1754211609800-108.jpg', $(meta 1754211609800-108.jpg), 'image/jpeg', true, false, NULL, '2025-09-24 10:06', 2, 1),
 (109, '1754211609900.jpg', '1754211609900-109.jpg', $(meta 1754211609900-109.jpg), 'image/jpeg', true, false, 3, '2025-09-24 10:07', 2, 1);
INSERT INTO g2p_document_tag_storage_file_rel VALUES (101, 1), (102, 1), (109, 1);
INSERT INTO g2p_land_information VALUES (11, 1, 101, true), (12, 1, 103, true), (13, 1, 108, false), (31, 3, 109, false);
EOF

# --- Gen2: the document tables, lands, farmers and the migration's migrated_record
SQL gen2 <<'EOF'
CREATE TABLE g2p_registry_documents (document_id varchar PRIMARY KEY, document_store_id varchar NOT NULL UNIQUE,
  bucket varchar NOT NULL, source_filename varchar NOT NULL, created_by varchar NOT NULL, created_at timestamp NOT NULL);
CREATE TABLE g2p_register_section_documents (internal_record_id varchar, document_id varchar,
  section_id varchar NOT NULL, label varchar NOT NULL, PRIMARY KEY (internal_record_id, document_id));
CREATE TABLE g2p_register_farmers (internal_record_id text PRIMARY KEY, functional_record_id text);
CREATE TABLE g2p_register_lands (internal_record_id text PRIMARY KEY, certificate_storage_id text, certificate_provided boolean);
CREATE SCHEMA migration;
CREATE TABLE migration.migrated_record (kind text, odoo_id bigint, gen2_id text UNIQUE, household_key text,
  PRIMARY KEY (kind, odoo_id));
INSERT INTO g2p_register_farmers VALUES ('F1', 'FR-1001'), ('F3', 'FR-1003');
INSERT INTO g2p_register_lands VALUES ('L11', NULL, true), ('L12', NULL, true), ('L13', NULL, false), ('L31', NULL, false);
INSERT INTO migration.migrated_record VALUES ('farmer', 1, 'F1', 'solo-1'), ('farmer', 3, 'F3', 'solo-3'),
  ('land', 11, 'L11', 'solo-1'), ('land', 12, 'L12', 'solo-1'), ('land', 13, 'L13', 'solo-1'), ('land', 31, 'L31', 'solo-3');
EOF

# --- MinIO: every file but 103 (Odoo has it, MinIO does not); 106 stored as binary/octet-stream
rc mkdir old:documents
rc copy "$W/files" old:documents --exclude 1724754653267-103.jpg --exclude 1754211609600-106.jpg -q
rc copyto "$W/files/1754211609600-106.jpg" old:documents/1754211609600-106.jpg \
  --header-upload "Content-Type: binary/octet-stream" -q
# --- Part A, then a damaged copy of 108 in Garage
RCLONE="$RCLONE" RCLONE_CONF="$W/rclone.conf" LOG_DIR="$W/logs" "$HERE/move_to_garage.sh" copy >/dev/null
head -c 999 /dev/urandom > "$W/damaged.jpg"; rc copyto "$W/damaged.jpg" garage:documents/1754211609800-108.jpg -q

export SOURCE_DSN="host=127.0.0.1 port=$PG_PORT dbname=gen1 user=postgres password=$PGP"
export TARGET_DSN="postgresql+psycopg2://postgres:$PGP@127.0.0.1:$PG_PORT/gen2"
export RCLONE_CONF="$W/rclone-local.conf" LOG_DIR="$W/logs"
MAP() { "$PY" "$HERE/map_documents.py" "$@"; }
last() { ls -d "$W"/logs/*-"$1" | sort | tail -1; }
status_of() {  # $1 entity, $2 record, $3 file -> status in the latest run's map
  awk -F, -v e="$1" -v r="$2" -v f="$3" 'NR==1{for(i=1;i<=NF;i++)c[$i]=i; next}
    $c["entity"]==e && $c["gen1_record_id"]==r && $c["gen1_storage_file_id"]==f {print $c["status"]}' "$4/document-map.csv"
}

# 1. plan: every status, nothing written
MAP plan >/dev/null && bad "plan should report rows to resolve" || ok "plan reports rows to resolve (exit 1)"
P=$(last plan)
want=( "land 11 101 ok" "farmer 1 101 ok" "farmer 1 102 ok" "farmer 1 106 ok" "land 31 109 ok" "farmer 3 109 ok"
       "land 12 103 missing_in_minio" "farmer 1 104 inactive" "farmer 1 105 not_image" "farmer 2 107 not_migrated"
       "land 13 108 differs" )
good=1
for w in "${want[@]}"; do set -- $w; got=$(status_of "$1" "$2" "$3" "$P"); [ "$got" = "$4" ] || { good=0; echo "  $1 $2 file $3: $got, want $4"; }; done
[ $good -eq 1 ] && ok "plan gives each reference its status (ok, missing_in_minio, inactive, not_image, not_migrated, differs)" || bad "plan statuses"
grep -q "orphan-999.jpg" "$P/orphans.csv" && ok "plan lists the MinIO object with no Gen1 row as orphan" || bad "orphan not listed"
[ "$(VAL "SELECT count(*) FROM g2p_registry_documents")" = 0 ] && [ -z "$(VAL "SELECT to_regclass('migration.document_map')")" ] \
  && ok "plan writes nothing to Gen2" || bad "plan wrote to Gen2"

# 2. apply: register and link, then again: nothing changes
MAP apply >/dev/null || true
docs=$(VAL "SELECT count(*) FROM g2p_registry_documents"); secs=$(VAL "SELECT count(*) FROM g2p_register_section_documents")
[ "$docs" = 4 ] && [ "$secs" = 4 ] && ok "apply: 4 documents registered, 4 farmer section links" || bad "apply: $docs documents, $secs section links"
[ "$(VAL "SELECT document_store_id FROM g2p_registry_documents d JOIN g2p_register_lands l ON l.certificate_storage_id = d.document_id WHERE l.internal_record_id = 'L11'")" = "1754211609235-101.jpg" ] \
  && ok "land L11 points at its certificate, stored under the MinIO key" || bad "land L11 certificate"
[ "$(VAL "SELECT count(*) FROM g2p_register_lands WHERE certificate_storage_id IS NOT NULL")" = 2 ] \
  && ok "only lands with an ok certificate are linked (L12 and L13 are not)" || bad "wrong lands linked"
[ "$(VAL "SELECT certificate_provided FROM g2p_register_lands WHERE internal_record_id = 'L31'")" = t ] \
  && ok "certificate_provided set for a linked land Gen1 had as false" || bad "certificate_provided"
[ "$(VAL "SELECT string_agg(label, ',' ORDER BY label) FROM g2p_register_section_documents WHERE internal_record_id = 'F1'")" = "land_document_1,land_document_2,other_document_1" ] \
  && ok "farmer documents go to Gen2's slots by tag (land_document_N, other_document_N)" || bad "slot labels"
[ "$(VAL "SELECT created_by FROM g2p_registry_documents WHERE document_store_id = '1754211609235-101.jpg'")" = enumerator1 ] \
  && ok "a document keeps its Gen1 creator" || bad "created_by"
[ "$(VAL "SELECT count(*) FROM migration.document_map")" = 11 ] && ok "document map: one row per Gen1 reference (11)" || bad "document map rows"
[ "$(VAL "SELECT gen1_storage_file_id || ' ' || minio_key || ' ' || garage_key || ' ' || functional_record_id FROM migration.document_map WHERE entity = 'land' AND gen1_record_id = 11")" = "101 1754211609235-101.jpg 1754211609235-101.jpg FR-1001" ] \
  && ok "map row keeps the old MinIO reference, the Garage key and the FR- id" || bad "map row content"
STATE="SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (SELECT d::text AS x FROM g2p_registry_documents d UNION ALL SELECT s::text FROM g2p_register_section_documents s UNION ALL SELECT l::text FROM g2p_register_lands l) q"
before=$(VAL "$STATE")
MAP apply >/dev/null || true
after=$(VAL "$STATE")
[ "$before" = "$after" ] && [ "$(VAL "SELECT count(*) FROM migration.document_map")" = 11 ] \
  && ok "apply runs again safely: nothing added or changed" || bad "second apply changed something"

# 3. validate before fix-types fails on the generic type; fix-types; validate passes
MAP validate >/dev/null && bad "validate should fail on binary/octet-stream" || ok "validate fails while a type is binary/octet-stream"
grep -q "run fix-types" "$(last validate)/validate.csv" && ok "validate names the type problem" || bad "type problem not named"
MAP fix-types >/dev/null && ok "fix-types finished" || bad "fix-types failed"
t=$(rc lsjson --metadata old:documents/1754211609600-106.jpg | grep -o '"content-type":"[^"]*"' | head -1)
g=$(rc lsjson --metadata garage:documents/1754211609600-106.jpg | grep -o '"content-type":"[^"]*"' | head -1)
[ "$g" = '"content-type":"image/jpeg"' ] && ok "Garage object 106 now image/jpeg" || bad "Garage type: $g"
[ "$t" = '"content-type":"binary/octet-stream"' ] && ok "MinIO object 106 unchanged" || bad "MinIO type changed: $t"
MAP validate && ok "validate passes: every linked document matches its record, size and SHA-1" || bad "validate failed after fix-types"
MAP validate --sample 2 >/dev/null && ok "validate --sample 2 passes" || bad "validate --sample failed"

# 4. evidence for one farmer
MAP evidence FR-1003 >/dev/null && ok "evidence FR-1003: all pass" || bad "evidence FR-1003 failed"
E=$(ls "$W"/logs/*-evidence-FR-1003.txt | tail -1)
grep -q "Gen1 storage_file: id 109" "$E" && grep -q "MinIO documents/1754211609900-109.jpg" "$E" \
  && grep -q "Garage documents/1754211609900-109.jpg" "$E" && grep -q "land_document_1" "$E" \
  && ok "evidence shows Gen1 file, MinIO, Garage and the Gen2 links" || bad "evidence content"

# 5. a document damaged in Garage after linking is caught and named
head -c 777 /dev/urandom > "$W/bad.webp"; rc copyto "$W/bad.webp" garage:documents/1754211609300-102.webp -q
MAP validate >/dev/null && bad "validate should catch the damaged document" || ok "validate catches a damaged document"
grep "1754211609300-102.webp" "$(last validate)/validate.csv" | grep -q FAIL && ok "the damaged document is named in the report" || bad "damaged document not named"

# 6. a Gen1 reference added after apply is reported as not in the map
echo "INSERT INTO g2p_land_information VALUES (14, 1, 102, true);" | SQL gen1
MAP validate >/dev/null || true
grep -q "Gen1 reference with no map row" "$(last validate)/not-in-map.csv" && ok "validate reports a Gen1 reference missing from the map" || bad "missing reference not reported"

# 7. settings errors exit 2; no secret in the logs
code=0; SOURCE_DSN= MAP plan >/dev/null 2>&1 || code=$?; [ $code -eq 2 ] && ok "missing setting: exit 2" || bad "missing setting: exit $code"
if grep -rq -- "$MP\|$GS\|$PGP" "$W/logs"; then bad "a secret appears in the logs"; else ok "no secret in the logs"; fi

echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
