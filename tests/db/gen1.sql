-- The parts of farmer profile's (Odoo) database the migration reads, empty.
CREATE TABLE ir_config_parameter (id serial PRIMARY KEY, key text, value text);
CREATE TABLE ir_model_fields (id serial PRIMARY KEY, model text, name text, ttype text, store boolean, relation text,
  relation_field text, relation_table text, column1 text, field_description jsonb);
CREATE TABLE ir_model_data (id serial PRIMARY KEY, module text, model text, res_id integer);
CREATE TABLE g2p_lang (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_import_source (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_enumerator (id integer PRIMARY KEY, name varchar, enumerator_user_id varchar, data_collection_date date,
  enum_latitude numeric, enum_longitude numeric, enum_altitude double precision, enum_accuracy double precision);
CREATE TABLE g2p_region (id integer PRIMARY KEY, code varchar, name varchar);
CREATE TABLE g2p_zone (id integer PRIMARY KEY, code varchar, name varchar);
CREATE TABLE g2p_woreda (id integer PRIMARY KEY, code varchar, name varchar);
CREATE TABLE g2p_kebele (id integer PRIMARY KEY, code varchar, name varchar);
CREATE TABLE res_partner (
  id integer PRIMARY KEY, name varchar, active boolean DEFAULT true, is_registrant boolean DEFAULT true,
  is_group boolean DEFAULT false,
  given_name varchar, family_name varchar, gf_name_eng varchar, first_name_amh varchar, family_name_amh varchar,
  gf_name_amh varchar, first_name_other varchar, family_name_other varchar, gf_name_other varchar, gender varchar,
  birthdate date, age_int integer, martial_status varchar, education varchar, is_disabled varchar, farming_type varchar,
  has_personal_phone varchar, has_national_id varchar, hh_is_household_head varchar, is_psnp_user boolean, email varchar,
  registration_date date, partner_latitude numeric, partner_longitude numeric, farmer_id varchar, state varchar,
  rejection_reason text, odk_instance_id varchar, size_of_family integer, number_of_children_in_family integer,
  number_of_males_in_family integer, number_of_females_in_family integer, other_family_member_own_land varchar,
  other_farmer_in_hh varchar, father_included boolean, mother_included boolean, is_farmer varchar, occupation varchar,
  address text, disabled timestamp, disabled_reason text, additional_g2p_info jsonb, "primary_Language" integer,
  rec_import_source integer, enumerator_id integer, region integer, zone integer, woreda integer, kebele integer,
  create_date timestamp DEFAULT '2025-01-01', write_date timestamp DEFAULT '2025-01-02');
CREATE TABLE g2p_group_membership (id integer PRIMARY KEY, "group" integer, individual integer, start_date timestamp,
  ended_date timestamp, status varchar, is_ended boolean);
CREATE TABLE g2p_group_membership_kind (id integer PRIMARY KEY, name varchar);
INSERT INTO g2p_group_membership_kind VALUES (1, 'Head'), (4, 'Son');
CREATE TABLE g2p_group_membership_g2p_group_membership_kind_rel (g2p_group_membership_id integer,
  g2p_group_membership_kind_id integer);
CREATE TABLE g2p_id_type (id integer PRIMARY KEY, name varchar);
INSERT INTO g2p_id_type VALUES (1, 'UID'), (2, 'FAN'), (3, 'RID');
CREATE TABLE g2p_reg_id (id integer PRIMARY KEY, partner_id integer, id_type integer, value varchar, status varchar);
CREATE TABLE g2p_hh_income (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_hh_income_res_partner_rel (res_partner_id integer, g2p_hh_income_id integer);
CREATE TABLE g2p_phone_number (id integer PRIMARY KEY, partner_id integer, phone_no varchar, phone_type varchar,
  disabled timestamp, create_date timestamp DEFAULT '2025-01-01', write_date timestamp DEFAULT '2025-01-01');
CREATE TABLE g2p_land_information (id integer PRIMARY KEY, partner_id integer, land_id varchar, ownership_type varchar,
  total_land_area numeric, certficate_provided boolean, year_of_acquisition date, polygon_data text,
  current_land_use text, soil_fertility text, means_of_acquisition text, remark varchar, land_kebele integer,
  create_date timestamp DEFAULT '2025-01-01', write_date timestamp DEFAULT '2025-01-01');
CREATE TABLE g2p_crop (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_season (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_crop_information (id integer PRIMARY KEY, partner_id integer, crop integer, season integer,
  collected_gc date, collected_ec varchar, is_diseased varchar,
  create_date timestamp DEFAULT '2025-01-01', write_date timestamp DEFAULT '2025-01-01');
CREATE TABLE g2p_illness_type (id integer PRIMARY KEY, name varchar);
CREATE TABLE g2p_crop_information_g2p_illness_type_rel (g2p_crop_information_id integer, g2p_illness_type_id integer);
CREATE TABLE g2p_livestock_information (id integer PRIMARY KEY, partner_id integer);
CREATE INDEX ON g2p_group_membership (individual);
CREATE INDEX ON g2p_group_membership ("group");
CREATE INDEX ON g2p_phone_number (partner_id);
CREATE INDEX ON g2p_land_information (partner_id);
