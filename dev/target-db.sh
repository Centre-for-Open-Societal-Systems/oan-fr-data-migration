#!/usr/bin/env bash
# A local, empty Farmer registry database to migrate into, as the registry's
# own deployment makes it: its tables (from the registry, dev/env.sh), the
# Farmer extension's schema additions and its metadata (from REGISTRY_REPO,
# the farmer-registry checkout: they ship with the registry's db-seed).
# Only for local tests: a deployed registry already has its database.
#
#   dev/target-db.sh          create it (fails if it exists)
#   dev/target-db.sh reset    drop it and create it again
#
# Postgres listens on 127.0.0.1:${TARGET_PORT:-55440}, user postgres, no password,
# database registry.
set -euo pipefail
source "$(dirname "$0")/env.sh"
NAME=fr-migration-target
PORT=${TARGET_PORT:-55440}
EXT="$REGISTRY_REPO/farmer-extension/src/openg2p_registry_farmer_extension"
[ -d "$EXT/meta_data" ] || { echo "no registry metadata at $EXT: set REGISTRY_REPO" >&2; exit 1; }

if [ "${1:-}" = reset ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
fi
docker run -d --name "$NAME" --network "$NET" -p "127.0.0.1:$PORT:5432" \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=registry postgres:15-alpine >/dev/null
for _ in $(seq 1 120); do
  docker exec "$NAME" psql -X -h 127.0.0.1 -U postgres -d registry -Atc 'SELECT 1' >/dev/null 2>&1 && break
  sleep 0.5
done

echo "tables, from $IMAGE"
docker run --rm --network "$NET" --entrypoint python -v "$MIG_ROOT/dev:/dev-scripts:ro" "${EXTENSION_MOUNT[@]}" \
  -e PYTHONPATH="${EXTENSION_PATH}" -e REGISTRY_EXTENSION_MODULE="${REGISTRY_EXTENSION_MODULE:-openg2p_registry_farmer_extension}" \
  -e TARGET_DSN="postgresql+psycopg2://postgres@$NAME/registry" \
  "$IMAGE" /dev-scripts/create_schema.py

psql_file() {
  docker exec -i "$NAME" psql -X -q -U postgres -d registry -v ON_ERROR_STOP=1 < "$1" >/dev/null \
    || { echo "failed: $1" >&2; exit 1; }
}
psql_file "$EXT/native_schema_compat.sql"
n=0
while IFS= read -r f; do psql_file "$f"; n=$((n + 1)); done < <(find "$EXT/meta_data" -name '*.sql' | LC_ALL=C sort)
echo "metadata: $n files from $REGISTRY_REPO"
echo "ready: postgresql://postgres@127.0.0.1:$PORT/registry"
