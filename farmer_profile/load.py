"""Loads transformed rows into the registry: finished in Python, loaded with SQL.

prepare() turns each row into the registry's own model object and runs the
registry's insert hooks on it in memory: core's search_text and record_name,
the Farmer extension's readable names and derived columns. They are the
same hooks the registry runs when it saves a record, and they only read the
record. The finished row is read back off the object. Nothing touches the
database.

The rows then go in with SQL: COPY into a temporary table, then one
INSERT ... SELECT ... ON CONFLICT (internal_record_id) DO NOTHING per table.
That is fast, and a record already there is left alone, so a rerun only adds
what is missing. write() runs it on the target in one transaction per batch;
SqlFile writes the same statements to a file, to be reviewed and run with psql.
"""
import contextlib
import enum
import functools
import importlib
import io
import json
from datetime import date, datetime

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import configure_mappers
from sqlalchemy.orm.attributes import set_committed_value

# Set on the object without going through the model's validators: setting the
# location makes the registry ask Master Data for a hierarchy we already built.
_SET_RAW = ("geo_lowest_level_value_id", "geo_code_hierarchy_json")


def _models():
    return importlib.import_module("openg2p_registry_extensions.register_domain.models")


class Prepared:
    """One batch's finished rows: table -> (column names, rows as tuples), parents first."""

    def __init__(self):
        self.tables = {}

    def items(self):
        return self.tables.items()

    def ids(self, table):
        columns, rows = self.tables[table]
        i = columns.index("internal_record_id")
        return [r[i] for r in rows]


class SchemaMismatch(Exception):
    """The migration and the registry disagree on a table's columns: no record's fault."""


@functools.lru_cache(maxsize=None)
def _plan(mnemonic):
    """How to finish a register's rows: worked out once per process."""
    configure_mappers()  # core registers its hooks when the mappers are configured
    cls = getattr(_models(), f"G2PRegister{mnemonic}")
    mapper = sa_inspect(cls)
    table = cls.__table__
    key_of = {prop.columns[0].name: prop.key for prop in mapper.column_attrs if prop.columns[0].table is table}
    names = [c.name for c in table.columns]
    defaults = [(key_of[c.name], c.default) for c in table.columns if c.default is not None
                and not c.default.is_sequence and not c.default.is_clause_element]
    return cls, mapper, table.name, key_of, names, defaults


def prepare(result) -> Prepared:
    out = Prepared()
    for mnemonic, rows in result.tables():
        cls, mapper, table, key_of, names, defaults = _plan(mnemonic)
        finished = []
        for row in rows:
            unknown = set(row) - set(names)
            if unknown:
                raise SchemaMismatch(f"{table} has no column {sorted(unknown)}: fix the field map")
            record = cls(**{k: v for k, v in row.items() if k not in _SET_RAW})
            for k in _SET_RAW:
                if k in row:
                    set_committed_value(record, key_of[k], row[k])
            for key, default in defaults:  # what the ORM would fill in at insert
                if getattr(record, key) is None:
                    set_committed_value(record, key, default.arg(None) if default.is_callable else default.arg)
            state = sa_inspect(record)
            for hook in mapper.dispatch.before_insert:
                hook(mapper, None, state)
            finished.append(tuple(getattr(record, key_of[n]) for n in names))
        out.tables[table] = (names, finished)
    return out


def merge(several) -> Prepared:
    """Several units' rows as one batch."""
    out = Prepared()
    for prepared in several:
        for table, (names, rows) in prepared.items():
            out.tables.setdefault(table, (names, []))[1].extend(rows)
    return out


def existing_ids(engine, prepared: Prepared) -> set:
    """The ids of the batch's records the registry has already (read only)."""
    found = set()
    with engine.connect() as conn:
        for table, _ in prepared.items():
            ids = prepared.ids(table)
            if ids:
                found.update(conn.exec_driver_sql(
                    f'SELECT internal_record_id FROM "{table}" WHERE internal_record_id = ANY(%s)', (ids,)).scalars())
    return found


# -- SQL ----------------------------------------------------------------------------------

def _value(v) -> str:
    """One value in COPY's text format."""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, enum.Enum):
        v = v.value
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False, default=str)
    elif isinstance(v, (datetime, date)):
        v = v.isoformat()
    else:
        v = str(v)
    return v.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def copy_data(rows) -> str:
    return "".join("\t".join(_value(v) for v in row) + "\n" for row in rows)


def _quoted(names):
    return ", ".join(f'"{n}"' for n in names)


def staging_sql(table):
    return (f'CREATE TEMP TABLE IF NOT EXISTS "mig_{table}" (LIKE "{table}" INCLUDING DEFAULTS) ON COMMIT DROP')


def copy_sql(table, names):
    return f'COPY "mig_{table}" ({_quoted(names)}) FROM STDIN'


def insert_sql(table, names):
    return (f'INSERT INTO "{table}" ({_quoted(names)})\n  SELECT {_quoted(names)} FROM "mig_{table}"\n'
            f'  ON CONFLICT (internal_record_id) DO NOTHING')


def write(engine, prepared: Prepared, dry_run=False, before=None, after=None) -> dict:
    """COPY the batch in and insert what is not there yet, in one transaction.
    before(cur) and after(cur, counts) run in it too."""
    counts = {}
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        if before:
            before(cur)
        for table, (names, rows) in prepared.items():
            cur.execute(staging_sql(table))
            cur.execute(f'TRUNCATE "mig_{table}"')
            cur.copy_expert(copy_sql(table, names), io.StringIO(copy_data(rows)))
            cur.execute(insert_sql(table, names))
            counts[table] = {"rows": len(rows), "added": cur.rowcount, "already there": len(rows) - cur.rowcount}
        if after:
            after(cur, counts)
        raw.rollback() if dry_run else raw.commit()
    except Exception:
        with contextlib.suppress(Exception):  # the connection may be gone: the error that matters is the first
            raw.rollback()
        raise
    finally:
        with contextlib.suppress(Exception):
            raw.close()
    return counts


class SqlFile:
    """The migration as one SQL file: every batch's rows as COPY data into
    temporary tables, then the inserts, the migration's progress and issues, and
    the after-load queueing, in one transaction.
    Run it with:  psql -v ON_ERROR_STOP=1 -f <file> <registry database>"""

    def __init__(self, path, header: list[str], opening: list[str] = ()):
        """opening: statements that run first (tracking.sql_guard)."""
        from . import tracking
        self.path = path
        self.handle = open(path, "w", encoding="utf-8")
        self.names = {}  # table -> columns, in the order first seen (parents first)
        self.rows = {}
        w = self.handle.write
        for line in header:
            w(f"-- {line}\n" if line else "--\n")
        w("\n\\set ON_ERROR_STOP on\nBEGIN;\n\n")
        for sql in opening:
            w(sql + ";\n\n")
        for sql in tracking.staging_sql():
            w(sql + ";\n")

    def _copy(self, statement, rows):
        self.handle.write(statement + ";\n" + copy_data(rows) + "\\.\n")

    def add(self, prepared: Prepared, track=None):
        """track: the batch's tracking rows (tracking.Batch)."""
        for table, (names, rows) in prepared.items():
            if table not in self.names:
                self.names[table] = names
                self.rows[table] = 0
                self.handle.write(staging_sql(table) + ";\n")
            self.rows[table] += len(rows)
            self._copy(copy_sql(table, names), rows)
        for name, rows in (track.rows if track else {}).items():
            if rows:
                self._copy(f"COPY {name} FROM STDIN", rows)

    def abandon(self, reason: str):
        self.handle.write(f"\n-- {reason}\nROLLBACK;\n")
        self.handle.close()

    def finish(self, progress: list[str], after_load: list):
        """progress: what records the progress and issues (tracking.apply_sql).
        after_load: (label, sql) statements to run after the inserts (finalize.statements)."""
        w = self.handle.write
        w("\n-- The registry's tables: only records not there yet are added\n")
        for table, names in self.names.items():
            w(f"\\echo {table}: {self.rows[table]} rows in this file\n")
            w(insert_sql(table, names) + ";\n")
        w("\n-- The migration's progress and issues\n")
        for sql in progress:
            w(sql + ";\n")
        if after_load:
            w("\n-- What the registry generates after the load (its workers do the rest)\n")
            for label, sql in after_load:
                w(f"\\echo {label}\n{sql};\n")
        w("\nCOMMIT;\n")
        self.handle.close()
