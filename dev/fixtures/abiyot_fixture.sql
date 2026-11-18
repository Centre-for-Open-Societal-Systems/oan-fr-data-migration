-- One presentation farmer for a local migration recheck.
-- Run only against farmer_registry_gen1 or the local demo clone, never production.
BEGIN;

INSERT INTO res_partner (
    id, company_id, type, name, active, is_registrant, is_group,
    given_name, family_name, gf_name_eng, gender, birthdate,
    is_farmer, hh_is_household_head, has_personal_phone,
    has_national_id, is_psnp_user, farmer_id, state,
    size_of_family, number_of_males_in_family, number_of_females_in_family,
    create_date, write_date
) VALUES
    (900008, 1, 'contact', 'PRESENTATION-HH-003', true, false, true,
     NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
     1, 1, 0, now(), now()),
    (900009, 1, 'contact', 'Abiyot Lemma', true, true, false,
     'Abiyot', 'Lemma', 'Tesfaye', 'male', DATE '1988-06-15',
     'yes', true, true, true, false, 'PRES-FR-005', 'active',
     1, 1, 0, now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_group_membership (
    id, "group", individual, status, is_ended, start_date, create_date, write_date
) VALUES
    (910005, 900008, 900009, 'active', false, DATE '2024-02-01', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_group_membership_g2p_group_membership_kind_rel
    (g2p_group_membership_id, g2p_group_membership_kind_id)
VALUES (910005, 6)
ON CONFLICT DO NOTHING;

INSERT INTO g2p_phone_number (
    id, partner_id, phone_no, phone_sanitized, phone_type, date_collected,
    create_date, write_date
) VALUES
    (940005, 900009, '+251911000005', '+251911000005', 'primary', DATE '2025-02-01', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_land_information (
    id, partner_id, land_id, ownership_type, total_land_area,
    certficate_provided, year_of_acquisition, polygon_data,
    soil_fertility, means_of_acquisition, remark, create_date, write_date
) VALUES
    (920005, 900009, 'ABIYOT-LAND-001', 'owner', 1.50,
     true, DATE '2018-01-01', '[[9.40,38.40],[9.50,38.40],[9.50,38.50]]',
     'High', 'Inheritance', 'Synthetic parcel for Abiyot', now(), now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO g2p_crop_information (
    id, partner_id, crop, collected_gc, collected_ec, is_diseased,
    create_date, write_date
) VALUES
    (930006, 900009, 1, DATE '2025-10-03', '2018-01-23', 'no', now(), now())
ON CONFLICT (id) DO NOTHING;

COMMIT;
