"""Reads farmer profile records from the Odoo database (read-only).

select_farmers picks the farmers to migrate; units() groups them into the
smallest pieces that can be migrated on their own (a household with all its
members, or a farmer in none); read() returns everything about some farmers as
plain dicts keyed by Odoo id; read_units() does so per unit.
"""
import collections
import hashlib
import json

import psycopg2

# Raised when the fingerprint's contents change, so that older ones are not compared
FINGERPRINT_VERSION = 1

# key: "household-<lowest group id>" or "solo-<partner id>"
Unit = collections.namedtuple("Unit", "key farmers households")

FARMERS = """
SELECT p.id, p.given_name, p.family_name, p.gf_name_eng, p.first_name_amh, p.family_name_amh, p.gf_name_amh,
       p.gender, p.birthdate, p.age_int, p.martial_status, p.education, p.is_disabled, p.farming_type,
       p.has_personal_phone, p.has_national_id, p.hh_is_household_head, p.is_psnp_user, p.email,
       p.registration_date, p.partner_latitude, p.partner_longitude, p.farmer_id, p.state, p.rejection_reason,
       p.odk_instance_id, NULL::boolean AS is_duplicated, p.size_of_family, p.number_of_children_in_family,
       p.number_of_males_in_family, p.number_of_females_in_family, p.other_family_member_own_land,
       p.other_farmer_in_hh, p.father_included, p.mother_included, p.create_date, p.write_date,
       p.is_farmer, p.occupation, p.address, p.first_name_other, p.family_name_other, p.gf_name_other,
       p.disabled, p.disabled_reason, p.additional_g2p_info::text AS additional_g2p_info,
       e.name AS enumerator_name, e.enumerator_user_id, e.data_collection_date, e.enum_latitude, e.enum_longitude,
       e.enum_altitude, e.enum_accuracy,
       lang.name AS language, src.name AS import_source,
       r.code AS region_code, r.name AS region_name, z.code AS zone_code, z.name AS zone_name,
       w.code AS woreda_code, w.name AS woreda_name, k.code AS kebele_code, k.name AS kebele_name
  FROM res_partner p
  LEFT JOIN g2p_lang lang ON lang.id = p."primary_Language"
  LEFT JOIN g2p_import_source src ON src.id = p.rec_import_source
  LEFT JOIN g2p_enumerator e ON e.id = p.enumerator_id
  LEFT JOIN g2p_region r ON r.id = p.region
  LEFT JOIN g2p_zone z ON z.id = p.zone
  LEFT JOIN g2p_woreda w ON w.id = p.woreda
  LEFT JOIN g2p_kebele k ON k.id = p.kebele
 WHERE p.id = ANY(%s) AND p.active AND NOT p.is_group
"""


def _rows(cur, sql, params=()):
    cur.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


# The farmers in scope: registrants that are people, not archived in Odoo
IN_SCOPE = "p.is_registrant AND NOT p.is_group AND p.active"


def select_farmers(conn, limit=None, ids=None, complete=False) -> list[int]:
    """Odoo ids of the farmers to migrate: the given ids, or every farmer in
    scope (the first `limit` of them; with complete, only those with a
    household, a land and a crop, to try every part). Ordered by household, so
    a batch carries whole households."""
    with conn.cursor() as cur:
        if ids:
            return sorted(int(i) for i in ids)
        extra = """ AND EXISTS (SELECT 1 FROM g2p_group_membership m WHERE m.individual = p.id)
                    AND EXISTS (SELECT 1 FROM g2p_land_information l WHERE l.partner_id = p.id)
                    AND EXISTS (SELECT 1 FROM g2p_crop_information c WHERE c.partner_id = p.id)""" if complete else ""
        cur.execute("SELECT p.id FROM res_partner p WHERE " + IN_SCOPE + extra
                    + " ORDER BY (SELECT min(m.\"group\") FROM g2p_group_membership m WHERE m.individual = p.id) NULLS LAST, p.id"
                    + (" LIMIT %s" if limit else ""), (limit,) if limit else ())
        return [r[0] for r in cur.fetchall()]


def read(conn, farmer_ids: list[int]) -> dict:
    with conn.cursor() as cur:
        # The households of these farmers, and every member of them
        memberships = _rows(cur, """
            SELECT m.id, m."group" AS household_id, m.individual AS farmer_id, m.start_date, m.status, m.is_ended,
                   (SELECT string_agg(k.name, ',' ORDER BY k.name)
                      FROM g2p_group_membership_g2p_group_membership_kind_rel rel
                      JOIN g2p_group_membership_kind k ON k.id = rel.g2p_group_membership_kind_id
                     WHERE rel.g2p_group_membership_id = m.id) AS kinds
              FROM g2p_group_membership m
             WHERE m."group" IN (SELECT "group" FROM g2p_group_membership WHERE individual = ANY(%s))
               AND NOT coalesce(m.is_ended, false)
             ORDER BY m."group", m.id""", (farmer_ids,))
        everyone = sorted(set(farmer_ids) | {m["farmer_id"] for m in memberships})
        households = _rows(cur, """
            SELECT id, name, create_date, write_date FROM res_partner WHERE id = ANY(%s)""",
                           (sorted({m["household_id"] for m in memberships}),))
        farmers = _rows(cur, FARMERS, (everyone,))
        ids = _rows(cur, """
            SELECT r.partner_id, t.name AS id_type, r.value, r.status
              FROM g2p_reg_id r JOIN g2p_id_type t ON t.id = r.id_type
             WHERE r.partner_id = ANY(%s) ORDER BY r.id""", (everyone,))
        incomes = _rows(cur, """
            SELECT rel.res_partner_id AS partner_id, i.name
              FROM g2p_hh_income_res_partner_rel rel JOIN g2p_hh_income i ON i.id = rel.g2p_hh_income_id
             WHERE rel.res_partner_id = ANY(%s)""", (everyone,))
        phones = _rows(cur, """
            SELECT id, partner_id, phone_no, phone_type, disabled, create_date, write_date
              FROM g2p_phone_number WHERE partner_id = ANY(%s) ORDER BY partner_id, id""", (everyone,))
        lands = _rows(cur, """
            SELECT l.id, l.partner_id, l.land_id, l.ownership_type, l.total_land_area, l.certficate_provided,
                   l.year_of_acquisition, l.polygon_data, l.current_land_use, l.soil_fertility,
                   l.means_of_acquisition, l.remark, l.create_date, l.write_date, k.code AS kebele_code
              FROM g2p_land_information l LEFT JOIN g2p_kebele k ON k.id = l.land_kebele
             WHERE l.partner_id = ANY(%s) ORDER BY l.partner_id, l.id""", (everyone,))
        crops = _rows(cur, """
            SELECT c.id, c.partner_id, g.name AS crop, s.name AS season, c.collected_gc, c.collected_ec,
                   c.is_diseased, c.create_date, c.write_date,
                   (SELECT string_agg(t.name, ',' ORDER BY t.name)
                      FROM g2p_crop_information_g2p_illness_type_rel rel
                      JOIN g2p_illness_type t ON t.id = rel.g2p_illness_type_id
                     WHERE rel.g2p_crop_information_id = c.id) AS illnesses
              FROM g2p_crop_information c
              LEFT JOIN g2p_crop g ON g.id = c.crop
              LEFT JOIN g2p_season s ON s.id = c.season
             WHERE c.partner_id = ANY(%s) ORDER BY c.partner_id, c.id""", (everyone,))
    return {"farmers": farmers, "households": households, "memberships": memberships, "ids": ids,
            "incomes": incomes, "phones": phones, "lands": lands, "crops": crops}


# -- units --------------------------------------------------------------------------------

def database_uuid(conn) -> str | None:
    """Odoo's own id of this database, None when it has none."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('ir_config_parameter')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT value FROM ir_config_parameter WHERE key = 'database.uuid'")
        row = cur.fetchone()
        return row[0] if row else None


def units(conn, farmer_ids: list[int]) -> tuple[list[Unit], list[int]]:
    """The units these farmers belong to, each whole, and the ids that are no
    active person. Households that share a member are one unit: the member's
    records depend on both."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM res_partner WHERE id = ANY(%s) AND active AND NOT is_group", (farmer_ids,))
        people = {r[0] for r in cur.fetchall()}
        cur.execute("""
            SELECT m."group", m.individual FROM g2p_group_membership m JOIN res_partner p ON p.id = m.individual
             WHERE NOT coalesce(m.is_ended, false) AND p.active AND NOT p.is_group AND m."group" IS NOT NULL
             ORDER BY 1, 2""")
        parent, members, groups_of = {}, collections.defaultdict(list), collections.defaultdict(list)

        def root(g):
            while parent[g] != g:
                parent[g] = parent[parent[g]]
                g = parent[g]
            return g

        for group, person in cur.fetchall():
            parent.setdefault(group, group)
            members[group].append(person)
            groups_of[person].append(group)
    for groups in groups_of.values():
        for other in groups[1:]:
            a, b = root(groups[0]), root(other)
            parent[max(a, b)] = min(a, b)  # the root is the lowest group id
    together = collections.defaultdict(list)
    for group in parent:
        together[root(group)].append(group)

    out, done, solo = [], set(), []
    for fid in farmer_ids:
        if fid not in people:
            continue
        if fid not in groups_of:
            solo.append(fid)
            continue
        top = root(groups_of[fid][0])
        if top not in done:
            done.add(top)
            households = tuple(sorted(together[top]))
            out.append(Unit(f"household-{top}", tuple(sorted({p for g in households for p in members[g]})), households))
    out.sort(key=lambda u: u.households[0])
    out += [Unit(f"solo-{fid}", (fid,), ()) for fid in dict.fromkeys(solo)]
    return out, [f for f in farmer_ids if f not in people]


def batches(all_units: list[Unit], size: int) -> list[list[Unit]]:
    """Whole units, about `size` farmers per batch (a larger unit is a batch of its own)."""
    out, current, n = [], [], 0
    for unit in all_units:
        if current and n + len(unit.farmers) > size:
            out.append(current)
            current, n = [], 0
        current.append(unit)
        n += len(unit.farmers)
    return out + [current] if current else out


class SourceChanged(Exception):
    """Farmer profile's households changed between planning the run and reading them."""


def split(data: dict, some_units: list[Unit]) -> dict:
    """read()'s result per unit: key -> the same dict, holding that unit's rows only."""
    out = {u.key: {part: [] for part in data} for u in some_units}
    of_farmer = {f: u.key for u in some_units for f in u.farmers}
    of_household = {h: u.key for u in some_units for h in u.households}
    for row in data["farmers"]:
        if row["id"] in of_farmer:
            out[of_farmer[row["id"]]]["farmers"].append(row)
    for part, owner in (("households", "id"), ("memberships", "household_id")):
        for row in data[part]:
            if row[owner] in of_household:
                out[of_household[row[owner]]][part].append(row)
    for part in ("ids", "incomes", "phones", "lands", "crops"):
        for row in data[part]:
            if row["partner_id"] in of_farmer:
                out[of_farmer[row["partner_id"]]][part].append(row)
    return out


def merge(parts: list[dict]) -> dict:
    """The opposite of split."""
    keys = ("farmers", "households", "memberships", "ids", "incomes", "phones", "lands", "crops")
    return {k: [row for p in parts for row in p[k]] for k in keys}


def _check_unit(unit: Unit, data: dict, everything: dict):
    """The unit as read must be the unit as planned."""
    mine = {f["id"] for f in data["farmers"]}
    households = {m["household_id"] for m in everything["memberships"] if m["farmer_id"] in mine}
    if mine != set(unit.farmers) or households != set(unit.households):
        raise SourceChanged("farmer profile changed while the migration was running: rerun to migrate it")


def read_units(conn, some_units: list[Unit]) -> list[tuple]:
    """(unit, its data, None) or (unit, None, the error) for each unit. One value the
    driver cannot read (e.g. a date in the year 20023) fails its unit only. A
    lost connection or a missing table is raised: it is nobody's record."""
    def one(group):
        data = read(conn, sorted({f for u in group for f in u.farmers}))
        per_unit, out = split(data, group), []
        for u in group:
            try:
                _check_unit(u, per_unit[u.key], data)
                out.append((u, per_unit[u.key], None))
            except SourceChanged as exc:
                out.append((u, None, exc))
        return out

    try:
        return one(some_units)
    except (psycopg2.DataError, ValueError, OverflowError) as exc:
        conn.rollback()
        if len(some_units) == 1:
            return [(some_units[0], None, exc)]
        middle = len(some_units) // 2
        return read_units(conn, some_units[:middle]) + read_units(conn, some_units[middle:])


# -- fingerprints: has a unit changed since it was migrated? ------------------------------
# Only what the migration uses counts. Left out: Odoo's own dates, the age Odoo
# recomputes from the birth date, and a location's name when it has a code
# (renaming a region is not a change to every farmer in it).
_NOT_COUNTED = {"create_date", "write_date", "start_date", "status", "is_ended", "is_duplicated"}


def fingerprint(data: dict) -> dict:
    """part -> a hash of its rows, e.g. {"farmers": "9f..", "phones": "07.."}."""
    out = {}
    for part, rows in data.items():
        lines = []
        for row in rows:
            kept = {k: v for k, v in row.items() if k not in _NOT_COUNTED}
            if part == "households":
                kept.pop("name", None)
            if part == "farmers":
                if kept.get("birthdate"):
                    kept.pop("age_int", None)
                for level in ("region", "zone", "woreda", "kebele"):
                    if kept.get(f"{level}_code"):
                        kept.pop(f"{level}_name", None)
            lines.append(json.dumps(kept, sort_keys=True, ensure_ascii=True, default=str))
        out[part] = hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()[:16]
    return out


def changed_parts(before: dict, now: dict) -> list[str]:
    return sorted(k for k in {*before, *now} if before.get(k) != now.get(k))
