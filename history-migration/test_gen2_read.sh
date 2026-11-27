#!/usr/bin/env bash
# The version 1 rows, read back by the registry itself: a real, empty Farmer registry
# database (../dev/target-db.sh: the registry's tables and the Farmer extension's
# metadata), the migration's schema, invented records as the database migration writes
# them, migrate_history.py apply --only version1, then the registry's own
# get_record_history (gen2_read_history.py, in the staff-api image) for each record.
#
#   REGISTRY_REPO=<farmer-registry checkout> PYTHON=<python with psycopg2> ./test_gen2_read.sh
#
# Leaves the database container (fr-migration-target) for a look; remove it with
# docker rm -f fr-migration-target.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-python3}"
PORT=${TARGET_PORT:-55440}
source "$ROOT/dev/env.sh"

"$ROOT/dev/target-db.sh" reset
Q() { docker exec -i fr-migration-target psql -X -q -U postgres -d registry -v ON_ERROR_STOP=1; }
Q < "$ROOT/deploy/migration-schema.sql"
# The same invented records as test_history.sh
awk '/^# --- Gen2 records/{f=1} f&&/^Q registry <<.SQL.$/{g=1;next} g&&/^SQL$/{exit} g' "$HERE/test_history.sh" | Q

TARGET_DSN="postgresql://postgres@127.0.0.1:$PORT/registry" LOG_DIR="$(mktemp -d)" \
  "$PY" "$HERE/migrate_history.py" apply --only version1 || true   # exit 1: FR-0002 is skipped, as it should be

docker run --rm --network "$NET" --entrypoint python ${EXTENSION_MOUNT[@]+"${EXTENSION_MOUNT[@]}"} \
  -v "$HERE/gen2_read_history.py:/gen2_read_history.py:ro" -e PYTHONPATH="${EXTENSION_PATH}" \
  -e REGISTRY_EXTENSION_MODULE="${REGISTRY_EXTENSION_MODULE:-openg2p_registry_farmer_extension}" \
  -e registry_staff_portal_api_db_hostname=fr-migration-target -e registry_staff_portal_api_db_port=5432 \
  -e registry_staff_portal_api_db_dbname=registry -e registry_staff_portal_api_db_username=postgres \
  -e registry_staff_portal_api_db_password= \
  "$IMAGE" /gen2_read_history.py 2>/dev/null | grep -E '^(PASS|FAIL)'
