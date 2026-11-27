-- Gen2 tables for test_history.sh: the six registers' live and history tables, as the
-- registry (staff-api 1.2.2-rc.625) and the farmer extension (farmer-registry develop 7bda4f0) create them,
-- and the register, section and tab metadata the script reads. Regenerate: see README.

\restrict dxp1yCmdRjJ1tcwnDViIVW5wxoFogdHeGU0Z5aVG5eKNptIA8x5B1XdYewJldun

CREATE TABLE public.g2p_register_crops (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    commodity character varying,
    planted_date date,
    season character varying,
    end_use character varying,
    water_sources json,
    planted_date_ec character varying,
    is_diseased boolean,
    disease_type character varying
);

CREATE TABLE public.g2p_register_farmer_phones (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    phone_type character varying,
    phone_number character varying,
    country_code character varying,
    is_primary boolean,
    phone_e164 character varying
);

CREATE TABLE public.g2p_register_farmers (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    foundational_id character varying,
    first_name character varying,
    middle_name character varying,
    last_name character varying,
    given_name character varying,
    prefix character varying,
    suffix character varying,
    gender character varying,
    birth_date date,
    phone_numbers jsonb,
    emails jsonb,
    marital_status character varying,
    occupation character varying,
    income_level character varying,
    language_code character varying,
    education_level character varying,
    registration_date date,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    estimated_age integer,
    has_personal_phone boolean,
    disabled boolean,
    disability_type character varying,
    disability_severity character varying,
    source_of_income character varying,
    source_of_income_other character varying,
    language_spoken character varying,
    national_id_masked character varying,
    income_sources json,
    first_name_local character varying,
    middle_name_local character varying,
    last_name_local character varying,
    local_name_from_fayda boolean,
    email character varying,
    is_psnp_user boolean,
    birth_date_ec character varying,
    local_language character varying,
    is_household_head boolean,
    rid character varying,
    odk_farmer_id character varying,
    pula_id character varying,
    enumerator_name character varying,
    enumerator_user_id character varying,
    data_collection_date date,
    enumerator_latitude numeric(10,7),
    enumerator_longitude numeric(10,7),
    enumerator_altitude numeric(10,2),
    enumerator_accuracy numeric(10,2),
    total_land_area numeric(16,2),
    total_land_owned_area numeric(16,2),
    total_land_rent_area numeric(16,2),
    total_land_crop_sharing_area numeric(16,2),
    land_ownership character varying,
    total_plots integer,
    primary_phone_number character varying,
    region_name character varying,
    zone_name character varying,
    woreda_name character varying,
    kebele_name character varying,
    has_national_id boolean,
    is_farmer boolean,
    farming_type character varying,
    father_first_name character varying,
    father_middle_name character varying,
    father_last_name character varying,
    import_source character varying,
    odk_instance_id character varying,
    is_duplicated boolean,
    legacy_state character varying,
    identity_document_type character varying,
    land_document_type character varying,
    farmer_document_type character varying,
    bank_document_type character varying,
    representative_document_type character varying,
    other_document_purpose character varying,
    other_document_name character varying,
    last_authentication_id character varying,
    last_authenticated_at timestamp without time zone,
    last_authentication_status character varying,
    authentication_expiry_at timestamp without time zone,
    authentication_expiry_notified boolean NOT NULL,
    authentication_token character varying
);

CREATE TABLE public.g2p_register_history_crops (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    commodity character varying,
    planted_date date,
    season character varying,
    end_use character varying,
    water_sources json,
    planted_date_ec character varying,
    is_diseased boolean,
    disease_type character varying
);

CREATE TABLE public.g2p_register_history_farmer_phones (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    phone_type character varying,
    phone_number character varying,
    country_code character varying,
    is_primary boolean,
    phone_e164 character varying
);

CREATE TABLE public.g2p_register_history_farmers (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    foundational_id character varying,
    first_name character varying,
    middle_name character varying,
    last_name character varying,
    given_name character varying,
    prefix character varying,
    suffix character varying,
    gender character varying,
    birth_date date,
    phone_numbers jsonb,
    emails jsonb,
    marital_status character varying,
    occupation character varying,
    income_level character varying,
    language_code character varying,
    education_level character varying,
    registration_date date,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    estimated_age integer,
    has_personal_phone boolean,
    disabled boolean,
    disability_type character varying,
    disability_severity character varying,
    source_of_income character varying,
    source_of_income_other character varying,
    language_spoken character varying,
    national_id_masked character varying,
    income_sources json,
    first_name_local character varying,
    middle_name_local character varying,
    last_name_local character varying,
    local_name_from_fayda boolean,
    email character varying,
    is_psnp_user boolean,
    birth_date_ec character varying,
    local_language character varying,
    is_household_head boolean,
    rid character varying,
    odk_farmer_id character varying,
    pula_id character varying,
    enumerator_name character varying,
    enumerator_user_id character varying,
    data_collection_date date,
    enumerator_latitude numeric(10,7),
    enumerator_longitude numeric(10,7),
    enumerator_altitude numeric(10,2),
    enumerator_accuracy numeric(10,2),
    total_land_area numeric(16,2),
    total_land_owned_area numeric(16,2),
    total_land_rent_area numeric(16,2),
    total_land_crop_sharing_area numeric(16,2),
    land_ownership character varying,
    total_plots integer,
    primary_phone_number character varying,
    region_name character varying,
    zone_name character varying,
    woreda_name character varying,
    kebele_name character varying,
    has_national_id boolean,
    is_farmer boolean,
    farming_type character varying,
    father_first_name character varying,
    father_middle_name character varying,
    father_last_name character varying,
    import_source character varying,
    odk_instance_id character varying,
    is_duplicated boolean,
    legacy_state character varying,
    identity_document_type character varying,
    land_document_type character varying,
    farmer_document_type character varying,
    bank_document_type character varying,
    representative_document_type character varying,
    other_document_purpose character varying,
    other_document_name character varying
);

CREATE TABLE public.g2p_register_history_household_members (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    foundational_id character varying,
    first_name character varying,
    middle_name character varying,
    last_name character varying,
    given_name character varying,
    prefix character varying,
    suffix character varying,
    gender character varying,
    birth_date date,
    phone_numbers jsonb,
    emails jsonb,
    marital_status character varying,
    occupation character varying,
    income_level character varying,
    language_code character varying,
    education_level character varying,
    registration_date date,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    is_disabled boolean,
    is_head boolean,
    relationship_to_the_head character varying,
    odk_member_id character varying,
    birth_date_ec character varying,
    certificate_storage_id text,
    certificate_provided boolean
);

CREATE TABLE public.g2p_register_history_households (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    household_head character varying,
    size_of_group integer,
    number_of_children integer,
    number_of_elderly_members integer,
    number_of_female_members integer,
    number_of_male_members integer,
    other_land_owner boolean,
    father_included boolean,
    mother_included boolean,
    other_farmer_in_household boolean
);

CREATE TABLE public.g2p_register_history_lands (
    history_record_id character varying NOT NULL,
    internal_record_id character varying NOT NULL,
    tab_id character varying NOT NULL,
    section_id character varying NOT NULL,
    change_request_id character varying,
    submission_id character varying,
    change_request_source character varying NOT NULL,
    is_primary_section boolean NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    subject_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    approved_by character varying NOT NULL,
    approved_at timestamp without time zone NOT NULL,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    shape_type character varying,
    shape_coordinates_json jsonb,
    land_ownership_type character varying,
    certificate_storage_id text,
    land_size numeric,
    unit character varying,
    soil_fertility character varying,
    current_land_use character varying,
    farming_type character varying,
    year_of_acquisition integer,
    means_of_acquisition character varying,
    land_id character varying,
    remark text,
    land_kebele character varying,
    area_in_hectare numeric(16,6),
    certificate_provided boolean
);

CREATE TABLE public.g2p_register_household_members (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    foundational_id character varying,
    first_name character varying,
    middle_name character varying,
    last_name character varying,
    given_name character varying,
    prefix character varying,
    suffix character varying,
    gender character varying,
    birth_date date,
    phone_numbers jsonb,
    emails jsonb,
    marital_status character varying,
    occupation character varying,
    income_level character varying,
    language_code character varying,
    education_level character varying,
    registration_date date,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    is_disabled boolean,
    is_head boolean,
    relationship_to_the_head character varying,
    odk_member_id character varying,
    birth_date_ec character varying,
    certificate_storage_id text,
    certificate_provided boolean
);

CREATE TABLE public.g2p_register_households (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    household_head character varying,
    size_of_group integer,
    number_of_children integer,
    number_of_elderly_members integer,
    number_of_female_members integer,
    number_of_male_members integer,
    other_land_owner boolean,
    father_included boolean,
    mother_included boolean,
    other_farmer_in_household boolean
);

CREATE TABLE public.g2p_register_lands (
    internal_record_id character varying NOT NULL,
    functional_record_id character varying,
    link_internal_record_id character varying,
    link_foundational_id character varying,
    record_name character varying,
    record_image_document_id text,
    created_by character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_approved_at timestamp without time zone NOT NULL,
    last_approved_by character varying NOT NULL,
    search_text text,
    record_status character varying NOT NULL,
    record_status_reason character varying,
    latitude double precision,
    longitude double precision,
    altitude double precision,
    plus_code character varying,
    address_line_1 character varying,
    address_line_2 character varying,
    postal_code character varying,
    country_code character varying,
    geo_lowest_level_value_id character varying,
    geo_code_hierarchy_json jsonb,
    shape_type character varying,
    shape_coordinates_json jsonb,
    land_ownership_type character varying,
    certificate_storage_id text,
    land_size numeric,
    unit character varying,
    soil_fertility character varying,
    current_land_use character varying,
    farming_type character varying,
    year_of_acquisition integer,
    means_of_acquisition character varying,
    land_id character varying,
    remark text,
    land_kebele character varying,
    area_in_hectare numeric(16,6),
    certificate_provided boolean
);

ALTER TABLE ONLY public.g2p_register_crops
    ADD CONSTRAINT g2p_register_crops_pkey PRIMARY KEY (internal_record_id);

ALTER TABLE ONLY public.g2p_register_farmer_phones
    ADD CONSTRAINT g2p_register_farmer_phones_pkey PRIMARY KEY (internal_record_id);

ALTER TABLE ONLY public.g2p_register_farmers
    ADD CONSTRAINT g2p_register_farmers_pkey PRIMARY KEY (internal_record_id);

ALTER TABLE ONLY public.g2p_register_history_crops
    ADD CONSTRAINT g2p_register_history_crops_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_history_farmer_phones
    ADD CONSTRAINT g2p_register_history_farmer_phones_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_history_farmers
    ADD CONSTRAINT g2p_register_history_farmers_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_history_household_members
    ADD CONSTRAINT g2p_register_history_household_members_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_history_households
    ADD CONSTRAINT g2p_register_history_households_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_history_lands
    ADD CONSTRAINT g2p_register_history_lands_pkey PRIMARY KEY (history_record_id);

ALTER TABLE ONLY public.g2p_register_household_members
    ADD CONSTRAINT g2p_register_household_members_pkey PRIMARY KEY (internal_record_id);

ALTER TABLE ONLY public.g2p_register_households
    ADD CONSTRAINT g2p_register_households_pkey PRIMARY KEY (internal_record_id);

ALTER TABLE ONLY public.g2p_register_lands
    ADD CONSTRAINT g2p_register_lands_pkey PRIMARY KEY (internal_record_id);

CREATE UNIQUE INDEX ix_g2p_register_crops_functional_record_id ON public.g2p_register_crops USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_crops_link_foundational_id ON public.g2p_register_crops USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_crops_link_internal_record_id ON public.g2p_register_crops USING btree (link_internal_record_id);

CREATE UNIQUE INDEX ix_g2p_register_farmer_phones_functional_record_id ON public.g2p_register_farmer_phones USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_farmer_phones_link_foundational_id ON public.g2p_register_farmer_phones USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_farmer_phones_link_internal_record_id ON public.g2p_register_farmer_phones USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_farmers_authentication_expiry_at ON public.g2p_register_farmers USING btree (authentication_expiry_at);

CREATE INDEX ix_g2p_register_farmers_country_code ON public.g2p_register_farmers USING btree (country_code);

CREATE INDEX ix_g2p_register_farmers_foundational_id ON public.g2p_register_farmers USING btree (foundational_id);

CREATE UNIQUE INDEX ix_g2p_register_farmers_functional_record_id ON public.g2p_register_farmers USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_farmers_geo_lowest_level_value_id ON public.g2p_register_farmers USING btree (geo_lowest_level_value_id);

CREATE INDEX ix_g2p_register_farmers_last_authentication_id ON public.g2p_register_farmers USING btree (last_authentication_id);

CREATE INDEX ix_g2p_register_farmers_link_foundational_id ON public.g2p_register_farmers USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_farmers_link_internal_record_id ON public.g2p_register_farmers USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_farmers_plus_code ON public.g2p_register_farmers USING btree (plus_code);

CREATE INDEX ix_g2p_register_farmers_postal_code ON public.g2p_register_farmers USING btree (postal_code);

CREATE INDEX ix_g2p_register_history_crops_functional_record_id ON public.g2p_register_history_crops USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_crops_internal_record_id ON public.g2p_register_history_crops USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_crops_link_foundational_id ON public.g2p_register_history_crops USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_crops_link_internal_record_id ON public.g2p_register_history_crops USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_crops_section_id ON public.g2p_register_history_crops USING btree (section_id);

CREATE INDEX ix_g2p_register_history_crops_subject_internal_record_id ON public.g2p_register_history_crops USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_crops_submission_id ON public.g2p_register_history_crops USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_crops_tab_id ON public.g2p_register_history_crops USING btree (tab_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_functional_record_id ON public.g2p_register_history_farmer_phones USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_internal_record_id ON public.g2p_register_history_farmer_phones USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_link_foundational_id ON public.g2p_register_history_farmer_phones USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_link_internal_record_id ON public.g2p_register_history_farmer_phones USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_section_id ON public.g2p_register_history_farmer_phones USING btree (section_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_subject_internal__e269 ON public.g2p_register_history_farmer_phones USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_submission_id ON public.g2p_register_history_farmer_phones USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_farmer_phones_tab_id ON public.g2p_register_history_farmer_phones USING btree (tab_id);

CREATE INDEX ix_g2p_register_history_farmers_foundational_id ON public.g2p_register_history_farmers USING btree (foundational_id);

CREATE INDEX ix_g2p_register_history_farmers_functional_record_id ON public.g2p_register_history_farmers USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_farmers_internal_record_id ON public.g2p_register_history_farmers USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_farmers_link_foundational_id ON public.g2p_register_history_farmers USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_farmers_link_internal_record_id ON public.g2p_register_history_farmers USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_farmers_section_id ON public.g2p_register_history_farmers USING btree (section_id);

CREATE INDEX ix_g2p_register_history_farmers_subject_internal_record_id ON public.g2p_register_history_farmers USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_farmers_submission_id ON public.g2p_register_history_farmers USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_farmers_tab_id ON public.g2p_register_history_farmers USING btree (tab_id);

CREATE INDEX ix_g2p_register_history_household_members_foundational_id ON public.g2p_register_history_household_members USING btree (foundational_id);

CREATE INDEX ix_g2p_register_history_household_members_functional_record_id ON public.g2p_register_history_household_members USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_household_members_internal_record_id ON public.g2p_register_history_household_members USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_household_members_link_foundational_id ON public.g2p_register_history_household_members USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_household_members_link_internal_2a6c ON public.g2p_register_history_household_members USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_household_members_section_id ON public.g2p_register_history_household_members USING btree (section_id);

CREATE INDEX ix_g2p_register_history_household_members_subject_inter_6801 ON public.g2p_register_history_household_members USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_household_members_submission_id ON public.g2p_register_history_household_members USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_household_members_tab_id ON public.g2p_register_history_household_members USING btree (tab_id);

CREATE INDEX ix_g2p_register_history_households_functional_record_id ON public.g2p_register_history_households USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_households_internal_record_id ON public.g2p_register_history_households USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_households_link_foundational_id ON public.g2p_register_history_households USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_households_link_internal_record_id ON public.g2p_register_history_households USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_households_section_id ON public.g2p_register_history_households USING btree (section_id);

CREATE INDEX ix_g2p_register_history_households_subject_internal_record_id ON public.g2p_register_history_households USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_households_submission_id ON public.g2p_register_history_households USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_households_tab_id ON public.g2p_register_history_households USING btree (tab_id);

CREATE INDEX ix_g2p_register_history_lands_functional_record_id ON public.g2p_register_history_lands USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_history_lands_internal_record_id ON public.g2p_register_history_lands USING btree (internal_record_id);

CREATE INDEX ix_g2p_register_history_lands_link_foundational_id ON public.g2p_register_history_lands USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_history_lands_link_internal_record_id ON public.g2p_register_history_lands USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_history_lands_section_id ON public.g2p_register_history_lands USING btree (section_id);

CREATE INDEX ix_g2p_register_history_lands_subject_internal_record_id ON public.g2p_register_history_lands USING btree (subject_internal_record_id);

CREATE INDEX ix_g2p_register_history_lands_submission_id ON public.g2p_register_history_lands USING btree (submission_id);

CREATE INDEX ix_g2p_register_history_lands_tab_id ON public.g2p_register_history_lands USING btree (tab_id);

CREATE INDEX ix_g2p_register_household_members_country_code ON public.g2p_register_household_members USING btree (country_code);

CREATE INDEX ix_g2p_register_household_members_foundational_id ON public.g2p_register_household_members USING btree (foundational_id);

CREATE UNIQUE INDEX ix_g2p_register_household_members_functional_record_id ON public.g2p_register_household_members USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_household_members_geo_lowest_level_value_id ON public.g2p_register_household_members USING btree (geo_lowest_level_value_id);

CREATE INDEX ix_g2p_register_household_members_link_foundational_id ON public.g2p_register_household_members USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_household_members_link_internal_record_id ON public.g2p_register_household_members USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_household_members_plus_code ON public.g2p_register_household_members USING btree (plus_code);

CREATE INDEX ix_g2p_register_household_members_postal_code ON public.g2p_register_household_members USING btree (postal_code);

CREATE INDEX ix_g2p_register_households_country_code ON public.g2p_register_households USING btree (country_code);

CREATE UNIQUE INDEX ix_g2p_register_households_functional_record_id ON public.g2p_register_households USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_households_geo_lowest_level_value_id ON public.g2p_register_households USING btree (geo_lowest_level_value_id);

CREATE INDEX ix_g2p_register_households_link_foundational_id ON public.g2p_register_households USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_households_link_internal_record_id ON public.g2p_register_households USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_households_plus_code ON public.g2p_register_households USING btree (plus_code);

CREATE INDEX ix_g2p_register_households_postal_code ON public.g2p_register_households USING btree (postal_code);

CREATE INDEX ix_g2p_register_lands_country_code ON public.g2p_register_lands USING btree (country_code);

CREATE UNIQUE INDEX ix_g2p_register_lands_functional_record_id ON public.g2p_register_lands USING btree (functional_record_id);

CREATE INDEX ix_g2p_register_lands_geo_lowest_level_value_id ON public.g2p_register_lands USING btree (geo_lowest_level_value_id);

CREATE INDEX ix_g2p_register_lands_link_foundational_id ON public.g2p_register_lands USING btree (link_foundational_id);

CREATE INDEX ix_g2p_register_lands_link_internal_record_id ON public.g2p_register_lands USING btree (link_internal_record_id);

CREATE INDEX ix_g2p_register_lands_plus_code ON public.g2p_register_lands USING btree (plus_code);

CREATE INDEX ix_g2p_register_lands_postal_code ON public.g2p_register_lands USING btree (postal_code);

\unrestrict dxp1yCmdRjJ1tcwnDViIVW5wxoFogdHeGU0Z5aVG5eKNptIA8x5B1XdYewJldun

CREATE TABLE g2p_register_definitions (register_id varchar PRIMARY KEY, register_mnemonic varchar NOT NULL UNIQUE, master_register_id varchar);
CREATE TABLE g2p_register_sections (section_id varchar PRIMARY KEY, register_id varchar NOT NULL, section_register_id varchar NOT NULL);
CREATE TABLE g2p_register_ui_tabs (tab_id varchar PRIMARY KEY, register_id varchar NOT NULL, tab_order integer NOT NULL);
CREATE TABLE g2p_register_ui_tab_sections (tab_section_id varchar PRIMARY KEY, register_id varchar NOT NULL, tab_id varchar NOT NULL, section_id varchar NOT NULL, section_order integer NOT NULL);
INSERT INTO g2p_register_definitions VALUES ('18df8370-3e9a-493f-aa27-fc1b9e05629c', 'FarmInputs', '493153d5-07ef-4743-8efd-07f4099772b9');
INSERT INTO g2p_register_definitions VALUES ('493153d5-07ef-4743-8efd-07f4099772b9', 'Land', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_definitions VALUES ('495f251c-83a5-4025-a307-1925712c9d0b', 'MembershipDetails', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_definitions VALUES ('4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb', 'Livestock', '493153d5-07ef-4743-8efd-07f4099772b9');
INSERT INTO g2p_register_definitions VALUES ('52979fdd-220c-48dd-8de0-0a434e786427', 'HouseholdMember', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_definitions VALUES ('5fa096f8-ffdc-4b0a-ab16-9ca386c23310', 'Crop', '493153d5-07ef-4743-8efd-07f4099772b9');
INSERT INTO g2p_register_definitions VALUES ('9055ab43-c85d-4833-bd00-ca657bb72644', 'Household', NULL);
INSERT INTO g2p_register_definitions VALUES ('a1a4d25a-1cd4-4356-abac-638239923092', 'Score', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_definitions VALUES ('a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'Farmer', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_definitions VALUES ('c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f', 'FarmerPhone', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('01425f4e-720e-4a4e-a0db-73f371ae2a07', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('58bc5e1c-1c5c-4bb5-aa5f-849755520112', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('bc882922-9008-4902-8f4f-98db0fa8f9ad', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('cd6b6b51-1a12-413f-a20a-a70fa83e0ca1', '9055ab43-c85d-4833-bd00-ca657bb72644', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_sections VALUES ('farmer_crop_crop_details_intake_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '5fa096f8-ffdc-4b0a-ab16-9ca386c23310');
INSERT INTO g2p_register_sections VALUES ('farmer_crop_crop_details_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '5fa096f8-ffdc-4b0a-ab16-9ca386c23310');
INSERT INTO g2p_register_sections VALUES ('farmer_crops', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '5fa096f8-ffdc-4b0a-ab16-9ca386c23310');
INSERT INTO g2p_register_sections VALUES ('farmer_crops_intake', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '5fa096f8-ffdc-4b0a-ab16-9ca386c23310');
INSERT INTO g2p_register_sections VALUES ('farmer_documents', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_email', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_enumerator', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_farm_farm_details_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '493153d5-07ef-4743-8efd-07f4099772b9');
INSERT INTO g2p_register_sections VALUES ('farmer_farm_input_farm_input_details_intake_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '18df8370-3e9a-493f-aa27-fc1b9e05629c');
INSERT INTO g2p_register_sections VALUES ('farmer_farm_input_farm_input_details_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '18df8370-3e9a-493f-aa27-fc1b9e05629c');
INSERT INTO g2p_register_sections VALUES ('farmer_farm_inputs', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '18df8370-3e9a-493f-aa27-fc1b9e05629c');
INSERT INTO g2p_register_sections VALUES ('farmer_farm_inputs_intake', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '18df8370-3e9a-493f-aa27-fc1b9e05629c');
INSERT INTO g2p_register_sections VALUES ('farmer_farmer_location_section_03', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_farmer_personal_identification_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_farmer_socio_economic_and_health_section_04', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_header', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_household_household_information_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_sections VALUES ('farmer_household_household_member_section_02', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '52979fdd-220c-48dd-8de0-0a434e786427');
INSERT INTO g2p_register_sections VALUES ('farmer_household_location_section_03', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_sections VALUES ('farmer_household_lookup', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_household_lookup_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_identity', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_identity_verification', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_land_summary', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_lands', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '493153d5-07ef-4743-8efd-07f4099772b9');
INSERT INTO g2p_register_sections VALUES ('farmer_livestock', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb');
INSERT INTO g2p_register_sections VALUES ('farmer_livestock_intake', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb');
INSERT INTO g2p_register_sections VALUES ('farmer_livestock_livestock_details_intake_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb');
INSERT INTO g2p_register_sections VALUES ('farmer_livestock_livestock_details_section_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb');
INSERT INTO g2p_register_sections VALUES ('farmer_location', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_membership', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '495f251c-83a5-4025-a307-1925712c9d0b');
INSERT INTO g2p_register_sections VALUES ('farmer_membership_membership_details_01', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', '495f251c-83a5-4025-a307-1925712c9d0b');
INSERT INTO g2p_register_sections VALUES ('farmer_personal_details', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_phones', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'c4f1d8e2-7a9b-4c5d-8e6f-1a2b3c4d5e6f');
INSERT INTO g2p_register_sections VALUES ('farmer_photo', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('farmer_socio_economic_health', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('household_computation_score', '9055ab43-c85d-4833-bd00-ca657bb72644', 'a1a4d25a-1cd4-4356-abac-638239923092');
INSERT INTO g2p_register_sections VALUES ('household_farmer_location_section_03', '9055ab43-c85d-4833-bd00-ca657bb72644', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('household_farmer_personal_identification_section_01', '9055ab43-c85d-4833-bd00-ca657bb72644', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('household_farmer_socio_economic_and_health_section_04', '9055ab43-c85d-4833-bd00-ca657bb72644', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd');
INSERT INTO g2p_register_sections VALUES ('household_household_household_information_section_01', '9055ab43-c85d-4833-bd00-ca657bb72644', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_sections VALUES ('household_household_household_member_section_02', '9055ab43-c85d-4833-bd00-ca657bb72644', '52979fdd-220c-48dd-8de0-0a434e786427');
INSERT INTO g2p_register_sections VALUES ('household_household_location_section_03', '9055ab43-c85d-4833-bd00-ca657bb72644', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_sections VALUES ('household_information', '9055ab43-c85d-4833-bd00-ca657bb72644', '9055ab43-c85d-4833-bd00-ca657bb72644');
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_crop_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 20);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_farm_input_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 30);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_farmer_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 0);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_household_link_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 2);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_land_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 15);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_livestock_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 25);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_membership_tab', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 10);
INSERT INTO g2p_register_ui_tabs VALUES ('farmer_tab_enumerator', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 40);
INSERT INTO g2p_register_ui_tabs VALUES ('household_farmer_tab', '9055ab43-c85d-4833-bd00-ca657bb72644', 2);
INSERT INTO g2p_register_ui_tabs VALUES ('household_household_tab', '9055ab43-c85d-4833-bd00-ca657bb72644', 1);
INSERT INTO g2p_register_ui_tab_sections VALUES ('1870bfd6-b5f9-4193-a65f-2765c7ea672c', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_farmer_tab', 'household_farmer_location_section_03', 30);
INSERT INTO g2p_register_ui_tab_sections VALUES ('2e92dcf7-17de-4f38-bddc-e9bd0d3a7081', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_household_tab', 'cd6b6b51-1a12-413f-a20a-a70fa83e0ca1', 5);
INSERT INTO g2p_register_ui_tab_sections VALUES ('a8cdc033-0228-425c-bae6-b8063086252c', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_household_tab', 'household_household_household_member_section_02', 30);
INSERT INTO g2p_register_ui_tab_sections VALUES ('a92a052c-d439-4809-9f30-df1465f667e4', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_farmer_tab', 'household_farmer_socio_economic_and_health_section_04', 20);
INSERT INTO g2p_register_ui_tab_sections VALUES ('beeb3463-cf42-48ec-ba4d-edf4bebf1933', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_farmer_tab', 'household_farmer_personal_identification_section_01', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('c3d4e5f6-a7b8-4901-c234-567890abcdef', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_household_tab', 'household_household_location_section_03', 20);
INSERT INTO g2p_register_ui_tab_sections VALUES ('f6ee19da-f32c-4a7b-8f5d-01f7af3edd92', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_household_tab', 'household_computation_score', 15);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_crop_tab__farmer_crops', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_crop_tab', 'farmer_crops', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farm_input_tab__farmer_farm_inputs', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farm_input_tab', 'farmer_farm_inputs', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_documents', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_documents', 35);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_email', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_email', 15);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_header', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_header', 5);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_identity', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_identity', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_identity_verification', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_identity_verification', 11);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_location', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_location', 19);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_personal_details', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_personal_details', 12);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_phones', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_phones', 14);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_farmer_tab__farmer_socio_economic_health', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_farmer_tab', 'farmer_socio_economic_health', 20);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_household_link_tab__farmer_household_lookup', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_household_link_tab', 'farmer_household_lookup', 1);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_land_tab__farmer_land_summary', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_land_tab', 'farmer_land_summary', 5);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_land_tab__farmer_lands', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_land_tab', 'farmer_lands', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_livestock_tab__farmer_livestock', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_livestock_tab', 'farmer_livestock', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_membership_tab__farmer_membership', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_membership_tab', 'farmer_membership', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('farmer_tab_enumerator__farmer_enumerator', 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd', 'farmer_tab_enumerator', 'farmer_enumerator', 10);
INSERT INTO g2p_register_ui_tab_sections VALUES ('household_household_tab__household_information', '9055ab43-c85d-4833-bd00-ca657bb72644', 'household_household_tab', 'household_information', 10);
