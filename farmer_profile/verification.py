"""The checks verify.py runs. Three kinds:

- Records and values: every record the migration should have written is in
  the registry, and every column holds what the field map says (the expected
  rows are the transform's output for the same source rows).
- Against farmer profile directly, without the transform: names, dates,
  gender, how many lands, crops, phones and members each farmer has, and
  their land area. A bug in the transform shows here even though the values
  check agrees with it.
- The registry on its own: links resolve, one head per household, coded
  values are in their code lists, locations carry a hierarchy, the registry's
  hooks ran, and functional ids are there or queued.
"""
import collections
import decimal
import json
from datetime import date, datetime

from sqlalchemy import select, text

from . import fieldmap as F
from .transform import MIGRATED_BY, record_id

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
# Kept per column; every difference is in differences.csv
EXAMPLES_PER_COLUMN = 1
SKIP_COLUMNS = {"search_text", "record_name"}  # the registry's hooks fill them: checked for presence instead


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, group, check, expected, found, ok=None, detail="", warn_only=False):
        if ok is None:
            ok = expected == found
        result = PASS if ok else (WARN if warn_only else FAIL)
        self.rows.append({"group": group, "check": check, "expected": expected, "found": found,
                          "result": result, "detail": detail})
        return result


def norm(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, decimal.Decimal)):
        return round(float(v), 6)
    if isinstance(v, datetime):
        return v.replace(tzinfo=None, microsecond=0).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, default=str)
    if hasattr(v, "value"):  # enums
        return v.value
    return str(v).strip()


class Comparison:
    """Expected rows (the transform's) against the registry's, column by column."""

    def __init__(self):
        self.columns = {}  # (register, column) -> {"compared", "differ", "example"}
        self.missing = collections.Counter()
        self.expected = collections.Counter()
        self.differences = []

    def run(self, session, models, result, odoo_of):
        for register, rows in result.tables():
            cls = getattr(models, f"G2PRegister{register}")
            if not rows:
                continue
            ids = [r["internal_record_id"] for r in rows]
            found = {r.internal_record_id: r for r in session.scalars(select(cls).where(cls.internal_record_id.in_(ids)))}
            self.expected[register] += len(rows)
            for row in rows:
                target = found.get(row["internal_record_id"])
                if target is None:
                    self.missing[register] += 1
                    self.differences.append({"register": register, "record_id": row["internal_record_id"],
                                             "odoo_id": odoo_of.get(row["internal_record_id"]), "column": "(record)",
                                             "expected": "present", "found": "missing"})
                    continue
                for column, want in row.items():
                    if column in SKIP_COLUMNS or (column == "functional_record_id" and want is None):
                        continue
                    have = getattr(target, column)
                    stat = self.columns.setdefault((register, column), {"compared": 0, "differ": 0, "example": ""})
                    stat["compared"] += 1
                    if norm(want) != norm(have):
                        stat["differ"] += 1
                        if not stat["example"]:
                            stat["example"] = f"{row['internal_record_id']}: expected {norm(want)!r}, found {norm(have)!r}"[:300]
                        self.differences.append({"register": register, "record_id": row["internal_record_id"],
                                                 "odoo_id": odoo_of.get(row["internal_record_id"]), "column": column,
                                                 "expected": norm(want), "found": norm(have)})

    def column_rows(self):
        return [{"register": r, "column": c, **s} for (r, c), s in sorted(self.columns.items())]


class Direct:
    """Farmer profile's raw rows against the registry, without the transform."""

    def __init__(self):
        self.stats = collections.defaultdict(lambda: [0, 0, ""])  # check -> [compared, differ, example]

    def _count(self, check, ok, example):
        s = self.stats[check]
        s[0] += 1
        if not ok:
            s[1] += 1
            s[2] = s[2] or example[:300]

    def run(self, conn, data):
        farmers = data["farmers"]
        fids = {f["id"]: record_id("farmer", f["id"]) for f in farmers}
        q = lambda sql, **p: conn.execute(text(sql), p).mappings().all()
        got = {r["internal_record_id"]: r for r in q(
            "SELECT internal_record_id, first_name, middle_name, last_name, gender, birth_date "
            "FROM g2p_register_farmers WHERE internal_record_id = ANY(:ids)", ids=list(fids.values()))}
        lands = {r["farmer"]: r for r in q(
            "SELECT link_internal_record_id AS farmer, count(*) AS n, coalesce(sum(land_size), 0) AS area "
            "FROM g2p_register_lands WHERE link_internal_record_id = ANY(:ids) GROUP BY 1", ids=list(fids.values()))}
        crops = {r["farmer"]: r["n"] for r in q(
            "SELECT l.link_internal_record_id AS farmer, count(*) AS n FROM g2p_register_crops c "
            "JOIN g2p_register_lands l ON l.internal_record_id = c.link_internal_record_id "
            "WHERE l.link_internal_record_id = ANY(:ids) GROUP BY 1", ids=list(fids.values()))}
        phones = collections.defaultdict(set)
        for r in q("SELECT link_internal_record_id AS farmer, phone_number FROM g2p_register_farmer_phones "
                   "WHERE link_internal_record_id = ANY(:ids)", ids=list(fids.values())):
            phones[r["farmer"]].add(_digits(r["phone_number"])[-9:])
        src_lands, src_crops, src_phones = collections.defaultdict(list), collections.Counter(), collections.defaultdict(set)
        for l in data["lands"]:
            src_lands[l["partner_id"]].append(l)
        for c in data["crops"]:
            src_crops[c["partner_id"]] += 1
        for p in data["phones"]:
            if not p["disabled"] and len(_digits(p["phone_no"])) >= 9:
                src_phones[p["partner_id"]].add(_digits(p["phone_no"])[-9:])

        for f in farmers:
            rid = fids[f["id"]]
            t = got.get(rid)
            tag = f"Odoo {f['id']}"
            if t is None:
                self._count("farmer is in the registry", False, tag)
                continue
            self._count("farmer is in the registry", True, "")
            for label, a, b in (("first name = given_name", f["given_name"], t["first_name"]),
                                ("middle name = family_name", f["family_name"], t["middle_name"]),
                                ("last name = gf_name_eng", f["gf_name_eng"], t["last_name"]),
                                ("birth date = birthdate", f["birthdate"], t["birth_date"])):
                self._count(label, norm(a) == norm(b), f"{tag}: {norm(a)!r} / {norm(b)!r}")
            if f["gender"]:
                self._count("gender = gender", str(f["gender"]).upper() == str(t["gender"] or "").upper(),
                            f"{tag}: {f['gender']!r} / {t['gender']!r}")
            mine = lands.get(rid, {"n": 0, "area": 0})
            self._count("number of lands", len(src_lands[f["id"]]) == mine["n"],
                        f"{tag}: {len(src_lands[f['id']])} / {mine['n']}")
            src_area = sum(float(l["total_land_area"] or 0) for l in src_lands[f["id"]])
            self._count("land area (sum of total_land_area)", abs(src_area - float(mine["area"])) < 1e-6,
                        f"{tag}: {src_area} / {mine['area']}")
            want_crops = src_crops[f["id"]] if src_lands[f["id"]] else 0  # a crop needs a land
            self._count("number of crops (farmers with land)", want_crops == crops.get(rid, 0),
                        f"{tag}: {want_crops} / {crops.get(rid, 0)}")
            self._count("every phone number kept", src_phones[f["id"]] <= phones[rid],
                        f"{tag}: missing {sorted(src_phones[f['id']] - phones[rid])}")

        members = collections.Counter(record_id("household", m["household_id"]) for m in data["memberships"]
                                      if m["farmer_id"] in fids)
        found = {r["hh"]: r["n"] for r in q(
            "SELECT link_internal_record_id AS hh, count(*) AS n FROM g2p_register_household_members "
            "WHERE link_internal_record_id = ANY(:ids) GROUP BY 1", ids=list(members))}
        for hh, n in members.items():
            self._count("household members = active memberships", n == found.get(hh, 0), f"{hh}: {n} / {found.get(hh, 0)}")

    def add_to(self, checks):
        for check, (compared, differ, example) in self.stats.items():
            checks.add("Against farmer profile", check, compared, compared - differ, ok=not differ,
                       detail=f"{differ} differ; e.g. {example}" if differ else "")


def _digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


# -- the registry on its own --------------------------------------------------------------

_LINKS = [("Farmer", "Household"), ("HouseholdMember", "Household"), ("FarmerPhone", "Farmer"),
          ("Land", "Farmer"), ("Crop", "Land")]


def registry_checks(conn, models, master, checks):
    t = lambda reg: getattr(models, f"G2PRegister{reg}").__tablename__
    one = lambda sql, **p: conn.execute(text(sql), {"by": MIGRATED_BY, **p}).scalar()

    for child, parent in _LINKS:
        n = one(f"SELECT count(*) FROM {t(child)} c WHERE c.created_by = :by AND NOT EXISTS "
                f"(SELECT 1 FROM {t(parent)} p WHERE p.internal_record_id = c.link_internal_record_id)")
        checks.add("Registry", f"every {child} links to a {parent}", 0, n)

    n = one(f"""SELECT count(*) FROM {t('Household')} h WHERE h.created_by = :by AND
                (SELECT count(*) FROM {t('HouseholdMember')} m
                  WHERE m.link_internal_record_id = h.internal_record_id AND m.is_head) <> 1""")
    checks.add("Registry", "every household has exactly one head member", 0, n)

    for reg in F.WRITTEN:
        n = one(f"SELECT count(*) FROM {t(reg)} WHERE created_by = :by AND (record_name IS NULL OR search_text IS NULL)")
        checks.add("Registry", f"{reg}: records the registry gave a name and search text", 0, n, warn_only=True,
                   detail=f"{n} have none: the registry builds them from fields that are empty here (for a crop, "
                          "its commodity, e.g. one Master Data does not have)" if n else "")
    for reg in ("Farmer", "Household"):
        n = one(f"SELECT count(*) FROM {t(reg)} WHERE created_by = :by AND geo_lowest_level_value_id IS NOT NULL "
                f"AND (geo_code_hierarchy_json IS NULL OR geo_code_hierarchy_json->'hierarchy'->-1->>'level_value_id' "
                f"<> geo_lowest_level_value_id)")
        checks.add("Registry", f"{reg}: the location's hierarchy ends at its P-code", 0, n)
        n = one(f"SELECT count(*) FROM {t(reg)} WHERE created_by = :by AND geo_lowest_level_value_id IS NULL")
        total = one(f"SELECT count(*) FROM {t(reg)} WHERE created_by = :by")
        checks.add("Registry", f"{reg}: records with a location", total, total - n, ok=not n, warn_only=True,
                   detail=f"{n} without one (no P-code for any level: see the migration's issues)" if n else "")
        n = one(f"""SELECT count(*) FROM {t(reg)} r WHERE r.created_by = :by AND (r.functional_record_id IS NULL
                    OR (r.functional_record_id LIKE 'TEMP-%%' AND NOT EXISTS (SELECT 1 FROM g2p_functional_id_generation_queue q
                         WHERE q.internal_record_id = r.internal_record_id)))""")
        checks.add("Registry", f"{reg}: a functional id, or one queued", 0, n,
                   detail="run migrate.py --finalize-only to queue them" if n else "")
        n = one(f"""SELECT count(*) FROM {t(reg)} r JOIN g2p_functional_id_generation_queue q
                    ON q.internal_record_id = r.internal_record_id
                    WHERE r.created_by = :by AND q.id_allocation_status = 'FAILED'""")
        checks.add("Registry", f"{reg}: functional id allocations that failed", 0, n, warn_only=True)

    _code_checks(conn, models, master, checks)
    _location_checks(conn, models, master, checks)


def _location_checks(conn, models, master, checks):
    """Every location the migration wrote is one Master Data has."""
    for register, column in (("Farmer", "geo_lowest_level_value_id"), ("Household", "geo_lowest_level_value_id"),
                             ("Land", "land_kebele")):
        table = getattr(models, f"G2PRegister{register}").__tablename__
        bad, total = collections.Counter(), 0
        for value, n in conn.execute(text(f'SELECT "{column}", count(*) FROM {table} WHERE created_by = :by '
                                          f'AND "{column}" IS NOT NULL GROUP BY 1'), {"by": MIGRATED_BY}).all():
            total += n
            if value not in master.nodes:
                bad[value] += n
        checks.add("Master Data", f"{register}.{column} is a location in Master Data", total,
                   total - sum(bad.values()), ok=not bad,
                   detail=("not in Master Data: " + ", ".join(f"{v} x{n}" for v, n in bad.most_common(10))) if bad else "")


def _code_checks(conn, models, master, checks):
    """Every coded value the migration wrote is in the column's code list in Master Data."""
    for (register, column), attributes in sorted(master.bindings.items()):
        if register not in F.WRITTEN:
            continue
        cls = getattr(models, f"G2PRegister{register}")
        if column not in cls.__table__.columns:
            continue
        allowed = master.allowed(register, column)
        name = "/".join(sorted(attributes))
        if not allowed:
            checks.add("Master Data", f"{register}.{column} in {name}", "a code list", "none in Master Data",
                       ok=False, warn_only=True, detail="Master Data has no such code list: the column stays empty")
            continue
        bad, total = collections.Counter(), 0
        # grouped as text: json columns have no equality
        for value, n in conn.execute(text(f'SELECT "{column}"::text, count(*) FROM {cls.__tablename__} '
                                          f'WHERE created_by = :by AND "{column}" IS NOT NULL GROUP BY 1'),
                                     {"by": MIGRATED_BY}).all():
            if str(cls.__table__.columns[column].type).upper() in ("JSON", "JSONB"):
                value = json.loads(value)
            values = value if isinstance(value, list) else [value]
            total += n
            for v in values:
                if v not in allowed:  # JSON null included: the column should be SQL NULL
                    bad[v] += n
        checks.add("Master Data", f"{register}.{column} in {name}", total, total - sum(bad.values()), ok=not bad,
                   detail=("not in Master Data: " + ", ".join(f"{v!r} x{n}" for v, n in bad.most_common(10))) if bad else "")
