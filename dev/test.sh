#!/usr/bin/env bash
# The tests, on the registry that is already there (dev/env.sh).
#   dev/test.sh [pytest arguments]
set -euo pipefail
source "$(dirname "$0")/env.sh"
docker run --rm --entrypoint sh -v "$MIG_ROOT:/migration:ro" -v "$PACK_DIR:/pack:ro" -v fr-migration-pydeps:/deps \
  "${EXTENSION_MOUNT[@]}" \
  -e PYTHONPATH="/deps:/migration${EXTENSION_PATH:+:$EXTENSION_PATH}" -e PYTHONDONTWRITEBYTECODE=1 \
  -e PACK_ROOT=/pack/packs -e REGISTRY_EXTENSION_MODULE="${REGISTRY_EXTENSION_MODULE:-openg2p_registry_farmer_extension}" \
  -w /migration "$IMAGE" -c '
    python -c "import pytest" 2>/dev/null || pip install --quiet --disable-pip-version-check --root-user-action=ignore --target /deps pytest==8.4.2
    exec python -m pytest -q -p no:cacheprovider -p no:warnings tests "$@"' sh "$@"
