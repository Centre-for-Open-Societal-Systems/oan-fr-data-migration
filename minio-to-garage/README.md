# fp-garage-move

Move the farmer profile documents (land certificate photos, bucket `documents`)
from MinIO (172.16.16.231) to Garage, and check that nothing was lost.
It only copies and compares: it never deletes or changes anything in MinIO and
never deletes anything in Garage.

## Files

| File | What it is |
|---|---|
| `move_to_garage.sh` | The moving script (rclone wrapper) |
| `rclone.conf.example` | The two storage connections, without keys |
| `test_local.sh` | Tests the moving script against MinIO and Garage in containers (2,000 test files) |
| `test_gen2_client.sh`, `test_fp_clients.py` | Test that the Gen2 registry, the farmer profile (Odoo) and the ODK import service work with Garage |

## Set up (on the Garage server)

1. Install rclone 1.59 or later (the official binary; the Ubuntu package can be too old).
2. `cp rclone.conf.example rclone.conf`, fill in the keys, `chmod 600 rclone.conf`.
   `rclone.conf` and `logs/` are git-ignored: keys never go into the repo.

## Use

```
./move_to_garage.sh size            # files and bytes in MinIO and Garage
./move_to_garage.sh copy            # copy every document (safe to stop and run again)
./move_to_garage.sh check           # compare every file: name, size, MD5
./move_to_garage.sh catchup 48      # copy only files added in the last 48 hours
```

Order during the move: `copy` (off-hours) → `check` (must show 0 missing, 0 different)
→ `catchup` once a day until the switch → on switch day: `catchup`, switch the farmer
profile to Garage, `catchup` again, final `check`.

The copy never replaces a file that is newer in Garage (rclone `--update`), so the
`catchup` after the switch cannot overwrite a document the farmer profile has
already written to Garage. Before the switch this changes nothing: Garage only has
what was copied from MinIO. After the switch, the final `check` lists such a file
as different; that is expected, and the Garage version is the one to keep.

Options (environment): `BWLIMIT=50M` to slow the copy if MinIO gets slow for users,
`TRANSFERS` / `CHECKERS` (default 32 / 64), `BUCKET` (default `documents`).

Each run writes to `logs/`, named with the date and time: the copy log, and for
`check` the lists of missing, different and unreadable files.
Exit code: 0 = clean, 1 = something missing or different, 2 = setup error.

## Region

Garage must use `s3_region = "us-east-1"`: the Gen2 registry's storage client
(minio-py) only works with that region against Garage. The farmer profile's
storage backend region changes from eu-west-2 to us-east-1 at the switch
(back to eu-west-2 on rollback). `test_gen2_client.sh` shows this.

## Tests

Need Docker. Images are pinned: `minio/minio:RELEASE.2025-04-22T22-12-26Z`,
`dxflrs/garage:v2.1.0`, `rclone/rclone:1.68.2`.

```
./test_local.sh                     # moving script: 14 checks
PYTHON=<python with minio==7.2.15> \
FP_PYTHONS="<python with boto3==1.15.18> <python with boto3==1.35.36>" \
REGION=us-east-1 ./test_gen2_client.sh
```

Both clean up their containers when they finish.
