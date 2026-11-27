#!/usr/bin/env bash
# Move the farmer profile documents from MinIO to Garage.
#
# Runs on the Garage server. Uses rclone (1.59 or later) with two remotes in
# an rclone config file kept next to this script (rclone.conf, chmod 600):
#   [old]     the MinIO the farmer profile uses today (http://172.16.16.231:9000)
#   [garage]  the new Garage (http://<GARAGE_IP>:3900, region us-east-1)
# The keys live only in that file; this script never prints them.
#
# It only copies and compares. It never deletes or changes anything in MinIO,
# and never deletes anything in Garage (no sync, no move, no purge). It never
# replaces a file that is newer in Garage (--update), so a catchup after the
# switch cannot overwrite a document the farmer profile wrote to Garage.
#
#   ./move_to_garage.sh size            count files and bytes on both sides
#   ./move_to_garage.sh copy            copy every document (safe to stop and run again)
#   ./move_to_garage.sh check           compare every file: name, size and MD5
#   ./move_to_garage.sh catchup [HOURS] copy only files added in the last HOURS (default 48)
#
# Every run writes a log under ./logs/ named with the date and time.
# Exit code: 0 = done and clean, 1 = something is missing or different, 2 = usage/config error.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF="${RCLONE_CONF:-$HERE/rclone.conf}"
BUCKET="${BUCKET:-documents}"
SRC="${SRC_REMOTE:-old}:$BUCKET"
DST="${DST_REMOTE:-garage}:$BUCKET"
TRANSFERS="${TRANSFERS:-32}"
CHECKERS="${CHECKERS:-64}"
BWLIMIT="${BWLIMIT:-}"          # e.g. 50M if MinIO gets slow for users during the copy
LOGS="${LOG_DIR:-$HERE/logs}"
RCLONE="${RCLONE:-rclone}"      # the test runs rclone in a container through this
STAMP="$(date -u +%Y%m%d-%H%M%S)"

die() { echo "move_to_garage: $*" >&2; exit 2; }

[ -f "$CONF" ] || die "no rclone config at $CONF (see the header of this script)"
mkdir -p "$LOGS"
chmod 700 "$LOGS" 2>/dev/null || true

rc() { $RCLONE --config "$CONF" "$@"; }
common=(--fast-list --s3-no-check-bucket --stats 1m --stats-one-line --log-level INFO)

size() {
  echo "MinIO  ($SRC):";  rc size "$SRC" --fast-list
  echo "Garage ($DST):";  rc size "$DST" --fast-list
}

copy() {   # $1 = optional --max-age value
  local log="$LOGS/$STAMP-${2:-copy}.log"
  local extra=()
  [ -n "${1:-}" ] && extra+=(--max-age "$1")
  [ -n "$BWLIMIT" ] && extra+=(--bwlimit "$BWLIMIT")
  echo "Copying $SRC -> $DST ${1:+(files newer than $1)}; log: $log"
  if rc copy "$SRC" "$DST" "${common[@]}" -M --update --transfers "$TRANSFERS" --checkers "$CHECKERS" \
        "${extra[@]}" --log-file "$log"; then
    echo "Copy finished without errors."
  else
    echo "Copy ended with errors: see $log. Run the same command again; it continues where it stopped." >&2
    exit 1
  fi
}

check() {
  local base="$LOGS/$STAMP-check"
  echo "Comparing every file in $SRC with $DST (name, size, MD5); reports: $base-*.txt"
  set +e
  rc check "$SRC" "$DST" --one-way --fast-list --checkers "$CHECKERS" \
     --missing-on-dst "$base-missing.txt" --differ "$base-differ.txt" --error "$base-error.txt" \
     --log-file "$base.log" --log-level NOTICE
  local status=$?
  set -e
  local missing differ errors
  missing=$(wc -l < "$base-missing.txt" 2>/dev/null || echo 0)
  differ=$(wc -l < "$base-differ.txt" 2>/dev/null || echo 0)
  errors=$(wc -l < "$base-error.txt" 2>/dev/null || echo 0)
  echo "Missing in Garage: $missing   Different: $differ   Could not read: $errors"
  if [ "$status" -eq 0 ] && [ "$missing" -eq 0 ] && [ "$differ" -eq 0 ] && [ "$errors" -eq 0 ]; then
    echo "Check passed: every file in MinIO is in Garage, identical."
  else
    echo "Check FAILED: run 'copy' (or 'catchup') again, then 'check'. Lists are in $base-*.txt" >&2
    exit 1
  fi
}

case "${1:-}" in
  size)    size ;;
  copy)    copy "" copy ;;
  catchup) hours="${2:-48}"; [[ "$hours" =~ ^[0-9]+$ ]] || die "catchup takes a whole number of hours"
           copy "${hours}h" "catchup-${hours}h" ;;
  check)   check ;;
  *)       sed -n '2,24p' "$0"; exit 2 ;;
esac
