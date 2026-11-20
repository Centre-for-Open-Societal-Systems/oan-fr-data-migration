"""Every farmer profile field and every Gen2 column, with how many records hold a value.

Farmer profile's fields are read from Odoo's own field table (ir_model_fields),
so the list is whatever the source database has, not what this code expects.
The counts are over the farmers the run covered (or every farmer in scope).
"""
import collections
import importlib

from sqlalchemy import text

from . import fieldmap as F
from .source import IN_SCOPE

FIELDS = """
SELECT f.model, f.name, f.ttype, f.store, f.relation, f.relation_field, f.relation_table, f.column1,
       (SELECT array_agg(DISTINCT d.module ORDER BY d.module) FROM ir_model_data d
         WHERE d.model = 'ir.model.fields' AND d.res_id = f.id) AS modules,
       coalesce(f.field_description->>'en_US', f.field_description::text) AS label
  FROM ir_model_fields f
 WHERE f.model = ANY(%s)
 ORDER BY f.model, f.name
"""

# The rows of each model that count, given the in-scope farmers as {farmers}
_ROWS = {
    "res.partner": "SELECT * FROM res_partner p WHERE {farmers}",
    "g2p.group.membership": 'SELECT m.* FROM g2p_group_membership m JOIN res_partner p ON p.id = m.individual WHERE {farmers}',
    "g2p.reg.id": "SELECT r.* FROM g2p_reg_id r JOIN res_partner p ON p.id = r.partner_id WHERE {farmers}",
    "g2p.phone.number": "SELECT n.* FROM g2p_phone_number n JOIN res_partner p ON p.id = n.partner_id WHERE {farmers}",
    "g2p.land.information": "SELECT l.* FROM g2p_land_information l JOIN res_partner p ON p.id = l.partner_id WHERE {farmers}",
    "g2p.crop.information": "SELECT c.* FROM g2p_crop_information c JOIN res_partner p ON p.id = c.partner_id WHERE {farmers}",
    "g2p.livestock.information": "SELECT v.* FROM g2p_livestock_information v JOIN res_partner p ON p.id = v.partner_id WHERE {farmers}",
    "g2p.enumerator": "SELECT e.* FROM g2p_enumerator e WHERE e.id IN (SELECT p.enumerator_id FROM res_partner p WHERE {farmers})",
}


def _table(model):
    return model.replace(".", "_")


def _scope(farmer_ids):
    """SQL for 'p is an in-scope farmer' and its parameters."""
    if farmer_ids is None:
        return IN_SCOPE, ()
    return "p.id = ANY(%s)", (list(farmer_ids),)


def source_fields(conn, farmer_ids=None) -> list[dict]:
    """One row per Odoo field of the source models, with its status from the
    field map and the number of in-scope records holding a value."""
    where, params = _scope(farmer_ids)
    out = []
    with conn.cursor() as cur:
        cur.execute(FIELDS, (list(F.SOURCE_MODELS),))
        names = [d[0] for d in cur.description]
        fields = [dict(zip(names, r)) for r in cur.fetchall()]
        cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ANY(%s)",
                    ([_table(m) for m in F.SOURCE_MODELS],))
        columns = {(t, c): d for t, c, d in cur.fetchall()}

        totals, counts = {}, {}
        for model, rows_sql in _ROWS.items():
            base = rows_sql.format(farmers=where)
            stored = [f for f in fields if f["model"] == model and (_table(model), f["name"]) in columns]
            parts = ["count(*)"] + [_count_expr(f["name"], columns[(_table(model), f["name"])]) for f in stored]
            cur.execute(f"SELECT {', '.join(parts)} FROM ({base}) x", params)
            row = cur.fetchone()
            totals[model] = row[0]
            counts.update({(model, f["name"]): n for f, n in zip(stored, row[1:])})
            # many2many and one2many: records with at least one linked row
            for f in fields:
                if f["model"] != model or (model, f["name"]) in counts:
                    continue
                n = _linked_count(cur, f, base, params)
                if n is not None:
                    counts[(model, f["name"])] = n

    for f in fields:
        stored = f["ttype"] in ("one2many", "many2many") or (_table(f["model"]), f["name"]) in columns
        if not stored and (f["model"], f["name"]) not in F.SOURCE:
            continue  # computed on the fly by Odoo: not data
        kind = f["ttype"] if stored else f"{f['ttype']} (not stored)"
        entry = F.source_status(f["model"], f["name"], f["modules"] or [])
        out.append({
            "model": f["model"], "field": f["name"], "label": f["label"], "type": kind,
            "module": ", ".join(f["modules"] or []), "status": entry["status"],
            "gen2": ", ".join(entry["targets"]), "how": entry["how"],
            "rows_in_scope": totals.get(f["model"]), "rows_with_value": counts.get((f["model"], f["name"])),
        })
    # Fields the map names that this database does not have
    present = {(f["model"], f["name"]) for f in fields}
    for (model, name), entry in F.SOURCE.items():
        if (model, name) not in present:
            out.append({"model": model, "field": name, "label": "", "type": "", "module": "",
                        "status": entry["status"], "gen2": ", ".join(entry["targets"]),
                        "how": (entry["how"] + "; " if entry["how"] else "") + "not in this database",
                        "rows_in_scope": totals.get(model), "rows_with_value": None})
    return out


def _count_expr(name, data_type):
    col = f'x."{name}"'
    if data_type == "boolean":
        return f"count(*) FILTER (WHERE {col})"
    if data_type in ("character varying", "text"):
        return f"count(nullif(btrim({col}), ''))"
    if data_type in ("json", "jsonb"):
        return f"count(*) FILTER (WHERE {col} IS NOT NULL AND {col}::text NOT IN ('null', '{{}}', '[]', '\"\"'))"
    return f"count({col})"


def _linked_count(cur, f, base, params):
    try:
        if f["ttype"] == "many2many" and f["relation_table"] and f["column1"]:
            cur.execute(f'SELECT count(DISTINCT r."{f["column1"]}") FROM "{f["relation_table"]}" r '
                        f"WHERE r.\"{f['column1']}\" IN (SELECT id FROM ({base}) x)", params)
            return cur.fetchone()[0]
        if f["ttype"] == "one2many" and f["relation"] and f["relation_field"]:
            cur.execute(f'SELECT count(DISTINCT c."{f["relation_field"]}") FROM "{_table(f["relation"])}" c '
                        f"WHERE c.\"{f['relation_field']}\" IN (SELECT id FROM ({base}) x)", params)
            return cur.fetchone()[0]
    except Exception:  # a relation Odoo names but this database lays out differently
        cur.connection.rollback()
    return None


def target_columns(engine, written=None) -> list[dict]:
    """One row per column of the Gen2 registers in scope, with its status and
    how many migrated records hold a value: counted in the registry, or, for
    a dry run or a SQL file (nothing written), in the finished rows of the run
    (written: register -> {"rows": n, "columns": Counter})."""
    models = importlib.import_module("openg2p_registry_extensions.register_domain.models")
    out = []
    with engine.connect() as conn:
        for register in F.REGISTERS:
            cls = getattr(models, f"G2PRegister{register}")
            table = cls.__tablename__
            cols = list(cls.__table__.columns.keys())
            if written is None:
                parts = ["count(*)"] + [f'count("{c}")' for c in cols]
                row = conn.execute(text(f"SELECT {', '.join(parts)} FROM {table} WHERE created_by = :by"),
                                   {"by": "farmer-profile-migration"}).one()
                total, filled = row[0], dict(zip(cols, row[1:]))
            else:
                mine = written.get(register, {"rows": 0, "columns": {}})
                total, filled = mine["rows"], {c: mine["columns"].get(c, 0) for c in cols}
            for column in cols:
                sources = F.sources_of(register, column)
                status, how = F.target_status(register, column, sources)
                n = filled[column]
                out.append({"register": register, "table": table, "column": column, "status": status,
                             "farmer_profile": ", ".join(f"{m}.{n_}" for m, n_ in sources), "how": how,
                             "migrated_rows": total, "rows_with_value": n})
    return out


def count_written(written: dict, prepared) -> None:
    """Add a batch's finished rows (load.Prepared) to written (see target_columns)."""
    import importlib as _il
    models = _il.import_module("openg2p_registry_extensions.register_domain.models")
    register_of = {getattr(models, f"G2PRegister{r}").__tablename__: r for r in F.REGISTERS}
    for table, (names, rows) in prepared.items():
        mine = written.setdefault(register_of[table], {"rows": 0, "columns": collections.Counter()})
        mine["rows"] += len(rows)
        for row in rows:
            for name, value in zip(names, row):
                if value is not None and value != "" and value != []:
                    mine["columns"][name] += 1
