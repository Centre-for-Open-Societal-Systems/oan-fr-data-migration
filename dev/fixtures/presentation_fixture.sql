-- Synthetic records for a local migration presentation only.
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
    (900001, 1, 'contact', 'PRESENTATION-HH-001', true, false, true,
     NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
     2, 1, 1, now(), now()),
    (900002, 1, 'contact', 'Presentation Farmer One', true, true, false,
     'Abebe', 'Kebede', 'Tola', 'male', DATE '1980-01-01',
     'yes', true, true, true, false, 'PRES-FR-001', 'active',
     2, 1, 1, now(), now()),
    (900003, 1, 'contact', 'Presentation Household Member', true, false, false,
     'Almaz', 'Bekele', 'Desta', 'female', DATE '1985-05-20',
     'no', false, true, true, false, NULL, 'active',
     NULL, NULL, NULL, now(), now()),
    (900004, 1, 'contact', 'Presentation Farmer Two', true, true, false,
     'Chala', 'Gemechu', 'Boru', 'male', DATE '1990-07-15',
     'yes', true, false, false, true, 'PRES-FR-002', 'active',
     1, 1, 0, now(), now());

INSERT INTO g2p_group_membership (
    id, "group", individual, status, is_ended, start_date, create_date, write_date
) VALUES
    (910001, 900001, 900002, 'active', false, DATE '2024-01-01', now(), now()),
    (910002, 900001, 900003, 'active', false, DATE '2024-01-01', now(), now());

INSERT INTO g2p_group_membership_g2p_group_membership_kind_rel
    (g2p_group_membership_id, g2p_group_membership_kind_id)
VALUES (910001, 1), (910002, 2);

INSERT INTO g2p_phone_number (
    id, partner_id, phone_no, phone_sanitized, phone_type, date_collected,
    create_date, write_date
) VALUES
    (940001, 900002, '+251911000001', '+251911000001', 'primary', DATE '2025-01-01', now(), now()),
    (940002, 900003, '+251911000002', '+251911000002', 'primary', DATE '2025-01-01', now(), now());

INSERT INTO g2p_land_information (
    id, partner_id, land_id, ownership_type, total_land_area,
    certficate_provided, year_of_acquisition, polygon_data,
    soil_fertility, means_of_acquisition, remark, create_date, write_date
) VALUES
    (920001, 900002, 'PRES-LAND-001', 'owner', 1.50,
     true, DATE '2018-01-01', '[[9.00,38.00],[9.10,38.00],[9.10,38.10]]',
     'High', 'Inheritance', 'Synthetic presentation parcel one', now(), now()),
    (920002, 900002, 'PRES-LAND-002', 'renter', 0.75,
     false, DATE '2022-01-01', NULL,
     'Medium', 'Rent', 'Synthetic presentation parcel two', now(), now());

INSERT INTO g2p_crop_information (
    id, partner_id, crop, collected_gc, collected_ec, is_diseased,
    create_date, write_date
) VALUES
    (930001, 900002, 3, DATE '2025-09-01', '2017-12-26', 'no', now(), now()),
    (930002, 900002, 2, DATE '2025-09-02', '2017-12-27', 'no', now(), now()),
    (930003, 900004, 3, DATE '2025-09-03', '2017-12-28', 'no', now(), now());

COMMIT;
