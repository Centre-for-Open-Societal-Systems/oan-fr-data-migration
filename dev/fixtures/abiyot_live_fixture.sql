-- One farmer for the live Gen1 -> Gen2 migration demo.
-- Run only against farmer_registry_gen1, never production.
BEGIN;

INSERT INTO res_partner (
    id, company_id, type, name, active, is_registrant, is_group,
    given_name, family_name, gf_name_eng, gender, birthdate,
    is_farmer, hh_is_household_head, has_personal_phone,
    has_national_id, is_psnp_user, farmer_id, state,
    size_of_family, number_of_males_in_family, number_of_females_in_family,
    create_date, write_date
) VALUES
    (900010, 1, 'contact', 'PRESENTATION-HH-004', true, false, true,
     NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
     1, 1, 0, now(), now()),
    (900011, 1, 'contact', 'Abiyot Bekele', true, true, false,
     'Abiyot', 'Bekele', 'Lemma', 'male', DATE '1990-11-04',
     'yes', true, true, true, false, 'PRES-FR-006', 'active',
     1, 1, 0, now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_group_membership (
    id, "group", individual, status, is_ended, start_date, create_date, write_date
) VALUES
    (910006, 900010, 900011, 'active', false, DATE '2024-02-01', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_group_membership_g2p_group_membership_kind_rel
    (g2p_group_membership_id, g2p_group_membership_kind_id)
VALUES (910006, 6)
ON CONFLICT DO NOTHING;

INSERT INTO g2p_phone_number (
    id, partner_id, phone_no, phone_sanitized, phone_type, date_collected,
    create_date, write_date
) VALUES
    (940006, 900011, '+251911000006', '+251911000006', 'primary', DATE '2025-02-01', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_land_information (
    id, partner_id, land_id, ownership_type, total_land_area,
    certficate_provided, year_of_acquisition, polygon_data,
    soil_fertility, means_of_acquisition, remark, create_date, write_date
) VALUES
    (920006, 900011, 'ABIYOT-BEKELE-LAND-001', 'owner', 2.25,
     true, DATE '2017-01-01', '[[9.60,38.60],[9.70,38.60],[9.70,38.70]]',
     'High', 'Inheritance', 'Synthetic parcel for the live demo', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_crop_information (
    id, partner_id, crop, collected_gc, collected_ec, is_diseased,
    create_date, write_date
) VALUES
    (930007, 900011, 2, DATE '2025-10-04', '2018-01-24', 'no', now(), now())
ON CONFLICT (id) DO NOTHING;

COMMIT;
