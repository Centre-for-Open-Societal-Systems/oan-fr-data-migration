"""Each run writes into a folder of its own, <report dir>/<UTC time>-<command>/:
the log (also printed), and the command's reports. Nothing is overwritten, so
the folders are the record of every run.
"""
import logging
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

LOGGER = "farmer_profile"


def start(report_dir: str, command: str, argv: list) -> tuple[Path, logging.Logger]:
    started = datetime.now(timezone.utc)
    for n in range(1, 100):  # a second run in the same second gets a folder of its own
        run_dir = Path(report_dir) / f"{started:%Y%m%d-%H%M%S}-{command}{'' if n == 1 else f'-{n}'}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue

    # The registry libraries log JSON at INFO; keep their warnings and errors only
    logging.getLogger().setLevel(logging.WARNING)
    log = logging.getLogger(LOGGER)
    log.setLevel(logging.INFO)
    log.propagate = False
    log.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%dT%H:%M:%SZ")
    fmt.converter = lambda *a: datetime.now(timezone.utc).timetuple()
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(run_dir / f"{command}.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)

    log.info("%s started on %s, run folder %s", command, socket.gethostname(), run_dir)
    log.info("arguments: %s", " ".join(argv) or "(none)")
    log.info("source %s; target %s", _safe_dsn(os.environ.get("SOURCE_DSN", "")), _safe_dsn(os.environ.get("TARGET_DSN", "")))
    return run_dir, log


def _safe_dsn(dsn: str) -> str:
    """A connection string without its password, for the log."""
    import re
    dsn = re.sub(r"(password=)\S+", r"\1***", dsn)
    return re.sub(r"(://[^:/@]+:)[^@]+@", r"\1***@", dsn)
