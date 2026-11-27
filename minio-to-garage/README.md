# fp-garage-move

Move the farmer profile documents (land certificate images, bucket `documents`)
from MinIO (172.16.16.231) to Garage, link each one to its Gen2 record, and check
that nothing was lost.

It runs in two parts:

- **Part A, copy** (`move_to_garage.sh`): copies the bucket to Garage under the
  same keys, and compares every file. It never deletes anything and never changes
  MinIO (except `copyback`, which only adds files and is for a rollback).
- **Part B, record mapping** (`map_documents.py`): after the database migration,
  registers each copied file as a Gen2 document under its MinIO key, links it to
  its land or farmer, and keeps the old MinIO reference (the Gen1 `storage_file`
  id) in a document map, so every document can be validated against its record.

## Files

| File | What it is |
|---|---|
| `move_to_garage.sh` | Part A: the copy script (rclone wrapper) |
| `map_documents.py` | Part B: document map, Gen2 links, type fix, validation, evidence |
| `rclone.conf.example` | The two storage connections, without keys (both parts use them) |
| `.env.example` | Part B's database settings |
| `test_local.sh` | Tests Part A against MinIO and Garage in containers (2,000 test files) |
| `test_map_documents.sh` | Tests Part B against Postgres, MinIO and Garage in containers |
| `test_gen2_client.sh`, `test_fp_clients.py` | Test that the Gen2 registry, the farmer profile (Odoo) and the ODK import service work with Garage |

## Set up (on the Garage server)

1. Install rclone 1.59 or later (the official binary; the Ubuntu package can be too old).
2. `cp rclone.conf.example rclone.conf`, fill in the keys, `chmod 600 rclone.conf`.
3. For Part B: Python 3.10 or later with `boto3` and `psycopg2`;
   `cp .env.example .env`, fill in, `chmod 600 .env`.

`rclone.conf`, `.env` and `logs/` are git-ignored: keys never go into the repo.

## Part A: copy

```
./move_to_garage.sh size            # files and bytes in MinIO and Garage
./move_to_garage.sh list            # every MinIO object: key, size, date, type (the baseline)
./move_to_garage.sh copy            # copy every document (safe to stop and run again)
./move_to_garage.sh check           # compare every file: name, size, MD5
./move_to_garage.sh catchup 48      # copy only files added in the last 48 hours
./move_to_garage.sh copyback 24     # ROLLBACK ONLY: files added to Garage in the last 24 h back to MinIO
```

Order during the move: `size` and `list` (baseline) → `copy` (off-hours) → `check`
(must show 0 missing, 0 different) → `catchup` once a day until the switch → on
switch day: `catchup`, switch the farmer profile to Garage, `catchup` again, final `check`.

`copyback` asks for `yes` first (or `YES=1`). It only adds files MinIO does not
have; it never overwrites or deletes.

The copy never replaces a file that is newer in Garage (rclone `--update`), so the
`catchup` after the switch cannot overwrite a document the farmer profile has
already written to Garage. Before the switch this changes nothing: Garage only has
what was copied from MinIO. After the switch, the final `check` lists such a file
as different; that is expected, and the Garage version is the one to keep.

Options (environment): `BWLIMIT=50M` to slow the copy if MinIO gets slow for users,
`TRANSFERS` / `CHECKERS` (default 32 / 64), `BUCKET` (default `documents`).

## Part B: record mapping

Runs after the database migration (it reads `migration.migrated_record`) and after
the copy. Gen1 and MinIO are only read.

```
python map_documents.py plan              # the document map, with a status per reference; writes nothing
python map_documents.py apply             # register and link the rows with status ok (safe to run again)
python map_documents.py fix-types         # Garage objects stored as binary/octet-stream get their image type
python map_documents.py validate          # every linked document against its record; --sample 100 for DM-10
python map_documents.py evidence FR-...   # one farmer from Gen1 to Gen2: the evidence report for sign-off
```

Order: `plan` → resolve what it lists → `apply` → `fix-types` → `validate`
(must pass) → `evidence` for the sample farmer.

What `apply` writes in Gen2, and nothing else:

| Gen1 | Gen2 |
|---|---|
| `storage_file` (id, `relative_path`, name, creator, date) | `g2p_registry_documents`: `document_id` = UUID5 of the file id, `document_store_id` = the MinIO key, bucket `documents` |
| `g2p_land_information.land_certificate` | `g2p_register_lands.certificate_storage_id` (and `certificate_provided` = true) |
| `storage_file.registrant_id` (the farmer's documents) | `g2p_register_section_documents`, section `farmer_documents`: tag *Land Certificate* to slots `land_document_1..5`, other files to `other_document_1..5` |
| — | `migration.document_map`: one row per Gen1 reference, with the old and new reference |

A Gen2 land that already has another certificate, or a slot that already holds
another file, is not changed: the row is reported (`kept_gen2`, `slot_taken`).

Statuses in the document map:

| Status | Meaning | Linked |
|---|---|---|
| `ok` | In Garage, same size as Gen1 | Yes |
| `missing_in_minio` | Gen1 has the file, MinIO does not: list for ATI | No |
| `missing` | In MinIO, not in Garage: run `catchup` | No |
| `differs` | Size in Garage differs from Gen1 | No |
| `not_migrated` | The land or farmer is not in `migrated_record` | No |
| `inactive` | Archived or marked for deletion in Gen1 | No |
| `not_image` | Not an image: out of scope | No |
| `over_slots` | More than 5 files of one category on a farmer | No |
| `orphan` | A MinIO object no Gen1 file names (in `orphans.csv`) | No |

Each run writes a folder under `logs/`: `document-map.csv`, `to-resolve.csv`,
`orphans.csv`; `validate.csv` and `not-in-map.csv`; `fix-types.csv`; and the
evidence report `logs/<time>-evidence-<FR id>.txt`.

Exit code (both parts): 0 = clean, 1 = something missing, different or to resolve, 2 = setup error.

## Region

Garage must use `s3_region = "us-east-1"`: the Gen2 registry's storage client
(minio-py) only works with that region against Garage. The farmer profile's
storage backend region changes from eu-west-2 to us-east-1 at the switch
(back to eu-west-2 on rollback). `test_gen2_client.sh` shows this.

## Tests

Need Docker. Images are pinned: `minio/minio:RELEASE.2025-04-22T22-12-26Z`,
`dxflrs/garage:v2.1.0`, `rclone/rclone:1.68.2`, `postgres:16`. Docker Hub no
longer serves the MinIO release: `MINIO_IMG=minio/minio:latest` uses another.

```
./test_local.sh                     # Part A: 19 checks
PYTHON=<python with boto3 and psycopg2> ./test_map_documents.sh   # Part B: 27 checks
PYTHON=<python with minio==7.2.15> \
FP_PYTHONS="<python with boto3==1.15.18> <python with boto3==1.35.36>" \
REGION=us-east-1 ./test_gen2_client.sh
```

All clean up their containers when they finish.
