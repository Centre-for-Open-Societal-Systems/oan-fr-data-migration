#!/usr/bin/env bash
# Local test of move_to_garage.sh: MinIO (same release as the image saved locally) and
# Garage v2.1.0 in containers, 2,000 random test files (no real data), rclone in a container.
# Usage: ./test_local.sh [workdir]   (removes its containers and network at the end)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
W="${1:-$(mktemp -d)}"; mkdir -p "$W"; W="$(cd "$W" && pwd)"
NET=fpmove-test
RC_IMG=rclone/rclone:1.68.2
MINIO_IMG=minio/minio:RELEASE.2025-04-22T22-12-26Z
GARAGE_IMG=dxflrs/garage:v2.1.0
pass=0; fail=0
ok()  { echo "PASS: $*"; pass=$((pass+1)); }
bad() { echo "FAIL: $*"; fail=$((fail+1)); }

cleanup() { docker rm -f fpmove-minio fpmove-garage >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker network create $NET >/dev/null

# --- MinIO with local test credentials
MU=testadmin; MP=$(openssl rand -hex 16)
docker run -d --name fpmove-minio --network $NET -e MINIO_ROOT_USER=$MU -e MINIO_ROOT_PASSWORD=$MP \
  $MINIO_IMG server /data >/dev/null

# --- Garage, region eu-west-2 like the plan
cat > "$W/garage.toml" <<EOF
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "$(openssl rand -hex 32)"
[s3_api]
s3_region = "eu-west-2"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"
[admin]
api_bind_addr = "[::]:3903"
admin_token = "$(openssl rand -base64 32)"
EOF
docker run -d --name fpmove-garage --network $NET -v "$W/garage.toml:/etc/garage.toml:ro" $GARAGE_IMG >/dev/null
sleep 4
G() { docker exec fpmove-garage /garage "$@"; }
NODE=$(G status 2>/dev/null | awk '/^[0-9a-f]{16}/{print $1; exit}')
G layout assign -z dc1 -c 1G "$NODE" >/dev/null
G layout apply --version 1 >/dev/null
G bucket create documents >/dev/null
KEYOUT=$(G key create migration-test)
GK=$(echo "$KEYOUT" | awk -F': *' '/Key ID/{print $2}' | tr -d ' ')
GS=$(echo "$KEYOUT" | awk -F': *' '/Secret key/{print $2}' | tr -d ' ')
G bucket allow --read --write --owner documents --key migration-test >/dev/null

cat > "$W/rclone.conf" <<EOF
[old]
type = s3
provider = Minio
endpoint = http://fpmove-minio:9000
access_key_id = $MU
secret_access_key = $MP
region = eu-west-2

[garage]
type = s3
provider = Other
endpoint = http://fpmove-garage:3900
access_key_id = $GK
secret_access_key = $GS
region = eu-west-2
force_path_style = true
EOF
chmod 600 "$W/rclone.conf"

RCLONE="docker run --rm --network $NET -u $(id -u):$(id -g) -v $W:$W $RC_IMG"
rc() { $RCLONE --config "$W/rclone.conf" "$@"; }
export RCLONE RCLONE_CONF="$W/rclone.conf" LOG_DIR="$W/logs"
M() { "$HERE/move_to_garage.sh" "$@"; }

# --- 2,000 test files, 1-300 KB, names like Odoo's name_with_id keys
mkdir -p "$W/files"
for i in $(seq 1 2000); do
  head -c $(( (RANDOM % 300 + 1) * 1024 )) /dev/urandom > "$W/files/land-certificate-$i-$((100000+i)).webp"
done
sleep 2
rc mkdir old:documents
rc copy "$W/files" old:documents --transfers 16 -q
n=$(rc lsf old:documents | wc -l); [ "$n" -eq 2000 ] && ok "MinIO has 2000 test files" || bad "MinIO has $n files"

# 1. full copy
M copy && ok "copy finished" || bad "copy failed"
n=$(rc lsf garage:documents | wc -l); [ "$n" -eq 2000 ] && ok "Garage has 2000 files" || bad "Garage has $n files"
# 2. check passes
M check && ok "check passes after copy" || bad "check failed after copy"
# 3. running copy again copies nothing new
M copy >/dev/null && ok "copy runs again safely" || bad "second copy failed"
# 4. new uploads during the move -> catchup
for i in 2001 2002 2003; do head -c 5000 /dev/urandom > "$W/new-$i.webp"; rc copyto "$W/new-$i.webp" "old:documents/land-certificate-$i-$((100000+i)).webp"; done
if M check >/dev/null 2>&1; then bad "check should fail with 3 new files"; else ok "check reports the 3 new files as missing"; fi
M catchup 1 && ok "catchup copied the new files" || bad "catchup failed"
M check && ok "check passes after catchup" || bad "check failed after catchup"
# 5. a damaged file in Garage is caught
head -c 7000 /dev/urandom > "$W/bad.webp"; rc copyto "$W/bad.webp" garage:documents/land-certificate-10-100010.webp
if M check >/dev/null 2>&1; then bad "check should catch the damaged file"; else ok "check catches a damaged file"; fi
grep -q "land-certificate-10-100010.webp" "$W"/logs/*-check-differ.txt && ok "the damaged file is named in the report" || bad "damaged file not in report"
# 6. MinIO untouched
n=$(rc lsf old:documents | wc -l); [ "$n" -eq 2003 ] && ok "MinIO still has all 2003 files" || bad "MinIO has $n files"
# 7. the key never appears in the logs
if grep -rq -- "$MP\|$GS" "$W/logs"; then bad "a secret appears in the logs"; else ok "no secret in the logs"; fi
M size

echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
