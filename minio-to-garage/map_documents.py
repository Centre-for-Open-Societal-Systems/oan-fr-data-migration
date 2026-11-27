#!/usr/bin/env python3
"""Link the moved farmer documents to their Gen2 records (Part B of the document migration).

Runs after move_to_garage.sh has copied the bucket and after the database migration
has loaded the records. The object keys do not change: Gen2 registers each Garage
object under its MinIO key, and keeps the Gen1 file id next to it, so every document
can be checked against its record after the migration.

  python map_documents.py plan              build the document map; writes nothing to Gen2
  python map_documents.py apply             register the documents in Gen2 and link them to the records
  python map_documents.py fix-types         set the image type on Garage objects stored as binary/octet-stream
  python map_documents.py validate [--sample N]   check every linked document against its record
  python map_documents.py evidence FR-...   one farmer, from Gen1 through MinIO and Garage to Gen2

Settings (environment or .env next to this script, as in the database migration):
  SOURCE_DSN   the Gen1 farmer profile (Odoo) database, libpq form; only read
  TARGET_DSN   the Gen2 registry database (postgresql:// or postgresql+psycopg2://)
  RCLONE_CONF  the rclone config with the [old] (MinIO) and [garage] remotes (default ./rclone.conf)
  BUCKET       default documents;  LOG_DIR default ./logs;  WORKERS default 16

Gen1 and MinIO are only read. In Gen2 it writes g2p_registry_documents,
g2p_register_section_documents, g2p_register_lands.certificate_storage_id and
migration.document_map, and nothing else. A second run changes nothing.
Exit code: 0 = clean, 1 = something to resolve (see the run's report), 2 = setup error.
"""
import argparse
import collections
import configparser
import csv
import datetime
import hashlib
import os
import random
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))

# Same namespace and naming as the database migration (farmer_profile/transform.py),
# so a document's Gen2 id is worked out from its Gen1 file id, and a rerun gives the same id.
NAMESPACE = uuid.UUID("5b0c7f0e-6f43-4c2e-9a39-6d0f0a7c2f11")
MIGRATION_USER = "farmer-profile-migration"

# Gen2's farmer documents section (12_form_sections.sql): each category has 5 file slots
# labelled <category>_1 .. <category>_5.
SECTION = "farmer_documents"
SLOTS = 5
CATEGORY_BY_TAG = {"land certificate": "land_document"}
DEFAULT_CATEGORY = "other_document"

LINKED = "ok"  # the only status that is linked in Gen2

MAP_COLUMNS = [
    "entity", "gen1_record_id", "functional_record_id", "gen2_internal_record_id", "document_kind", "label",
    "gen1_storage_file_id", "minio_bucket", "minio_key", "file_name", "gen1_checksum", "size", "mimetype",
    "gen2_document_id", "garage_bucket", "garage_key", "status", "note",
]

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS migration;
-- One row per Gen1 document reference: the old MinIO reference, the new Garage
-- reference and the Gen2 record, so each document can be validated per record.
CREATE TABLE IF NOT EXISTS migration.document_map (
  entity                  text   NOT NULL,   -- land or farmer
  gen1_record_id          bigint NOT NULL,   -- Odoo id of the land or the farmer
  gen1_storage_file_id    bigint NOT NULL,   -- the old MinIO reference: Gen1 storage_file.id
  functional_record_id    text,              -- the farmer's FR- id
  gen2_internal_record_id text,              -- the Gen2 land or farmer
  document_kind           text,              -- land_certificate, land_document, other_document
  label                   text,              -- the slot in Gen2's farmer documents section
  minio_bucket            text,
  minio_key               text,
  file_name               text,
  gen1_checksum           text,              -- SHA-1, as Odoo computed it
  size                    bigint,
  mimetype                text,
  gen2_document_id        text,              -- the new reference: g2p_registry_documents.document_id
  garage_bucket           text,
  garage_key              text,
  status                  text   NOT NULL,
  note                    text,
  run_id                  text,
  updated_at              timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (entity, gen1_record_id, gen1_storage_file_id)
);
"""

# Every Gen1 file row: its key in MinIO is the backend's directory (empty for ATI) + relative_path
FILES = """
SELECT f.id, f.name, f.relative_path, f.file_size, f.checksum, f.mimetype, f.active, f.to_delete,
       f.registrant_id, f.create_date, u.login AS created_by, {directory} AS directory,
       (SELECT string_agg(t.name, ', ' ORDER BY t.name)
          FROM g2p_document_tag_storage_file_rel r JOIN g2p_document_tag t ON t.id = r.g2p_document_tag_id
         WHERE r.storage_file_id = f.id) AS tags
  FROM storage_file f
  LEFT JOIN res_users u ON u.id = f.create_uid
  LEFT JOIN storage_backend b ON b.id = f.backend_id
"""
LANDS = "SELECT id, partner_id, land_certificate, certficate_provided FROM g2p_land_information WHERE land_certificate IS NOT NULL"


class SetupError(Exception):
    pass


# -- settings and connections --------------------------------------------------------------

def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def setting(name, default=None):
    value = os.environ.get(name, default)
    if value in (None, ""):
        raise SetupError(f"{name} is not set (environment or .env)")
    return value


def connect(name, readonly):
    import psycopg2
    dsn = setting(name).replace("postgresql+psycopg2://", "postgresql://").replace("postgres+psycopg2://", "postgres://")
    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.OperationalError as e:
        raise SetupError(f"cannot connect with {name}: {str(e).strip()}") from None
    conn.set_session(readonly=readonly)
    return conn


def rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


class Store:
    """One S3 remote of rclone.conf ([old] = MinIO, [garage] = Garage), through boto3."""

    def __init__(self, remote):
        import boto3
        from botocore.config import Config
        conf_path = os.environ.get("RCLONE_CONF", os.path.join(HERE, "rclone.conf"))
        conf = configparser.ConfigParser()
        if not conf.read(conf_path):
            raise SetupError(f"no rclone config at {conf_path}")
        if remote not in conf:
            raise SetupError(f"remote [{remote}] is not in {conf_path}")
        c = conf[remote]
        self.name = {"old": "MinIO", "garage": "Garage"}.get(remote, remote)
        self.bucket = os.environ.get("BUCKET", "documents")
        self.client = boto3.client(
            "s3", endpoint_url=c.get("endpoint"), aws_access_key_id=c.get("access_key_id"),
            aws_secret_access_key=c.get("secret_access_key"), region_name=c.get("region", "us-east-1"),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          retries={"max_attempts": 5, "mode": "standard"}, max_pool_connections=64))

    def listing(self):
        """key -> size of every object in the bucket."""
        out = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket):
            for o in page.get("Contents", []):
                out[o["Key"]] = o["Size"]
        return out

    def head(self, key):
        """size, content type and date of one object, or None when it is not there."""
        from botocore.exceptions import ClientError
        try:
            h = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return {"size": h["ContentLength"], "type": h.get("ContentType"), "date": h.get("LastModified")}

    def sha1(self, key):
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        digest = hashlib.sha1()
        for chunk in iter(lambda: body.read(1 << 20), b""):
            digest.update(chunk)
        return digest.hexdigest()

    def set_type(self, key, content_type):
        """Change only the object's content type: a copy onto itself, in this store only."""
        self.client.copy_object(Bucket=self.bucket, Key=key, CopySource={"Bucket": self.bucket, "Key": key},
                                ContentType=content_type, MetadataDirective="REPLACE")


def document_id(storage_file_id):
    return str(uuid.uuid5(NAMESPACE, f"farmer-profile/document/{storage_file_id}"))


def is_image(mimetype):
    return bool(mimetype) and mimetype.lower().startswith("image/")


def run_dir(command):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(os.environ.get("LOG_DIR", os.path.join(HERE, "logs")), f"{stamp}-{command}")
    os.makedirs(path, exist_ok=True)
    return stamp, path


def write_csv(path, header, data):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)


def parallel(fn, items):
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", "16"))) as pool:
        return list(pool.map(fn, items))


# -- the document map ------------------------------------------------------------------------

def gen1_files(src):
    has_dir = rows(src, "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'storage_backend' AND column_name = 'directory_path'")
    files = {}
    for f in rows(src, FILES.format(directory="b.directory_path" if has_dir else "NULL")):
        directory = (f.pop("directory") or "").strip("/")
        f["key"] = f"{directory}/{f['relative_path']}" if directory else f["relative_path"]
        files[f["id"]] = f
    return files


def gen2_ids(dst):
    """(kind, Odoo id) -> Gen2 id, from the database migration's migrated_record; and Gen2 id -> FR- id."""
    if not rows(dst, "SELECT 1 FROM information_schema.tables "
                     "WHERE table_schema = 'migration' AND table_name = 'migrated_record'"):
        raise SetupError("migration.migrated_record is not in the Gen2 database: run the database migration first")
    migrated = {(r["kind"], r["odoo_id"]): r["gen2_id"]
                for r in rows(dst, "SELECT kind, odoo_id, gen2_id FROM migration.migrated_record "
                                   "WHERE kind IN ('farmer', 'land')")}
    fr = {r["internal_record_id"]: r["functional_record_id"]
          for r in rows(dst, "SELECT internal_record_id, functional_record_id FROM g2p_register_farmers")}
    return migrated, fr


def build_map(src, dst, minio, garage):
    """Every Gen1 document reference as a document map row, plus the MinIO objects no Gen1 file names."""
    files = gen1_files(src)
    migrated, fr = gen2_ids(dst)
    in_minio, in_garage = minio.listing(), garage.listing()
    bucket = minio.bucket

    refs = []  # (entity, record id, farmer id, file id, kind)
    for land in rows(src, LANDS):
        refs.append(("land", land["id"], land["partner_id"], land["land_certificate"], "land_certificate",
                     land["certficate_provided"]))
    for f in sorted(files.values(), key=lambda f: f["id"]):
        if f["registrant_id"]:
            tags = [t.strip().lower() for t in (f["tags"] or "").split(",") if t.strip()]
            kind = next((CATEGORY_BY_TAG[t] for t in tags if t in CATEGORY_BY_TAG), DEFAULT_CATEGORY)
            refs.append(("farmer", f["registrant_id"], f["registrant_id"], f["id"], kind, None))

    out, slots = [], collections.Counter()
    for entity, record_id, farmer_id, file_id, kind, provided in refs:
        f = files.get(file_id)
        gen2_farmer = migrated.get(("farmer", farmer_id))
        row = {
            "entity": entity, "gen1_record_id": record_id, "gen1_storage_file_id": file_id,
            "functional_record_id": fr.get(gen2_farmer), "gen2_internal_record_id": migrated.get((entity, record_id)),
            "document_kind": kind, "label": None, "minio_bucket": bucket, "garage_bucket": bucket,
            "gen2_document_id": document_id(file_id), "note": None,
            "_created_by": f["created_by"] if f else None, "_created_at": f["create_date"] if f else None,
        }
        if f is None:
            row.update(status="no_gen1_file", note="the record names a file that is not in storage_file")
            out.append(row)
            continue
        row.update(minio_key=f["key"], garage_key=f["key"], file_name=f["name"], gen1_checksum=f["checksum"],
                   size=f["file_size"], mimetype=f["mimetype"])
        garage_size = in_garage.get(f["key"])
        if not f["active"] or f["to_delete"]:
            row.update(status="inactive", note="archived or marked for deletion in Gen1: not linked")
        elif not is_image(f["mimetype"]):
            row.update(status="not_image", note=f"type {f['mimetype']}: only images are migrated")
        elif row["gen2_internal_record_id"] is None:
            row.update(status="not_migrated", note=f"the {entity} is not in migration.migrated_record")
        elif f["key"] not in in_minio and garage_size is None:
            row.update(status="missing_in_minio", note="Gen1 has the file, MinIO does not")
        elif garage_size is None:
            row.update(status="missing", note="in MinIO, not in Garage: run move_to_garage.sh catchup")
        elif f["file_size"] is not None and garage_size != f["file_size"]:
            row.update(status="differs", note=f"size in Garage {garage_size}, in Gen1 {f['file_size']}")
        else:
            row["status"] = LINKED
        if entity == "farmer" and row["status"] == LINKED:
            slots[(record_id, kind)] += 1
            n = slots[(record_id, kind)]
            row["label"] = f"{kind}_{n}"
            if n > SLOTS:
                row.update(status="over_slots", label=None,
                           note=f"more than {SLOTS} {kind} files: Gen2 shows {SLOTS} per category")
        if entity == "land" and row["status"] == LINKED and provided is False:
            row["note"] = "Gen1 had certficate_provided = false: set to true, as Gen2 does for a land with a file"
        out.append(row)

    known = {f["key"] for f in files.values()}
    orphans = [{"minio_bucket": bucket, "minio_key": k, "size": s, "status": "orphan",
                "note": "object in MinIO with no Gen1 storage_file row: not linked"}
               for k, s in sorted(in_minio.items()) if k not in known]
    return out, orphans, files


def summarise(map_rows, orphans):
    counts = collections.Counter(r["status"] for r in map_rows)
    counts["orphan"] = len(orphans)
    return counts


def print_counts(title, counts):
    print(title)
    for status in [LINKED, "missing_in_minio", "missing", "differs", "not_migrated", "inactive", "not_image",
                   "over_slots", "slot_taken", "kept_gen2", "key_taken", "no_gen1_file", "orphan"]:
        if counts.get(status):
            print(f"  {status:<17} {counts[status]}")


# -- commands ------------------------------------------------------------------------------------

def cmd_plan(args, write=False):
    src, dst = connect("SOURCE_DSN", True), connect("TARGET_DSN", not write)
    minio, garage = Store("old"), Store("garage")
    stamp, folder = run_dir("apply" if write else "plan")
    map_rows, orphans, _ = build_map(src, dst, minio, garage)
    if write:
        apply(dst, map_rows, stamp)
    write_csv(os.path.join(folder, "document-map.csv"), MAP_COLUMNS, map_rows)
    write_csv(os.path.join(folder, "orphans.csv"), ["minio_bucket", "minio_key", "size", "status", "note"], orphans)
    write_csv(os.path.join(folder, "to-resolve.csv"), MAP_COLUMNS,
              [r for r in map_rows if r["status"] != LINKED])
    counts = summarise(map_rows, orphans)
    print_counts(f"{'Applied' if write else 'Plan'}: {len(map_rows)} Gen1 document references; "
                 f"reports in {folder}", counts)
    if not write:
        print(f"Nothing was written. 'apply' links the {counts[LINKED]} rows with status ok.")
    return 0 if counts[LINKED] == len(map_rows) and not orphans else 1


def apply(dst, map_rows, run_id):
    """Register and link the rows with status ok, in batches; every row goes to migration.document_map."""
    from psycopg2.extras import execute_values
    with dst, dst.cursor() as cur:
        cur.execute(SCHEMA)
    for start in range(0, len(map_rows), 500):
        batch = map_rows[start:start + 500]
        with dst, dst.cursor() as cur:
            for r in batch:
                if r["status"] == LINKED:
                    link(cur, r)
            execute_values(cur, f"""
                INSERT INTO migration.document_map ({", ".join(MAP_COLUMNS)}, run_id) VALUES %s
                ON CONFLICT (entity, gen1_record_id, gen1_storage_file_id) DO UPDATE SET
                {", ".join(f"{c} = EXCLUDED.{c}" for c in MAP_COLUMNS
                           if c not in ("entity", "gen1_record_id", "gen1_storage_file_id"))},
                run_id = EXCLUDED.run_id, updated_at = clock_timestamp()""",
                [tuple(r.get(c) for c in MAP_COLUMNS) + (run_id,) for r in batch])


def link(cur, r):
    doc = r["gen2_document_id"]
    cur.execute("SELECT document_id FROM g2p_registry_documents WHERE document_store_id = %s", (r["garage_key"],))
    found = cur.fetchone()
    if found and found[0] != doc:
        r.update(status="key_taken", note=f"Gen2 document {found[0]} already uses this key: not linked")
        return
    cur.execute("""INSERT INTO g2p_registry_documents (document_id, document_store_id, bucket, source_filename,
                       created_by, created_at)
                   VALUES (%s, %s, %s, %s, %s, COALESCE(%s::timestamp, now() AT TIME ZONE 'utc'))
                   ON CONFLICT (document_id) DO NOTHING""",
                (doc, r["garage_key"], r["garage_bucket"], r["file_name"] or r["garage_key"],
                 r.get("_created_by") or MIGRATION_USER, r.get("_created_at")))
    if r["entity"] == "land":
        cur.execute("""UPDATE g2p_register_lands SET certificate_storage_id = %s, certificate_provided = true
                        WHERE internal_record_id = %s AND (certificate_storage_id IS NULL OR certificate_storage_id = %s)""",
                    (doc, r["gen2_internal_record_id"], doc))
        if cur.rowcount == 0:
            r.update(status="kept_gen2", note="the Gen2 land already has another certificate: kept, not replaced")
    else:
        cur.execute("""SELECT document_id FROM g2p_register_section_documents
                        WHERE internal_record_id = %s AND section_id = %s AND label = %s""",
                    (r["gen2_internal_record_id"], SECTION, r["label"]))
        taken = cur.fetchone()
        if taken and taken[0] != doc:
            r.update(status="slot_taken", note=f"slot {r['label']} already holds Gen2 document {taken[0]}")
            return
        cur.execute("""INSERT INTO g2p_register_section_documents (internal_record_id, document_id, section_id, label)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (r["gen2_internal_record_id"], doc, SECTION, r["label"]))


def cmd_apply(args):
    return cmd_plan(args, write=True)


def linked_rows(dst):
    if not rows(dst, "SELECT 1 FROM information_schema.tables "
                     "WHERE table_schema = 'migration' AND table_name = 'document_map'"):
        raise SetupError("migration.document_map is not there yet: run 'apply' first")
    return rows(dst, f"SELECT {', '.join(MAP_COLUMNS)} FROM migration.document_map WHERE status = %s "
                     "ORDER BY entity, gen1_record_id, gen1_storage_file_id", (LINKED,))


def cmd_fix_types(args):
    dst, garage = connect("TARGET_DSN", True), Store("garage")
    _, folder = run_dir("fix-types")
    by_key = {}
    for r in linked_rows(dst):
        if is_image(r["mimetype"]):
            by_key[r["garage_key"]] = r["mimetype"]

    def check(item):
        key, mimetype = item
        h = garage.head(key)
        if h is None:
            return {"garage_key": key, "result": "not in Garage"}
        if h["type"] == mimetype:
            return None
        garage.set_type(key, mimetype)
        after = garage.head(key)
        ok = after and after["type"] == mimetype and after["size"] == h["size"]
        return {"garage_key": key, "type_before": h["type"], "type_after": after and after["type"],
                "result": "fixed" if ok else "FAILED"}

    changed = [x for x in parallel(check, sorted(by_key.items())) if x]
    write_csv(os.path.join(folder, "fix-types.csv"), ["garage_key", "type_before", "type_after", "result"], changed)
    fixed = sum(1 for x in changed if x["result"] == "fixed")
    print(f"Checked {len(by_key)} Garage objects: {fixed} type set from Gen1, "
          f"{len(changed) - fixed} failed or missing. Report: {folder}/fix-types.csv")
    return 0 if fixed == len(changed) else 1


def cmd_validate(args):
    src, dst = connect("SOURCE_DSN", True), connect("TARGET_DSN", True)
    minio, garage = Store("old"), Store("garage")
    _, folder = run_dir("validate")
    stored = rows(dst, f"SELECT {', '.join(MAP_COLUMNS)} FROM migration.document_map") if rows(
        dst, "SELECT 1 FROM information_schema.tables WHERE table_schema = 'migration' "
             "AND table_name = 'document_map'") else None
    if stored is None:
        raise SetupError("migration.document_map is not there yet: run 'apply' first")
    linked = [r for r in stored if r["status"] == LINKED]
    sample = linked
    if args.sample and args.sample < len(linked):
        sample = random.Random(args.sample).sample(linked, args.sample)

    docs = {r["document_id"]: r for r in rows(
        dst, "SELECT document_id, document_store_id, bucket FROM g2p_registry_documents WHERE document_id = ANY(%s)",
        ([r["gen2_document_id"] for r in sample],))}
    lands = {r["internal_record_id"]: r["certificate_storage_id"] for r in rows(
        dst, "SELECT internal_record_id, certificate_storage_id FROM g2p_register_lands "
             "WHERE internal_record_id = ANY(%s)", ([r["gen2_internal_record_id"] for r in sample if r["entity"] == "land"],))}
    sections = {(r["internal_record_id"], r["document_id"]) for r in rows(
        dst, "SELECT internal_record_id, document_id FROM g2p_register_section_documents "
             "WHERE section_id = %s AND internal_record_id = ANY(%s)",
        (SECTION, [r["gen2_internal_record_id"] for r in sample if r["entity"] == "farmer"]))}

    def check(r):
        problems = []
        doc = docs.get(r["gen2_document_id"])
        if doc is None:
            problems.append("no Gen2 document row")
        elif doc["document_store_id"] != r["garage_key"] or doc["bucket"] != r["garage_bucket"]:
            problems.append(f"Gen2 document points at {doc['bucket']}/{doc['document_store_id']}")
        if r["entity"] == "land" and lands.get(r["gen2_internal_record_id"]) != r["gen2_document_id"]:
            problems.append("the land's certificate_storage_id is not this document")
        if r["entity"] == "farmer" and (r["gen2_internal_record_id"], r["gen2_document_id"]) not in sections:
            problems.append("not in the farmer's documents section")
        h = garage.head(r["garage_key"])
        if h is None:
            problems.append("object not in Garage")
        else:
            if r["size"] is not None and h["size"] != r["size"]:
                problems.append(f"size {h['size']} in Garage, {r['size']} in Gen1")
            if not is_image(h["type"]):
                problems.append(f"Garage type {h['type']}: run fix-types")
            if r["gen1_checksum"] and garage.sha1(r["garage_key"]) != r["gen1_checksum"]:
                problems.append("SHA-1 in Garage differs from Gen1")
        return {**r, "result": "PASS" if not problems else "FAIL", "problems": "; ".join(problems)}

    results = parallel(check, sample)

    # Both ways: every Gen1 reference has a map row, every map row has a Gen1 reference
    current, _, _ = build_map(src, dst, minio, garage)
    gen1 = {(r["entity"], r["gen1_record_id"], r["gen1_storage_file_id"]) for r in current}
    mapped = {(r["entity"], r["gen1_record_id"], r["gen1_storage_file_id"]) for r in stored}
    not_mapped, no_ref = sorted(gen1 - mapped), sorted(mapped - gen1)

    write_csv(os.path.join(folder, "validate.csv"), MAP_COLUMNS + ["result", "problems"], results)
    write_csv(os.path.join(folder, "not-in-map.csv"), ["entity", "gen1_record_id", "gen1_storage_file_id", "problem"],
              [dict(zip(["entity", "gen1_record_id", "gen1_storage_file_id"], k), problem="Gen1 reference with no map row")
               for k in not_mapped] +
              [dict(zip(["entity", "gen1_record_id", "gen1_storage_file_id"], k), problem="map row with no Gen1 reference")
               for k in no_ref])
    failed = [x for x in results if x["result"] == "FAIL"]
    others = collections.Counter(r["status"] for r in stored if r["status"] != LINKED)
    print(f"Validated {len(results)} of {len(linked)} linked documents"
          f"{' (sample)' if len(results) < len(linked) else ''}: {len(results) - len(failed)} pass, {len(failed)} fail.")
    print(f"Gen1 references not in the map: {len(not_mapped)}   map rows with no Gen1 reference: {len(no_ref)}")
    if others:
        print("Not linked, by status (see the apply run's to-resolve.csv): "
              + ", ".join(f"{k} {v}" for k, v in sorted(others.items())))
    print(f"Reports: {folder}/validate.csv, not-in-map.csv")
    clean = not failed and not not_mapped and not no_ref
    print("Validation passed." if clean else "Validation FAILED.")
    return 0 if clean else 1


def cmd_evidence(args):
    src, dst = connect("SOURCE_DSN", True), connect("TARGET_DSN", True)
    minio, garage = Store("old"), Store("garage")
    stamp, _ = run_dir("evidence")
    log_dir = os.environ.get("LOG_DIR", os.path.join(HERE, "logs"))
    out_path = os.path.join(log_dir, f"{stamp}-evidence-{args.fr_id}.txt")
    lines, ok = [], [True]

    def say(text=""):
        lines.append(text)
        print(text)

    def verdict(cond, text):
        ok[0] &= bool(cond)
        say(f"  [{'PASS' if cond else 'FAIL'}] {text}")

    farmer = rows(dst, "SELECT internal_record_id FROM g2p_register_farmers WHERE functional_record_id = %s",
                  (args.fr_id,))
    if not farmer:
        raise SetupError(f"no Gen2 farmer with functional_record_id {args.fr_id}")
    gen2_farmer = farmer[0]["internal_record_id"]
    odoo = rows(dst, "SELECT odoo_id FROM migration.migrated_record WHERE kind = 'farmer' AND gen2_id = %s",
                (gen2_farmer,))
    if not odoo:
        raise SetupError(f"{args.fr_id} is not a migrated farmer (not in migration.migrated_record)")
    odoo_farmer = odoo[0]["odoo_id"]
    files = gen1_files(src)
    lands = rows(src, "SELECT id, land_certificate FROM g2p_land_information WHERE partner_id = %s ORDER BY id",
                 (odoo_farmer,))
    refs = [("land", l["id"], l["land_certificate"]) for l in lands if l["land_certificate"]]
    refs += [("farmer", odoo_farmer, f["id"]) for f in sorted(files.values(), key=lambda f: f["id"])
             if f["registrant_id"] == odoo_farmer]
    has_map = rows(dst, "SELECT 1 FROM information_schema.tables WHERE table_schema = 'migration' "
                        "AND table_name = 'document_map'")

    say(f"Document migration evidence for {args.fr_id}  ({stamp} UTC)")
    say(f"Gen1 farmer: Odoo res_partner {odoo_farmer}    Gen2 farmer: {gen2_farmer}")
    say(f"Lands in Gen1: {len(lands)}, with a certificate: {sum(1 for l in lands if l['land_certificate'])}; "
        f"documents on the farmer: {sum(1 for r in refs if r[0] == 'farmer')}")
    if not refs:
        say("This farmer has no documents in Gen1: pick another sample farmer.")
        ok[0] = False
    for entity, record_id, file_id in refs:
        f = files.get(file_id)
        say()
        say(f"== {entity} {record_id}: Gen1 storage_file {file_id}")
        if f is None:
            verdict(False, "storage_file row exists in Gen1")
            continue
        say(f"1. Gen1 storage_file: id {f['id']}, name {f['name']}, relative_path {f['relative_path']}, "
            f"size {f['file_size']}, SHA-1 {f['checksum']}, type {f['mimetype']}, tags {f['tags'] or '-'}, "
            f"active {f['active']}")
        m = minio.head(f["key"])
        say(f"2. MinIO {minio.bucket}/{f['key']}: " +
            (f"size {m['size']}, type {m['type']}, date {m['date']}" if m else "NOT FOUND"))
        verdict(m is not None, "the object is in MinIO")
        g = garage.head(f["key"])
        say(f"3. Garage {garage.bucket}/{f['key']}: " +
            (f"size {g['size']}, type {g['type']}, date {g['date']}" if g else "NOT FOUND"))
        verdict(g is not None, "the object is in Garage under the same key")
        if g:
            verdict(g["size"] == f["file_size"], "size in Garage equals Gen1")
            verdict(garage.sha1(f["key"]) == f["checksum"], "SHA-1 in Garage equals Gen1's checksum")
        doc_id = document_id(file_id)
        doc = rows(dst, "SELECT document_id, document_store_id, bucket, source_filename, created_by, created_at "
                        "FROM g2p_registry_documents WHERE document_id = %s", (doc_id,))
        say(f"4. Gen2 g2p_registry_documents {doc_id}: " +
            (", ".join(f"{k} {v}" for k, v in doc[0].items() if k != "document_id") if doc else "NOT FOUND"))
        verdict(doc and doc[0]["document_store_id"] == f["key"], "Gen2 document's storage key is the MinIO key")
        if entity == "land":
            gen2_land = rows(dst, "SELECT gen2_id FROM migration.migrated_record WHERE kind = 'land' AND odoo_id = %s",
                             (record_id,))
            cert = gen2_land and rows(dst, "SELECT certificate_storage_id FROM g2p_register_lands "
                                           "WHERE internal_record_id = %s", (gen2_land[0]["gen2_id"],))
            say(f"5. Gen2 land {gen2_land[0]['gen2_id'] if gen2_land else '(not migrated)'}: certificate_storage_id "
                f"{cert[0]['certificate_storage_id'] if cert else '-'}")
            verdict(cert and cert[0]["certificate_storage_id"] == doc_id, "the Gen2 land points at this document")
        else:
            sec = rows(dst, "SELECT section_id, label FROM g2p_register_section_documents "
                            "WHERE internal_record_id = %s AND document_id = %s", (gen2_farmer, doc_id))
            say(f"5. Gen2 farmer documents section: {sec[0]['section_id'] + ' / ' + sec[0]['label'] if sec else 'NOT FOUND'}")
            verdict(sec, "the file is in the Gen2 farmer's documents section")
        if has_map:
            mrow = rows(dst, f"SELECT {', '.join(MAP_COLUMNS)} FROM migration.document_map WHERE entity = %s "
                             "AND gen1_record_id = %s AND gen1_storage_file_id = %s", (entity, record_id, file_id))
            say("6. Document map row: " + (", ".join(f"{k}={v}" for k, v in mrow[0].items()) if mrow else "NOT FOUND"))
            verdict(mrow and mrow[0]["status"] == LINKED, "document map row with status ok")
        else:
            verdict(False, "migration.document_map exists (run 'apply')")
    say()
    say("Evidence: ALL PASS" if ok[0] else "Evidence: SOMETHING FAILED (see the FAIL lines)")
    os.makedirs(log_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Saved: {out_path}")
    return 0 if ok[0] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="build the document map; write nothing to Gen2")
    sub.add_parser("apply", help="register the documents in Gen2 and link them to their records")
    sub.add_parser("fix-types", help="set the image type on Garage objects stored as binary/octet-stream")
    v = sub.add_parser("validate", help="check every linked document against its record")
    v.add_argument("--sample", type=int, help="check N random linked documents (the full both-ways check still runs)")
    e = sub.add_parser("evidence", help="one farmer from Gen1 through MinIO and Garage to Gen2")
    e.add_argument("fr_id", help="the farmer's FR- id")
    args = p.parse_args(argv)
    load_env()
    try:
        return {"plan": cmd_plan, "apply": cmd_apply, "fix-types": cmd_fix_types,
                "validate": cmd_validate, "evidence": cmd_evidence}[args.command](args)
    except SetupError as e:
        print(f"map_documents: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
