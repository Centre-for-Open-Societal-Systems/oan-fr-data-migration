"""Measure the health of a farmer profile -> Farmer registry migration.

Reads both databases and writes the results (counts only, no personal data) to
the registry's schema migration_report and to health-report.xlsx, in a folder
of its own under --report. Run it after migrate.py and verify.py.

  python health.py

Exit codes: 0 green or amber; 3 red, something blocks sign-off; 1 it could not be measured.
"""
import argparse
import importlib
import os
import sys
import traceback

from sqlalchemy import create_engine

from migrate import init_registry


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", default=os.environ.get("REPORT_DIR", "/out"))
    args = parser.parse_args(argv)
    init_registry()
    from farmer_profile import health, health_report, runlog
    run_dir, log = runlog.start(args.report, "health", argv)
    engine = create_engine(os.environ["TARGET_DSN"], pool_pre_ping=True)
    models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
    try:
        data = health.take(engine, os.environ["SOURCE_DSN"], models, log, "health")
        health_report.workbook(run_dir / "health-report.xlsx", data)
    except health.NotMeasurable as exc:
        log.error("%s", exc)
        return 1
    except Exception:
        log.error("the health could not be measured:\n%s", traceback.format_exc())
        return 1
    for line in health_report.lines(data):
        log.info("%s", line)
    log.info("wrote %s", run_dir / "health-report.xlsx")
    return 3 if data["overall"] == health.RED else 0


if __name__ == "__main__":
    sys.exit(main())
