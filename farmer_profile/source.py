"""Reads farmer profile records from the Odoo database (read-only).

select_farmers picks the farmers to migrate; read() returns everything about
them as plain dicts keyed by Odoo id, including every member of their
households, so a household is always migrated whole.
"""

FARMERS = """
SELECT p.id, p.given_name, p.family_name, p.gf_name_eng, p.first_name_amh, p.family_name_amh, p.gf_name_amh,
       p.gender, p.birthdate, p.age_int, p.martial_status, p.education, p.is_disabled, p.farming_type,
       p.has_personal_phone, p.has_national_id, p.hh_is_household_head, p.is_psnp_user, p.email,
       p.registration_date, p.partner_latitude, p.partner_longitude, p.farmer_id, p.state, p.rejection_reason,
       p.odk_instance_id, p.is_duplicated, p.size_of_family, p.number_of_children_in_family,
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
