"""Writes transformed rows through the registry's own models.

Going through the ORM runs the same insert hooks the registry runs on an
approved record: core's search_text and record_name, and OAN's readable names
and farmer search text. A record whose id is already there is left alone, so
running the migration again only adds what is missing.
"""
import importlib

from sqlalchemy import select
from sqlalchemy.orm import Session


def _models():
    return importlib.import_module("openg2p_registry_extensions.register_domain.models")


def write(engine, result, dry_run=False) -> dict:
    models = _models()
    counts = {}
    with Session(engine) as session:
        with session.begin():
            for mnemonic, rows in result.tables():
                cls = getattr(models, f"G2PRegister{mnemonic}")
                columns = set(cls.__table__.columns.keys())
                # None in a JSON column would be stored as JSON null; leave the column out: SQL NULL
                json_columns = {c.name for c in cls.__table__.columns if str(c.type).upper() in ("JSON", "JSONB")}
                ids = [r["internal_record_id"] for r in rows]
                existing = set(session.scalars(select(cls.internal_record_id).where(cls.internal_record_id.in_(ids)))) if ids else set()
                added = 0
                for row in rows:
                    if row["internal_record_id"] in existing:
                        continue
                    unknown = set(row) - columns
                    if unknown:
                        raise ValueError(f"{cls.__tablename__} has no column {sorted(unknown)}: fix the field map")
                    values = {k: v for k, v in row.items()
                              if k != "geo_code_hierarchy_json" and not (v is None and k in json_columns)}
                    record = cls(**values)
                    # Setting the location asks Master Data for its hierarchy; we built it from the pack
                    if "geo_code_hierarchy_json" in row:
                        record.geo_code_hierarchy_json = row["geo_code_hierarchy_json"]
                    session.add(record)
                    added += 1
                session.flush()
                counts[cls.__tablename__] = {"rows": len(rows), "added": added, "already there": len(existing)}
            if dry_run:
                session.rollback()
    return counts
