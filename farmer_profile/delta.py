"""Bringing farmer profile's changes into records that are already migrated.

A household that changed in farmer profile is prepared again, as a first load
prepares it (transform, then the registry's hooks), and its rows are written
over the registry's by their record id. Only what the migration fills is
written: the functional id, who created the record and when, and what the
registry's own workers fill in stay as they are (fieldmap says which column is
which). A row is updated only when one of its values differs; each value that
differs is recorded in migration.change.

Records the household no longer has are not touched here: tracking marks them
orphaned, and remove() sets them INACTIVE at the end of a complete --all run,
unless another household has them by then.

Neither is done to a household the registry has edited since (tracking.edited):
that is a conflict, for a person to decide.
"""
import functools
import importlib
import io

from sqlalchemy import types as sa_types

from . import fieldmap as F
from . import load
from .tracking import REGISTERS as _REGISTERS

# Never written over: the registry's ids, and who made the record and when
KEEP = {"internal_record_id", "functional_record_id", "created_at", "created_by", "last_approved_by"}
# Written over, not listed as changes: they follow from the others
QUIET = {"search_text", "record_name", "last_approved_at", "geo_code_hierarchy_json"}
REMOVED_REASON = "No longer in farmer profile (migration)"


def _models():
    return importlib.import_module("openg2p_registry_extensions.register_domain.models")


@functools.lru_cache(maxsize=None)
def _register_of(table) -> str:
    for mnemonic in F.WRITTEN:
        if getattr(_models(), f"G2PRegister{mnemonic}").__tablename__ == table:
            return mnemonic
    raise KeyError(table)


@functools.lru_cache(maxsize=None)
def plan(table) -> dict:
    """column -> how an update writes it: "set", "fill" (only when the migration has a value:
    a column farmer profile has no field for, which the registry may fill) or absent (never)."""
    register = _register_of(table)
    cls = getattr(_models(), f"G2PRegister{register}")
    out = {}
    for column in cls.__table__.columns:
        name = column.name
        if name in KEEP:
            continue
        if name == "record_status_reason":
            out[name] = "set"
            continue
        status, _ = F.target_status(register, name, F.sources_of(register, name))
        if status in (F.AFTER, F.T_NOT_YET):
            continue
        out[name] = "fill" if status == F.ABSENT else "set"
    return out


@functools.lru_cache(maxsize=None)
def _json(table) -> set:
    cls = getattr(_models(), f"G2PRegister{_register_of(table)}")
    return {c.name for c in cls.__table__.columns if isinstance(c.type, sa_types.JSON)}


def _q(name):
    return f'"{name}"'


def _text(alias, column, table):
    """A value as text, to compare: json compared as jsonb, which ignores spacing and key order."""
    return f"{alias}.{_q(column)}::jsonb::text" if column in _json(table) else f"{alias}.{_q(column)}::text"


def _new(column, how):
    return f"coalesce(s.{_q(column)}, t.{_q(column)})" if how == "fill" else f"s.{_q(column)}"


def write(cur, prepared: load.Prepared) -> list[tuple]:
    """In the caller's transaction: add the rows the registry does not have, and write the
    others over the registry's where they differ. Returns (action, gen2_id, field, old, new):
    ADDED, UPDATED, or ACTIVE_AGAIN / SET_INACTIVE for record_status."""
    out = []
    for table, (names, rows) in prepared.items():
        if not rows:
            continue
        cur.execute(load.staging_sql(table))
        cur.execute(f'TRUNCATE "mig_{table}"')
        cur.copy_expert(load.copy_sql(table, names), io.StringIO(load.copy_data(rows)))
        cur.execute(load.insert_sql(table, names) + " RETURNING internal_record_id")
        added = [r[0] for r in cur.fetchall()]
        out += [("ADDED", i, "", None, None) for i in added]
        how = {c: h for c, h in plan(table).items() if c in names}
        if not how:
            continue
        pairs = ", ".join(f"('{c}', {_text('t', c, table)}, ({_new(c, h)})"
                          + ("::jsonb::text)" if c in _json(table) else "::text)") for c, h in how.items())
        cur.execute(f"""
            SELECT s.internal_record_id, k.f, k.o, k.n
              FROM "mig_{table}" s JOIN {_q(table)} t ON t.internal_record_id = s.internal_record_id
             CROSS JOIN LATERAL (VALUES {pairs}) AS k(f, o, n)
             WHERE k.o IS DISTINCT FROM k.n AND NOT s.internal_record_id = ANY(%s)""", (added,))
        diffs = cur.fetchall()
        if not diffs:
            continue
        cur.execute(f"""
            UPDATE {_q(table)} AS t SET {", ".join(f"{_q(c)} = {_new(c, h)}" for c, h in how.items())}
              FROM "mig_{table}" s
             WHERE t.internal_record_id = s.internal_record_id AND t.internal_record_id = ANY(%s)""",
                    (sorted({d[0] for d in diffs}),))
        for gen2_id, field, old, new in diffs:
            if field == "record_status":
                out.append(("ACTIVE_AGAIN" if new == "ACTIVE" else "SET_INACTIVE", gen2_id, field, old, new))
            elif field not in QUIET:
                out.append(("UPDATED", gen2_id, field, old, new))
    return out


def lock(cur, models, gen2_ids):
    """Hold the registry's rows of these records until the transaction ends: an edit made
    meanwhile waits, and is seen by the next run."""
    ids = list(gen2_ids)
    if not ids:
        return
    for table in sorted({getattr(models, f"G2PRegister{r}").__tablename__ for r in _REGISTERS.values()}):
        cur.execute(f"SELECT 1 FROM {_q(table)} WHERE internal_record_id = ANY(%s) FOR UPDATE", (ids,))


def set_inactive(cur, models, records) -> list[tuple]:
    """records: (kind, odoo_id, gen2_id). Set the ones still active INACTIVE. Returns
    (kind, odoo_id, gen2_id, old status) of those changed."""
    out = []
    by_table = {}
    for kind, odoo_id, gen2_id in records:
        by_table.setdefault(getattr(models, f"G2PRegister{_REGISTERS[kind]}").__tablename__, {})[gen2_id] = (kind, odoo_id)
    for table, ids in sorted(by_table.items()):
        cur.execute(f"""
            WITH old AS (SELECT internal_record_id, record_status FROM {_q(table)}
                          WHERE internal_record_id = ANY(%s) AND record_status IS DISTINCT FROM 'INACTIVE' FOR UPDATE)
            UPDATE {_q(table)} t SET record_status = 'INACTIVE', record_status_reason = %s
              FROM old WHERE t.internal_record_id = old.internal_record_id
            RETURNING t.internal_record_id, old.record_status""", (list(ids), REMOVED_REASON))
        out += [(*ids[gen2_id], gen2_id, old) for gen2_id, old in cur.fetchall()]
    return out
