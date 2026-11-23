#!/usr/bin/env bash
# Does the Gen2 registry's storage client (minio-py, as in openg2p_registry_core
# helpers/document/minio_client.py) work against Garage? Local containers only.
# Checks: bucket_exists, put/get, presigned GET fetched over plain HTTP (what a
# browser does), reading an object copied from the farmer profile under its
# Odoo key, a read-only key for presigned URLs, and remove_object.
set -euo pipefail
W="$(mktemp -d)"
NET=fpgen2-test
GARAGE_IMG=dxflrs/garage:v2.1.0
cleanup() { docker rm -f fpgen2-garage >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; rm -rf "$W"; }
trap cleanup EXIT
cleanup; W="$(mktemp -d)"
docker network create $NET >/dev/null
cat > "$W/garage.toml" <<EOF
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "lmdb"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "127.0.0.1:3901"
rpc_secret = "$(openssl rand -hex 32)"
[s3_api]
s3_region = "${REGION:-us-east-1}"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"
[admin]
api_bind_addr = "[::]:3903"
admin_token = "$(openssl rand -base64 32)"
EOF
docker run -d --name fpgen2-garage --network $NET -p 127.0.0.1:39000:3900 \
  -v "$W/garage.toml:/etc/garage.toml:ro" $GARAGE_IMG >/dev/null
sleep 4
G() { docker exec fpgen2-garage /garage "$@"; }
NODE=$(G status 2>/dev/null | awk '/^[0-9a-f]{16}/{print $1; exit}')
G layout assign -z dc1 -c 1G "$NODE" >/dev/null
G layout apply --version 1 >/dev/null
for b in documents default templates import-files export-files; do G bucket create "$b" >/dev/null; done
RW_OUT=$(G key create gen2-registry); RO_OUT=$(G key create gen2-registry-read)
RW_ID=$(echo "$RW_OUT" | awk -F': *' '/Key ID/{print $2}' | tr -d ' ');  RW_SK=$(echo "$RW_OUT" | awk -F': *' '/Secret key/{print $2}' | tr -d ' ')
RO_ID=$(echo "$RO_OUT" | awk -F': *' '/Key ID/{print $2}' | tr -d ' ');  RO_SK=$(echo "$RO_OUT" | awk -F': *' '/Secret key/{print $2}' | tr -d ' ')
for b in documents default templates import-files export-files; do
  G bucket allow --read --write "$b" --key gen2-registry >/dev/null
  G bucket allow --read "$b" --key gen2-registry-read >/dev/null
done

PY="${PYTHON:-python3}"
RW_ID=$RW_ID RW_SK=$RW_SK RO_ID=$RO_ID RO_SK=$RO_SK $PY - <<'EOF'
import io, os, urllib.request
from datetime import timedelta
from minio import Minio
ep = "127.0.0.1:39000"
rw = Minio(ep, access_key=os.environ["RW_ID"], secret_key=os.environ["RW_SK"], secure=False)
ro = Minio(ep, access_key=os.environ["RO_ID"], secret_key=os.environ["RO_SK"], secure=False)
res = []
def check(name, cond): res.append(cond); print(("PASS: " if cond else "FAIL: ") + name)

check("bucket_exists('documents') (HeadBucket)", rw.bucket_exists("documents"))
# a farmer profile file, as the move leaves it: Odoo's key at the bucket root
odoo_key = "land-certificate-1484638-2201913.webp"
data = os.urandom(150_000)
rw.put_object("documents", odoo_key, io.BytesIO(data), len(data), content_type="image/webp")
# a Gen2 upload: uuid4().hex key
gen2_key = "0f8e1c2a9b7d4e6f8a1b2c3d4e5f6a7b"
rw.put_object("documents", gen2_key, io.BytesIO(b"pdf-bytes"), 9, content_type="application/pdf")
r = rw.get_object("documents", odoo_key); got = r.read(); r.close(); r.release_conn()
check("download of a moved farmer profile file by its Odoo key", got == data)
url = ro.presigned_get_object("documents", odoo_key, expires=timedelta(hours=1))
with urllib.request.urlopen(url) as resp:
    body, ctype = resp.read(), resp.headers.get("Content-Type")
check("presigned URL (read-only key) opens the file like a browser would", body == data)
check(f"content type served: {ctype}", ctype == "image/webp")
try:
    ro.put_object("documents", "should-fail", io.BytesIO(b"x"), 1)
    check("read-only key cannot write", False)
except Exception:
    check("read-only key cannot write", True)
rw.remove_object("documents", gen2_key)
check("remove_object", not any(o.object_name == gen2_key for o in rw.list_objects("documents")))
print("RESULT:", sum(res), "passed,", len(res) - sum(res), "failed")
raise SystemExit(0 if all(res) else 1)
EOF
# the farmer profile's clients (Odoo boto3 1.15.18 / ODK import 1.35.36), when their Pythons are given
for py in ${FP_PYTHONS:-}; do
  EP=http://127.0.0.1:39000 REGION="${REGION:-us-east-1}" KID=$RW_ID KSK=$RW_SK "$py" "$(dirname "$0")/test_fp_clients.py"
done
