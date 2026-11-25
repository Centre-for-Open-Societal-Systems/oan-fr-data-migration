#!/usr/bin/env bash
# The low-level runner behind ./run.sh: runs migrate.py or verify.py locally, on the registry that is
# already there (dev/env.sh: REGISTRY_IMAGE, or a farmer-registry checkout in
# REGISTRY_REPO). Settings come from .env (see .env.example) or the shell;
# without SOURCE_DSN and TARGET_DSN it uses the local databases: the farmer
# profile copy in the fp-db container (database $SOURCE_DB, default odk_a) and
# the target from dev/target-db.sh. No image is built: this code is mounted,
# and openpyxl (for the Excel reports) is installed once into the
# fr-migration-pydeps volume.
#
#   dev/py.sh migrate --all --dry-run
#   dev/py.sh verify
#
# Codes and locations are checked against the Master Data Service at
# MDS_API_URL (with MDS_TOKEN_URL, MDS_CLIENT_ID, MDS_CLIENT_SECRET); with
# --pack-only, against the country pack. dev/fake-mds.sh starts a local
# stand-in serving the pack. Each run writes a folder under out/.
set -euo pipefail
source "$(dirname "$0")/env.sh"

command=${1:?usage: dev/py.sh migrate|verify [arguments]}
shift
case "$command" in migrate|verify) ;; *) echo "unknown command $command: migrate or verify" >&2; exit 2;; esac

SOURCE_CONTAINER=${SOURCE_CONTAINER:-fp-db}
SOURCE_DB=${SOURCE_DB:-odk_a}
OPENPYXL=$(sed -n 's/.*\(openpyxl==[^ ]*\).*/\1/p' "$MIG_ROOT/Dockerfile" | head -1)

have=$(git -C "$PACK_DIR" rev-parse HEAD)
[ "$have" = "$PACK_REF" ] || { echo "pack $PACK_DIR is at $have, the migration pins $PACK_REF" >&2; exit 1; }

# SOURCE_DSN from .env or the shell; else the farmer profile copy in the local container
if [ -z "${SOURCE_DSN:-}" ]; then
  docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$SOURCE_CONTAINER" | grep -qw "$NET" \
    || docker network connect "$NET" "$SOURCE_CONTAINER"
  user=$(docker exec "$SOURCE_CONTAINER" printenv POSTGRES_USER)
  password=$(docker exec "$SOURCE_CONTAINER" printenv POSTGRES_PASSWORD)
  SOURCE_DSN="host=$SOURCE_CONTAINER dbname=$SOURCE_DB user=$user password=$password"
fi
export SOURCE_DSN

mkdir -p "$MIG_ROOT/out"
docker run --rm --network "$NET" --entrypoint sh \
  -v "$MIG_ROOT:/migration:ro" -v "$PACK_DIR:/pack:ro" -v "$MIG_ROOT/out:/out" -v fr-migration-pydeps:/deps \
  ${EXTENSION_MOUNT[@]+"${EXTENSION_MOUNT[@]}"} \
  -e PYTHONPATH="/deps:/migration${EXTENSION_PATH:+:$EXTENSION_PATH}" -e PYTHONDONTWRITEBYTECODE=1 \
  -e REGISTRY_EXTENSION_MODULE="${REGISTRY_EXTENSION_MODULE:-openg2p_registry_farmer_extension}" \
  -e MDS_API_URL -e MDS_TOKEN_URL -e MDS_CLIENT_ID -e MDS_CLIENT_SECRET \
  -e SOURCE_DSN -e TARGET_DSN="${TARGET_DSN:-postgresql+psycopg2://postgres@fr-migration-target/registry}" \
  -e HOST_OWNER="$(id -u):$(id -g)" \
  -w /migration "$IMAGE" -c '
    python -c "import openpyxl" 2>/dev/null || pip install --quiet --disable-pip-version-check --no-cache-dir --root-user-action=ignore --target /deps "$0" >&2
    python "$@"; status=$?
    chown -R "$HOST_OWNER" /out   # the run folders belong to whoever ran this, not root
    exit $status' "$OPENPYXL" "$command.py" "$@" 2>&1 \
  | grep --line-buffered -v -E '"level": ?"(DEBUG|INFO|WARNING)"|Deprecat|from (\._compat|authlib)|compatible before'
exit "${PIPESTATUS[0]}"
