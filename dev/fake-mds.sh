#!/usr/bin/env bash
# Start (or restart) a local stand-in for the Master Data Service, serving the
# country pack, as container fr-migration-mds on the fr-migration network:
#
#   dev/fake-mds.sh                       everything in the pack
#   dev/fake-mds.sh CROP_TEFF,ET04041110  without these codes / P-codes
#   ./run.sh dry-run --limit 10      (run.sh uses it when MDS_API_URL is not set)
set -euo pipefail
source "$(dirname "$0")/env.sh"
docker rm -f fr-migration-mds >/dev/null 2>&1 || true
docker run -d --name fr-migration-mds --network "$NET" --entrypoint python \
  -v "$MIG_ROOT:/migration:ro" -v "$PACK_DIR:/pack:ro" -e PYTHONDONTWRITEBYTECODE=1 \
  "$IMAGE" /migration/dev/fake_mds.py --pack /pack/packs --drop "${1:-}" >/dev/null
sleep 2
docker logs fr-migration-mds
echo "MDS_API_URL=http://fr-migration-mds:8000"
