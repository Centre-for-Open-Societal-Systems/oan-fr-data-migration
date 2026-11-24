#!/usr/bin/env bash
# The tests, on the registry that is already there (dev/env.sh). Those in tests/db
# run on a Postgres of their own, started here and removed afterwards.
#   dev/test.sh [pytest arguments]
set -euo pipefail
source "$(dirname "$0")/env.sh"
OPENPYXL=$(sed -n 's/.*\(openpyxl==[^ ]*\).*/\1/p' "$MIG_ROOT/Dockerfile" | head -1)
DB=fr-migration-test-$$
trap 'docker rm -f "$DB" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$DB" --network "$NET" -e POSTGRES_PASSWORD=test postgres:15-alpine >/dev/null
for _ in $(seq 1 120); do
  docker exec "$DB" psql -X -h 127.0.0.1 -U postgres -Atc 'SELECT 1' >/dev/null 2>&1 && break
  sleep 0.5
done
docker run --rm --init --network "$NET" --entrypoint sh \
  -v "$MIG_ROOT:/migration:ro" -v "$PACK_DIR:/pack:ro" -v fr-migration-pydeps:/deps \
  ${EXTENSION_MOUNT[@]+"${EXTENSION_MOUNT[@]}"} \
  -e PYTHONPATH="/deps:/migration${EXTENSION_PATH:+:$EXTENSION_PATH}" -e PYTHONDONTWRITEBYTECODE=1 \
  -e TEST_PG="host=$DB user=postgres password=test" \
  -e PACK_ROOT=/pack/packs -e REGISTRY_EXTENSION_MODULE="${REGISTRY_EXTENSION_MODULE:-openg2p_registry_farmer_extension}" \
  -w /migration "$IMAGE" -c '
    python -c "import pytest, openpyxl" 2>/dev/null || pip install --quiet --disable-pip-version-check --root-user-action=ignore --target /deps pytest==8.4.2 "$0"
    exec python -m pytest -q -p no:cacheprovider -p no:warnings tests "$@"' "$OPENPYXL" "$@"
