# Settings shared by the local scripts (run.sh, dev/*.sh). Sourced, not run.
#
# This repository has no copy of the registry or its Farmer extension: the
# migration runs on the registry that is already there. Locally that is one of:
#
#   REGISTRY_IMAGE  an image with the registry and the Farmer extension installed
#                   (the staff-api image the registry runs), or
#   REGISTRY_REPO   a checkout of the farmer-registry repository (default
#                   ~/farmer-registry-develop): the platform image its
#                   docker/staff-api/Dockerfile names, with its farmer-extension/src.
#                   dev/target-db.sh needs it too, for the registry's metadata.
#
# PACK_DIR is a checkout of openg2p-data at OPENG2P_DATA_REF (see Dockerfile).

MIG_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# .env (from .env.example): settings already set in the shell win
if [ -f "$MIG_ROOT/.env" ]; then
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue;; esac
    name=${line%%=*}
    [ -n "${!name+x}" ] || export "$name=${line#*=}"
  done < "$MIG_ROOT/.env"
fi
NET=fr-migration
REGISTRY_REPO=${REGISTRY_REPO:-$HOME/farmer-registry-develop}
REGISTRY_REPO=${REGISTRY_REPO/#\~/$HOME}
PACK_DIR=${PACK_DIR:-$HOME/openg2p-data}
PACK_DIR=${PACK_DIR/#\~/$HOME}
PACK_REF=$(sed -n 's/^ARG OPENG2P_DATA_REF=//p' "$MIG_ROOT/Dockerfile")

if [ -n "${REGISTRY_IMAGE:-}" ]; then
  IMAGE=$REGISTRY_IMAGE
  EXTENSION_MOUNT=()
  EXTENSION_PATH=
else
  [ -d "$REGISTRY_REPO/farmer-extension/src" ] || {
    echo "set REGISTRY_IMAGE (a registry image with the Farmer extension) or REGISTRY_REPO (a farmer-registry checkout)" >&2
    exit 1
  }
  IMAGE=openg2p/openg2p-registry-staff-api:$(sed -n 's/.*BASE_IMAGE_VERSION=\([^ ]*\).*/\1/p' "$REGISTRY_REPO/docker/staff-api/Dockerfile" | head -1)
  EXTENSION_MOUNT=(-v "$REGISTRY_REPO/farmer-extension/src:/registry-extension:ro")
  EXTENSION_PATH=/registry-extension
fi

docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null
