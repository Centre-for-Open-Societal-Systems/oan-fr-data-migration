#!/usr/bin/env bash
# Run the migration locally, one word per step.
#
#   ./run.sh setup        start the local Master Data and an empty registry database (if not there)
#   ./run.sh dry-run      migrate everything, then roll it back: nothing is kept
#   ./run.sh migrate      migrate everything into the registry
#   ./run.sh sql          write the load as migration.sql instead (the registry is only read)
#   ./run.sh apply [FILE] run migration.sql (default: the latest one) on the registry database
#   ./run.sh verify       check the registry against farmer profile and Master Data
#   ./run.sh fresh        reset + migrate + verify, in one go
#   ./run.sh summary      show the latest summaries
#   ./run.sh report       open the latest Excel report
#   ./run.sh reset        empty the local registry database
#   ./run.sh test         run the tests
#
# Every farmer is migrated unless you pick some, e.g.
#   ./run.sh dry-run --limit 10
#   ./run.sh migrate --ids 12 40
# Other options go through as they are (see python migrate.py --help): --batch-size, --workers, ...
#
# Settings come from .env (see .env.example) or the shell. Without MDS_API_URL,
# the local Master Data stand-in is used when it runs (./run.sh setup starts it).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/dev/env.sh"

running() { docker ps --format '{{.Names}}' | grep -qx "$1"; }
exists() { docker ps -a --format '{{.Names}}' | grep -qx "$1"; }
latest() { ls -d "$HERE"/out/*-"$1" 2>/dev/null | sort | tail -1 || true; }

use_local_master_data() {
  if [ -z "${MDS_API_URL:-}" ] && running fr-migration-mds; then
    export MDS_API_URL=http://fr-migration-mds:8000
  fi
}

# --all unless farmers are picked
selection() {
  for a in "$@"; do
    case "$a" in --all|--limit|--limit=*|--ids|--finalize-only) return 0;; esac
  done
  return 1
}

migrate() {
  use_local_master_data
  if selection "$@"; then "$HERE/dev/py.sh" migrate "$@"; else "$HERE/dev/py.sh" migrate --all "$@"; fi
}

step=${1:-help}
shift || true
case "$step" in
  setup)
    running fr-migration-mds || "$HERE/dev/fake-mds.sh"
    if exists fr-migration-target; then
      running fr-migration-target || docker start fr-migration-target >/dev/null
      echo "registry database: fr-migration-target (./run.sh reset to empty it)"
    else
      "$HERE/dev/target-db.sh" 2>&1 | grep -v NOTICE
    fi
    ;;
  dry-run) migrate --dry-run "$@" ;;
  migrate) migrate "$@" ;;
  sql) migrate --sql-out "$@" ;;
  apply)
    file=${1:-$(latest migrate)/migration.sql}
    [ -f "$file" ] || { echo "no migration.sql: run ./run.sh sql first" >&2; exit 1; }
    echo "applying $file"
    if [ -n "${TARGET_DSN:-}" ]; then
      psql -X -v ON_ERROR_STOP=1 -f "$file" "${TARGET_DSN/+psycopg2/}"
    else
      docker exec -i fr-migration-target psql -X -U postgres -d registry -v ON_ERROR_STOP=1 -f - < "$file"
    fi
    ;;
  verify)
    use_local_master_data
    "$HERE/dev/py.sh" verify "$@"
    ;;
  fresh)
    "$HERE/dev/target-db.sh" reset 2>&1 | grep -v NOTICE
    migrate "$@"
    use_local_master_data
    "$HERE/dev/py.sh" verify
    ;;
  summary)
    for kind in migrate verify; do
      d=$(latest "$kind")
      if [ -n "$d" ] && [ -f "$d/summary.txt" ]; then echo "### $(basename "$d")"; cat "$d/summary.txt"; echo; fi
    done
    ;;
  report)
    f=$(latest migrate)/migration-report.xlsx
    [ -f "$f" ] || { echo "no report yet: run ./run.sh dry-run or migrate" >&2; exit 1; }
    echo "$f"
    if command -v xdg-open >/dev/null; then xdg-open "$f" >/dev/null 2>&1 & fi
    ;;
  reset) "$HERE/dev/target-db.sh" reset 2>&1 | grep -v NOTICE ;;
  test) "$HERE/dev/test.sh" "$@" ;;
  help|-h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown step: $step (./run.sh help)" >&2; exit 2 ;;
esac
