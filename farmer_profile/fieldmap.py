"""What happens to every farmer profile field, and where every Gen2 column comes from.

This is the field report's source of truth (report.py). The farmer profile
side is discovered from Odoo at run time (inventory.py), so a field this map
does not name still appears, as "Not reviewed", and the Gen2 side is read
from the registry's models, so a Gen2 column this map does not name appears
as "Not in farmer profile". transform.py does the work; keep the two in step
(tests/test_fieldmap.py checks every Gen2 column named here exists).
"""

# -- statuses of a farmer profile field ---------------------------------------------------
MIGRATED = "Migrated"                      # its value is carried to a Gen2 column
RECOMPUTED = "Recomputed in Gen2"          # Gen2 computes it again from migrated data
NOT_YET = "Not migrated yet"               # Gen2 has a column; this migration does not write it yet
NO_COLUMN = "No Gen2 column"               # cannot be added: Gen2 has nowhere to put it
WORKFLOW = "Not carried: Odoo workflow"    # the old system's review, change-request, consent or sharing state
TECHNICAL = "Odoo technical"               # Odoo bookkeeping, not farmer data
UNREVIEWED = "Not reviewed"                # a field this map does not know yet: review it

SOURCE_STATUSES = [MIGRATED, RECOMPUTED, NOT_YET, NO_COLUMN, WORKFLOW, TECHNICAL, UNREVIEWED]

# -- statuses of a Gen2 column ------------------------------------------------------------
FILLED = "Filled from farmer profile"
DERIVED = "Derived during migration"
AFTER = "Generated after the load"
REGISTRY = "Set by the registry"
T_NOT_YET = "Not migrated yet"
ABSENT = "Not in farmer profile"

TARGET_STATUSES = [FILLED, DERIVED, AFTER, REGISTRY, T_NOT_YET, ABSENT]

# The Gen2 registers in the migration's scope, parents first
REGISTERS = ["Household", "Farmer", "HouseholdMember", "FarmerPhone", "Land", "Crop",
             "Livestock", "FarmInputs", "MembershipDetails"]
WRITTEN = {"Household", "Farmer", "HouseholdMember", "FarmerPhone", "Land", "Crop"}

# The farmer profile (Odoo) models read, with the rows that count as in scope
SOURCE_MODELS = {
    "res.partner": "farmers in scope",
    "g2p.group.membership": "memberships of those farmers",
    "g2p.reg.id": "ids of those farmers",
    "g2p.phone.number": "phone numbers of those farmers",
    "g2p.land.information": "lands of those farmers",
    "g2p.crop.information": "crops of those farmers",
    "g2p.livestock.information": "livestock of those farmers",
    "g2p.enumerator": "enumerators of those farmers",
}

# Modules whose fields are Odoo's own, unless named below
ODOO_MODULES = {"base", "mail", "account", "website", "auth_signup", "contacts", "portal", "sms", "bus",
                "phone_validation", "base_setup", "web", "snailmail", "partner_autocomplete", "product",
                "base_geolocalize", "utm", "payment", "digest", "resource", "hr", "calendar"}

# model | field | status | Gen2 columns (Register.column, comma separated) | how
_SOURCE = """
res.partner | given_name | M | Farmer.first_name, HouseholdMember.first_name |
res.partner | family_name | M | Farmer.middle_name, HouseholdMember.middle_name | the father's name
res.partner | gf_name_eng | M | Farmer.last_name, HouseholdMember.last_name | the grandfather's name
res.partner | first_name_amh | M | Farmer.first_name_local | Amharic names, language_spoken = AMHARIC
res.partner | family_name_amh | M | Farmer.middle_name_local |
res.partner | gf_name_amh | M | Farmer.last_name_local |
res.partner | first_name_other | M | Farmer.first_name_local | when there are no Amharic names (else reported, dropped); language_spoken = the primary language
res.partner | family_name_other | M | Farmer.middle_name_local |
res.partner | gf_name_other | M | Farmer.last_name_local |
res.partner | primary_Language | M | Farmer.local_language, Farmer.language_spoken | through the LANGUAGE code list
res.partner | gender | M | Farmer.gender, HouseholdMember.gender | GENDER code list
res.partner | birthdate | M | Farmer.birth_date, HouseholdMember.birth_date |
res.partner | birthdate_ec | R | Farmer.birth_date_ec, HouseholdMember.birth_date_ec | computed again from birthdate
res.partner | age | R | | computed by Odoo, not stored
res.partner | age_int | M | Farmer.estimated_age |
res.partner | martial_status | M | Farmer.marital_status | MARITAL_STATUS code list
res.partner | education | M | Farmer.education_level | EDUCATION_LEVEL code list
res.partner | is_disabled | M | Farmer.disabled, HouseholdMember.is_disabled | yes/no
res.partner | farming_type | M | Farmer.farming_type | FARMING_TYPE code list
res.partner | has_personal_phone | M | Farmer.has_personal_phone | yes/no
res.partner | has_national_id | M | Farmer.has_national_id | yes/no; empty: whether a FIN or FAN is there
res.partner | hh_is_household_head | M | Farmer.is_household_head | yes/no; also picks the head when the membership does not say
res.partner | is_psnp_user | M | Farmer.is_psnp_user |
res.partner | is_farmer | M | Farmer.is_farmer | yes/no; empty: yes
res.partner | occupation | M | Farmer.occupation |
res.partner | address | M | Farmer.address_line_1 |
res.partner | email | M | Farmer.email |
res.partner | registration_date | M | Farmer.registration_date |
res.partner | partner_latitude | M | Farmer.latitude |
res.partner | partner_longitude | M | Farmer.longitude |
res.partner | farmer_id | M | Farmer.functional_record_id | when empty the registry allocates one after the load
res.partner | state | M | Farmer.legacy_state | every state is migrated; the record is ACTIVE unless disabled
res.partner | rejection_reason | M | Farmer.record_status_reason |
res.partner | disabled | M | Farmer.record_status | a disabled farmer is INACTIVE
res.partner | disabled_reason | M | Farmer.record_status_reason | for a disabled farmer
res.partner | disabled_by | N | | who disabled the farmer
res.partner | odk_instance_id | M | Farmer.odk_instance_id |
res.partner | is_duplicated | M | Farmer.is_duplicated |
res.partner | rec_import_source | M | Farmer.import_source | the source's name
res.partner | region | M | Farmer.region_name, Farmer.geo_code_hierarchy_json, Household.geo_code_hierarchy_json | P-code through the pack's id_map.csv
res.partner | zone | M | Farmer.zone_name, Farmer.geo_code_hierarchy_json, Household.geo_code_hierarchy_json |
res.partner | woreda | M | Farmer.woreda_name, Farmer.geo_code_hierarchy_json, Household.geo_code_hierarchy_json |
res.partner | kebele | M | Farmer.kebele_name, Farmer.geo_lowest_level_value_id, Household.geo_lowest_level_value_id | an unmapped kebele falls back to its woreda (reported)
res.partner | hh_income_type | M | Farmer.income_sources, Farmer.source_of_income, Farmer.source_of_income_other | SOURCE_OF_INCOME code list; unmapped names go to source_of_income_other
res.partner | additional_g2p_info | M | Farmer.source_of_income_other, Farmer.kebele_name, Farmer.woreda_name | the ODK form's free-text answers: income, kebele and woreda kept; the rest reported, dropped
res.partner | enumerator_id | M | Farmer.enumerator_name, Farmer.enumerator_user_id, Farmer.data_collection_date | see g2p.enumerator
res.partner | eid | N | | enumerator_user_id comes from the enumerator record
res.partner | size_of_family | M | Household.size_of_group | the head's answer; empty: the members counted
res.partner | number_of_children_in_family | M | Household.number_of_children | the head's answer
res.partner | number_of_males_in_family | M | Household.number_of_male_members | the head's answer
res.partner | number_of_females_in_family | M | Household.number_of_female_members | the head's answer
res.partner | other_family_member_own_land | M | Household.other_land_owner | the head's answer, yes/no
res.partner | other_farmer_in_hh | M | Household.other_farmer_in_household | the head's answer, yes/no
res.partner | father_included | M | Household.father_included | the head's answer
res.partner | mother_included | M | Household.mother_included | the head's answer
res.partner | total_land_area | R | Farmer.total_land_area | summed again from the migrated lands
res.partner | total_land_owned_area | R | Farmer.total_land_owned_area | summed again from the migrated lands
res.partner | total_land_rent_area | R | Farmer.total_land_rent_area | summed again from the migrated lands
res.partner | total_land_crop_sharing_area | R | Farmer.total_land_crop_sharing_area | summed again from the migrated lands
res.partner | land_ownership | R | Farmer.land_ownership | from the migrated lands
res.partner | name | R | Farmer.record_name, Household.household_head | the registry names the record
res.partner | create_date | M | Farmer.created_at |
res.partner | write_date | M | Farmer.last_approved_at |
res.partner | land_information_ids | M | Land.link_internal_record_id | the farmer's lands, see g2p.land.information
res.partner | crop_information_ids | M | Crop.link_internal_record_id | the farmer's crops, see g2p.crop.information
res.partner | phone_number_ids | M | FarmerPhone.link_internal_record_id | see g2p.phone.number
res.partner | reg_ids | M | Farmer.foundational_id | see g2p.reg.id
res.partner | individual_membership_ids | M | HouseholdMember.link_internal_record_id, Farmer.link_internal_record_id | see g2p.group.membership
res.partner | livestock_information_ids | Y | Livestock.link_internal_record_id | see g2p.livestock.information
res.partner | do_you_use_fertilizer | Y | FarmInputs.fertilizer_use |
res.partner | do_you_use_pesticide | Y | FarmInputs.pesticide_use |
res.partner | do_you_use_insecticide | Y | FarmInputs.insecticide_use |
res.partner | do_you_use_improved_seed | Y | FarmInputs.improved_seed_use |
res.partner | amount_fertilizer_utilized | Y | FarmInputs.amount_fertilizer_utilized |
res.partner | amount_pesticide_utilized | Y | FarmInputs.amount_pesticide_utilized |
res.partner | amount_insecticide_utilized | Y | FarmInputs.amount_insecticide_utilized |
res.partner | amount_improved_seed_utilized | Y | FarmInputs.amount_improved_seed_utilized |
res.partner | crop_water_sources | Y | FarmInputs.water_sources |
res.partner | livestock_water_sources | Y | FarmInputs.livestock_water_sources |
res.partner | access_to_machinery | Y | FarmInputs.access_to_machinery |
res.partner | type_of_machinery | Y | FarmInputs.machinery_types |
res.partner | irrigation_types | Y | FarmInputs.irrigation_type |
res.partner | has_finance_access | Y | FarmInputs.access_to_finance |
res.partner | finance_accesses | Y | FarmInputs.finance_access_types |
res.partner | is_member_of_primary_cooperative | Y | MembershipDetails.is_primary_cooperative_member |
res.partner | primary_cooperatives | Y | MembershipDetails.primary_cooperative_name |
res.partner | is_member_of_cooperative_union | Y | MembershipDetails.is_cooperative_union_member |
res.partner | cooperative_unions | Y | MembershipDetails.cooperative_union_name |
res.partner | is_member_in_farmer_cluster | Y | MembershipDetails.is_farmer_cluster_member |
res.partner | role_in_farmer_cluster | Y | MembershipDetails.farmer_cluster_role |
res.partner | primary_commodity | Y | MembershipDetails.primary_commodity |
res.partner | supporting_documents_ids | Y | Farmer.record_image_document_id | documents and the photo are files: a separate step
res.partner | image_1920 | Y | Farmer.record_image_document_id | the photo; a separate step with the documents
res.partner | phone | Y | FarmerPhone.phone_number | farmer profile keeps numbers in g2p.phone.number
res.partner | mobile | Y | FarmerPhone.phone_number | farmer profile keeps numbers in g2p.phone.number
res.partner | civil_status | N | |
res.partner | income | N | |
res.partner | district | N | |
res.partner | addl_name | N | |
res.partner | birth_place | N | |
res.partner | birthdate_not_exact | N | |
res.partner | tags_ids | N | |
res.partner | unique_id | N | |
res.partner | related_1_ids | N | | relationships between registrants
res.partner | related_2_ids | N | | relationships between registrants
res.partner | language_skills | N | |
res.partner | service_ids | N | | API service records
res.partner | message_ids | N | | Odoo chatter: notes and field-change tracking; Gen2 history starts at the migration
res.partner | is_registrant | T | | selects the farmers
res.partner | is_group | T | | selects the farmers
res.partner | active | T | | selects the farmers: archived ones are not migrated
res.partner | kind | T | | household groups
res.partner | is_partial_group | T | |
res.partner | z_ind_grp_num_individuals | T | |
res.partner | force_recompute_canary | T | |
res.partner | company_id | T | |
res.partner | group_membership_ids | T | | a group's side of the membership
res.partner | odk_app_user | T | |
res.partner | odk_config_id | T | |
res.partner | db_import | T | |
res.partner | imported_record_state | T | |
res.partner | source | T | | import bookkeeping
res.partner | source_db_ids | T | | import bookkeeping
res.partner | is_orphan | T | | import bookkeeping
res.partner | asigned_region | T | | portal users
res.partner | websub_last_shared_at | W | | data sharing
res.partner | websub_sent_at | W | | data sharing
res.partner | websub_share_status_ids | W | | data sharing
res.partner | approval_status | W | | change requests
res.partner | edit_count | W | | change requests
res.partner | edit_state | W | | change requests
res.partner | edit_suggestion_ids | W | | change requests
res.partner | update_request_ids | W | | change requests
res.partner | validation_status | W | | farmer review
res.partner | review_note | W | | farmer review
res.partner | review_comments | W | | farmer review
res.partner | review_identity_ids | W | | farmer review
res.partner | review_location_ids | W | | farmer review
res.partner | review_national_id_ids | W | | farmer review
res.partner | review_coordinates_ids | W | | farmer review
res.partner | review_socio_economic_ids | W | | farmer review
res.partner | review_farming_ids | W | | farmer review
res.partner | review_enumerator_ids | W | | farmer review
res.partner | review_household_ids | W | | farmer review
res.partner | review_phone_ids | W | | farmer review
res.partner | is_consent_parent | W | | consent management
res.partner | consent_websub_config_id | W | | consent management
res.partner | allowed_data_field_ids | W | | consent management
res.partner | consent_portal_role_ids | W | | consent management
res.partner | consent_portal_user_ids | W | | consent management
res.partner | consent_receipt_ids | W | | consent management
res.partner | consent_request_ids | W | | consent management

g2p.group.membership | group | M | HouseholdMember.link_internal_record_id, Farmer.link_internal_record_id | the household
g2p.group.membership | individual | M | HouseholdMember.first_name | the member's names and details come from the farmer
g2p.group.membership | kind | M | HouseholdMember.relationship_to_the_head, HouseholdMember.is_head | Head: SELF; Wife/Husband - Head: SPOUSE; else OTHER_RELATIVE
g2p.group.membership | is_ended | M | | ended memberships are not migrated
g2p.group.membership | status | N | |
g2p.group.membership | start_date | N | |
g2p.group.membership | ended_date | N | | ended memberships are not migrated
g2p.group.membership | create_date | M | HouseholdMember.created_at | the farmer's dates
g2p.group.membership | write_date | M | HouseholdMember.last_approved_at | the farmer's dates

g2p.reg.id | partner_id | M | Farmer.foundational_id |
g2p.reg.id | id_type | M | Farmer.foundational_id, Farmer.rid, Farmer.odk_farmer_id, HouseholdMember.odk_member_id | UID (FIN) else FAN: foundational_id; RID: rid; ODK ack ids
g2p.reg.id | value | M | Farmer.foundational_id, Farmer.rid, Farmer.odk_farmer_id, HouseholdMember.odk_member_id |
g2p.reg.id | status | N | | an id's status has no column (README)
g2p.reg.id | expiry_date | N | | an id's expiry has no column (README)
g2p.reg.id | description | N | |
g2p.reg.id | fayda_processed | T | | Fayda connector bookkeeping
g2p.reg.id | fayda_response_status | T | | Fayda connector bookkeeping

g2p.phone.number | partner_id | M | FarmerPhone.link_internal_record_id |
g2p.phone.number | phone_no | M | FarmerPhone.phone_number | normalized; duplicates of a farmer dropped
g2p.phone.number | phone_type | M | FarmerPhone.phone_type, FarmerPhone.is_primary | PHONE_NUMBER_TYPE; one primary per farmer
g2p.phone.number | phone_sanitized | R | FarmerPhone.phone_e164 | from phone_no
g2p.phone.number | country_id | M | FarmerPhone.country_code | ET
g2p.phone.number | disabled | M | | disabled numbers are not migrated
g2p.phone.number | disabled_by | N | |
g2p.phone.number | date_collected | N | |
g2p.phone.number | create_date | M | FarmerPhone.created_at |
g2p.phone.number | write_date | M | FarmerPhone.last_approved_at |

g2p.land.information | partner_id | M | Land.link_internal_record_id |
g2p.land.information | land_id | M | Land.land_id |
g2p.land.information | ownership_type | M | Land.land_ownership_type | LAND_OWNERSHIP_TYPE
g2p.land.information | total_land_area | M | Land.land_size, Land.area_in_hectare | unit HECTARE
g2p.land.information | certficate_provided | M | Land.certificate_provided |
g2p.land.information | year_of_acquisition | M | Land.year_of_acquisition | the year
g2p.land.information | polygon_data | M | Land.shape_coordinates_json, Land.shape_type | GeoJSON Polygon, [lon, lat], closed
g2p.land.information | current_land_use | M | Land.current_land_use | CURRENT_LAND_USE
g2p.land.information | soil_fertility | M | Land.soil_fertility |
g2p.land.information | means_of_acquisition | M | Land.means_of_acquisition |
g2p.land.information | remark | M | Land.remark |
g2p.land.information | land_kebele | M | Land.land_kebele | P-code
g2p.land.information | land_certificate | Y | Land.certificate_storage_id | a file: a separate step with the documents
g2p.land.information | create_date | M | Land.created_at |
g2p.land.information | write_date | M | Land.last_approved_at |
g2p.land.information | integration_status | T | |
g2p.land.information | reviewed_by | W | | farmer review
g2p.land.information | is_reviewed | W | | farmer review
g2p.land.information | reviewed_on | W | | farmer review
g2p.land.information | review_tag_ids | W | | farmer review
g2p.land.information | review_remark_ids | W | | farmer review

g2p.crop.information | partner_id | M | Crop.link_internal_record_id | on the farmer's first land: farmer profile does not say which (reported)
g2p.crop.information | crop | M | Crop.commodity | CROP_COMMODITY
g2p.crop.information | season | M | Crop.season | CROP_SEASON
g2p.crop.information | collected_gc | M | Crop.planted_date |
g2p.crop.information | collected_ec | M | Crop.planted_date_ec | computed from collected_gc when empty
g2p.crop.information | is_diseased | M | Crop.is_diseased | yes/no
g2p.crop.information | illness_type | M | Crop.disease_type |
g2p.crop.information | create_date | M | Crop.created_at |
g2p.crop.information | write_date | M | Crop.last_approved_at |

g2p.livestock.information | partner_id | Y | Livestock.link_internal_record_id |
g2p.livestock.information | livestock_type | Y | Livestock.livestock_type |
g2p.livestock.information | number_of_livestock | Y | Livestock.head_count |
g2p.livestock.information | season | Y | Livestock.season |
g2p.livestock.information | collected_gc | Y | Livestock.collected_date |
g2p.livestock.information | collected_ec | Y | Livestock.collected_date_ec |
g2p.livestock.information | is_diseased | Y | Livestock.is_diseased |
g2p.livestock.information | illness_type | Y | Livestock.disease_type |
g2p.livestock.information | create_date | Y | Livestock.created_at |
g2p.livestock.information | write_date | Y | Livestock.last_approved_at |

g2p.enumerator | name | M | Farmer.enumerator_name |
g2p.enumerator | enumerator_user_id | M | Farmer.enumerator_user_id |
g2p.enumerator | data_collection_date | M | Farmer.data_collection_date |
g2p.enumerator | enum_latitude | M | Farmer.enumerator_latitude |
g2p.enumerator | enum_longitude | M | Farmer.enumerator_longitude |
g2p.enumerator | enum_altitude | M | Farmer.enumerator_altitude |
g2p.enumerator | enum_accuracy | M | Farmer.enumerator_accuracy |
"""

_CODES = {"M": MIGRATED, "R": RECOMPUTED, "Y": NOT_YET, "N": NO_COLUMN, "W": WORKFLOW, "T": TECHNICAL}

# Odoo's bookkeeping columns on every model
COMMON_TECHNICAL = {"id", "create_uid", "write_uid", "create_date", "write_date", "__last_update", "display_name"}


def _parse():
    out = {}
    for line in _SOURCE.strip().splitlines():
        if not line.strip():
            continue
        model, name, code, targets, how = (part.strip() for part in line.split("|"))
        out[(model, name)] = {"status": _CODES[code],
                              "targets": [t.strip() for t in targets.split(",") if t.strip()],
                              "how": how}
    return out


SOURCE = _parse()


def source_status(model, name, modules) -> dict:
    """The map's entry for an Odoo field, or a default from where it comes from."""
    if (model, name) in SOURCE:
        return SOURCE[(model, name)]
    if name in COMMON_TECHNICAL:
        return {"status": TECHNICAL, "targets": [], "how": "Odoo bookkeeping"}
    if modules and set(modules) <= ODOO_MODULES:
        return {"status": TECHNICAL, "targets": [], "how": "an Odoo field (" + ", ".join(sorted(modules)) + ")"}
    return {"status": UNREVIEWED, "targets": [], "how": ""}


# -- the Gen2 side: columns not filled straight from a farmer profile field ------------------
_EVERY_REGISTER = {
    "internal_record_id": (DERIVED, "uuid5 of the Odoo record id: the same record always gets the same id"),
    "link_internal_record_id": (DERIVED, "the parent record: household, farmer or land"),
    "created_by": (DERIVED, "farmer-profile-migration"),
    "last_approved_by": (DERIVED, "farmer-profile-migration"),
    "record_status": (DERIVED, "ACTIVE (a disabled farmer: INACTIVE)"),
    "record_name": (REGISTRY, "the registry's insert hook"),
    "search_text": (REGISTRY, "the registry's insert hook"),
    "country_code": (DERIVED, "ET"),
    "geo_code_hierarchy_json": (DERIVED, "built from the P-code with the pack's levels and values"),
}

TARGET = {
    ("Farmer", "functional_record_id"): (AFTER, "farmer profile's farmer_id when there is one; else the registry's "
                                                "ID worker allocates it from the queue the migration fills at the end"),
    ("Household", "functional_record_id"): (AFTER, "the registry's ID worker allocates it from the queue the "
                                                   "migration fills at the end"),
    ("Farmer", "birth_date_ec"): (DERIVED, "birth_date in the Ethiopian calendar"),
    ("HouseholdMember", "birth_date_ec"): (DERIVED, "birth_date in the Ethiopian calendar"),
    ("Farmer", "phone_numbers"): (DERIVED, "the farmer's migrated phone numbers"),
    ("Farmer", "total_land_area"): (DERIVED, "the sum of the farmer's migrated lands"),
    ("Farmer", "total_land_owned_area"): (DERIVED, "the sum of the farmer's migrated lands"),
    ("Farmer", "total_land_rent_area"): (DERIVED, "the sum of the farmer's migrated lands"),
    ("Farmer", "total_land_crop_sharing_area"): (DERIVED, "the sum of the farmer's migrated lands"),
    ("Farmer", "land_ownership"): (DERIVED, "from the farmer's migrated lands"),
    ("Household", "household_head"): (DERIVED, "the head member's name"),
    ("HouseholdMember", "is_head"): (DERIVED, "from the membership kind"),
    ("Land", "unit"): (DERIVED, "HECTARE: farmer profile keeps hectares"),
    ("Land", "area_in_hectare"): (DERIVED, "land_size in hectares"),
    ("FarmerPhone", "phone_e164"): (DERIVED, "from the number"),
    ("FarmerPhone", "is_primary"): (DERIVED, "one primary number per farmer"),
    ("Crop", "planted_date_ec"): (DERIVED, "collected_ec, else planted_date in the Ethiopian calendar"),
}

# Produced after the rows are written: what the registry does for an approved record
AFTER_LOAD = [
    ("Functional ids (Farmer, Household)", "g2p_functional_id_generation_queue",
     "queued at the end of the migration for records without one; the registry's ID worker allocates them"),
    ("Completion scores (Farmer)", "g2p_completion_score_computation_queue",
     "queued at the end of the migration, one row per section; the registry's score worker computes them"),
    ("Record history", "g2p_register_history_*", "not written yet: a migrated record's history starts empty"),
]


def target_status(register, column, filled_from: list) -> tuple[str, str]:
    if register not in WRITTEN:
        return T_NOT_YET, "this register is not migrated yet"
    if (register, column) in TARGET:
        return TARGET[(register, column)]
    if column in _EVERY_REGISTER:
        return _EVERY_REGISTER[column]
    if filled_from:
        status = FILLED if any(SOURCE[s]["status"] == MIGRATED for s in filled_from) else (
            T_NOT_YET if any(SOURCE[s]["status"] == NOT_YET for s in filled_from) else DERIVED)
        return status, ""
    return ABSENT, "stays empty"


def sources_of(register, column) -> list:
    return [key for key, entry in SOURCE.items() if f"{register}.{column}" in entry["targets"]]
