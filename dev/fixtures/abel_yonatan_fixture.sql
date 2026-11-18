-- Two presentation farmers for a local migration test only.
-- Run only against farmer_registry_migration_demo_20261113, never production.
BEGIN;

INSERT INTO res_partner (
    id, company_id, type, name, active, is_registrant, is_group,
    given_name, family_name, gf_name_eng, gender, birthdate,
    is_farmer, hh_is_household_head, has_personal_phone,
    has_national_id, is_psnp_user, farmer_id, state,
    size_of_family, number_of_males_in_family, number_of_females_in_family,
    create_date, write_date
) VALUES
    (900005, 1, 'contact', 'PRESENTATION-HH-002', true, false, true,
     NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
     2, 2, 0, now(), now()),
    (900006, 1, 'contact', 'Abel Tesfaye', true, true, false,
     'Abel', 'Tesfaye', 'Bekele', 'male', DATE '1984-03-12',
     'yes', true, true, true, false, 'PRES-FR-003', 'active',
     2, 2, 0, now(), now()),
    (900007, 1, 'contact', 'Yonatan Bekele', true, true, false,
     'Yonatan', 'Bekele', 'Tesfaye', 'male', DATE '1992-08-21',
     'yes', false, true, false, false, 'PRES-FR-004', 'active',
     2, 2, 0, now(), now());

INSERT INTO g2p_group_membership (
    id, "group", individual, status, is_ended, start_date, create_date, write_date
) VALUES
    (910003, 900005, 900006, 'active', false, DATE '2024-02-01', now(), now()),
    (910004, 900005, 900007, 'active', false, DATE '2024-02-01', now(), now());

INSERT INTO g2p_group_membership_g2p_group_membership_kind_rel
    (g2p_group_membership_id, g2p_group_membership_kind_id)
VALUES (910003, 1), (910004, 6);

INSERT INTO g2p_phone_number (
    id, partner_id, phone_no, phone_sanitized, phone_type, date_collected,
    create_date, write_date
) VALUES
    (940003, 900006, '+251911000003', '+251911000003', 'primary', DATE '2025-02-01', now(), now()),
    (940004, 900007, '+251911000004', '+251911000004', 'primary', DATE '2025-02-01', now(), now());

INSERT INTO g2p_land_information (
    id, partner_id, land_id, ownership_type, total_land_area,
    certficate_provided, year_of_acquisition, polygon_data,
    soil_fertility, means_of_acquisition, remark, create_date, write_date
) VALUES
    (920003, 900006, 'ABEL-LAND-001', 'owner', 2.00,
     true, DATE '2016-01-01', '[[9.20,38.20],[9.30,38.20],[9.30,38.30]]',
     'High', 'Inheritance', 'Synthetic parcel for Abel', now(), now()),
    (920004, 900007, 'YONATAN-LAND-001', 'renter', 1.25,
     false, DATE '2021-01-01', NULL,
     'Medium', 'Rent', 'Synthetic parcel for Yonatan', now(), now());

INSERT INTO g2p_crop_information (
    id, partner_id, crop, collected_gc, collected_ec, is_diseased,
    create_date, write_date
) VALUES
    (930004, 900006, 1, DATE '2025-10-01', '2018-01-21', 'no', now(), now()),
    (930005, 900007, 2, DATE '2025-10-02', '2018-01-22', 'no', now(), now());

COMMIT;
