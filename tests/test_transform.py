"""The transform on hand-made farmer profile rows: no database."""
from datetime import date, datetime

import pytest

from farmer_profile import fieldmap as F


@pytest.fixture(scope="module")
def transformer(models, pack_root):
    from farmer_profile.codes import PackCodes
    from farmer_profile.geo import Geo
    from farmer_profile.transform import Transformer
    return Transformer(PackCodes(pack_root), Geo(pack_root))


def farmer(id_, **kw):
    row = dict.fromkeys(
        "given_name family_name gf_name_eng first_name_amh family_name_amh gf_name_amh first_name_other "
        "family_name_other gf_name_other gender birthdate age_int martial_status education is_disabled farming_type "
        "has_personal_phone has_national_id hh_is_household_head is_psnp_user email registration_date partner_latitude "
        "partner_longitude farmer_id state rejection_reason odk_instance_id is_duplicated size_of_family "
        "number_of_children_in_family number_of_males_in_family number_of_females_in_family "
        "other_family_member_own_land other_farmer_in_hh father_included mother_included is_farmer occupation address "
        "disabled disabled_reason additional_g2p_info enumerator_name enumerator_user_id data_collection_date "
        "enum_latitude enum_longitude enum_altitude enum_accuracy language import_source region_code region_name "
        "zone_code zone_name woreda_code woreda_name kebele_code kebele_name".split())
    row.update(id=id_, given_name="Abebe", family_name="Kebede", gf_name_eng="Tola", gender="male",
               birthdate=date(1980, 1, 1), create_date=datetime(2025, 1, 1), write_date=datetime(2025, 2, 1))
    row.update(kw)
    return row


def data(farmers, **kw):
    out = {"farmers": farmers, "households": [], "memberships": [], "ids": [], "incomes": [], "phones": [],
           "lands": [], "crops": []}
    out.update(kw)
    return out


def phone(id_, partner, number, kind=None, disabled=None):
    return {"id": id_, "partner_id": partner, "phone_no": number, "phone_type": kind, "disabled": disabled,
            "create_date": datetime(2025, 1, 1), "write_date": datetime(2025, 1, 1)}


def test_farmer_alone_gets_a_household_and_names(transformer):
    out = transformer(data([farmer(1)]))
    f = out.farmers[0]
    assert (f["first_name"], f["middle_name"], f["last_name"]) == ("Abebe", "Kebede", "Tola")
    assert f["gender"] == "MALE" and f["record_status"] == "ACTIVE"
    assert len(out.households) == 1 and out.members[0]["is_head"] and out.members[0]["relationship_to_the_head"] == "SELF"
    assert f["link_internal_record_id"] == out.households[0]["internal_record_id"]
    assert any(i.field == "household" for i in out.issues)


def test_other_language_names_used_when_no_amharic(transformer):
    f = transformer(data([farmer(1, first_name_other="Caalaa", language="Afaan Oromoo")])).farmers[0]
    assert f["first_name_local"] == "Caalaa" and f["language_spoken"] == "AFAAN_OROMO"
    f = transformer(data([farmer(1, first_name_amh="አበበ", first_name_other="Caalaa")])).farmers[0]
    assert f["first_name_local"] == "አበበ" and f["language_spoken"] == "AMHARIC"


def test_disabled_farmer_is_inactive(transformer):
    f = transformer(data([farmer(1, disabled=datetime(2025, 3, 1), disabled_reason="dead")])).farmers[0]
    assert f["record_status"] == "INACTIVE" and f["record_status_reason"] == "dead"


def test_phones_one_primary_no_duplicates_no_disabled(transformer):
    out = transformer(data([farmer(1)], phones=[
        phone(1, 1, "0911000001", "secondary"), phone(2, 1, "+251911000002", "primary"),
        phone(3, 1, "911000001", "other"), phone(4, 1, "0911000003", disabled=datetime(2025, 1, 1))]))
    assert [(p["phone_number"][-4:], p["phone_type"], p["is_primary"]) for p in out.phones] == \
        [("0002", "PRIMARY", True), ("0001", "SECONDARY", False)]
    assert any(i.reason.startswith("the farmer has this number") for i in out.issues)


def land(id_, partner, **kw):
    row = dict(id=id_, partner_id=partner, land_id=f"L{id_}", ownership_type="owner", total_land_area=1.5,
               certficate_provided=None, year_of_acquisition=None, polygon_data=None, current_land_use=None,
               soil_fertility=None, means_of_acquisition=None, remark=None, kebele_code=None,
               create_date=datetime(2025, 1, 1), write_date=datetime(2025, 1, 1))
    row.update(kw)
    return row


def test_land_codes_and_shape(transformer):
    out = transformer(data([farmer(1)], lands=[land(1, 1, means_of_acquisition="Rent", soil_fertility="High",
                                                    polygon_data="[[9.0, 38.0], [9.1, 38.0], [9.1, 38.1]]")]))
    l = out.lands[0]
    assert l["means_of_acquisition"] == "MOA_RENTING_LEASING" and l["soil_fertility"] == "SF_HIGH"
    assert l["shape_coordinates_json"]["coordinates"][0][0] == [38.0, 9.0]
    assert l["shape_coordinates_json"]["coordinates"][0][-1] == [38.0, 9.0]
    assert out.farmers[0]["total_land_area"] == 1.5


def crop(id_, partner, name, illnesses=None):
    return {"id": id_, "partner_id": partner, "crop": name, "season": None, "collected_gc": None,
            "collected_ec": None, "is_diseased": "yes" if illnesses else None, "illnesses": illnesses,
            "create_date": datetime(2025, 1, 1), "write_date": datetime(2025, 1, 1)}


def test_crop_disease_codes(transformer):
    out = transformer(data([farmer(1)], lands=[land(1, 1)], crops=[
        crop(1, 1, "Wheat", "Stem Rust"), crop(2, 1, "Maize", "Grey Leaf spot,MLND"), crop(3, 1, "Teff", "Smudge"),
        crop(4, 1, "Barley", "Leaf Rust")]))
    assert [c["disease_type"] for c in out.crops] == \
        ["AGENT_WHEAT_RUST", "AGENT_MAIZE_LETHAL_NECROSIS", "AGENT_OTHER", "AGENT_OTHER"]


def test_crop_without_land_is_skipped(transformer):
    out = transformer(data([farmer(1)], crops=[crop(1, 1, "Teff")]))
    assert not out.crops and out.issues[-1].severity == "skipped"


def test_ids_are_stable():
    from farmer_profile.transform import record_id
    assert record_id("farmer", 12) == record_id("farmer", 12) != record_id("land", 12)


def test_values_master_data_does_not_have_are_left_empty(models, pack_root):
    """A code or location missing from Master Data is not migrated: the field stays empty and it is reported."""
    from farmer_profile.codes import PackCodes
    from farmer_profile.geo import Geo
    from farmer_profile.masterdata import MasterData
    from farmer_profile.transform import Transformer
    master = MasterData.from_pack(pack_root)
    master.codes["MARITAL_STATUS"].discard("MARRIED")
    master.bindings = {("Farmer", "marital_status"): {"MARITAL_STATUS"},
                       ("Farmer", "income_sources"): {"SOURCE_OF_INCOME"},
                       ("Crop", "commodity"): {"CROP_COMMODITY"}}
    master.codes["SOURCE_OF_INCOME"].discard("SOI_LIVESTOCK_PRODUCTION")
    master.codes["CROP_COMMODITY"].discard("CROP_TEFF")
    t = Transformer(PackCodes(pack_root), Geo(pack_root, master.nodes), master)
    out = t(data([farmer(1, martial_status="married")], lands=[land(1, 1)], crops=[crop(1, 1, "Teff")],
                 incomes=[{"partner_id": 1, "name": "Crop Production"}, {"partner_id": 1, "name": "Livestock Production"}]))
    f = out.farmers[0]
    assert f["marital_status"] is None
    assert f["income_sources"] == ["SOI_CROP_PRODUCTION"]
    assert out.crops[0]["commodity"] is None
    dropped = {(i.field, i.value) for i in out.issues if i.reason.startswith("not in Master Data")}
    assert dropped == {("marital_status", "MARRIED"), ("income_sources", "SOI_LIVESTOCK_PRODUCTION"),
                       ("commodity", "CROP_TEFF")}


def test_location_master_data_does_not_have_falls_back_a_level(models, pack_root):
    from farmer_profile.geo import Geo
    from farmer_profile.masterdata import MasterData
    master = MasterData.from_pack(pack_root)
    full = Geo(pack_root, master.nodes)
    kebele = next(k for k in full.id_map if k.startswith("kebele-") and full.pcode("kebele", k.split("-ET")[1]))
    code = kebele.split("-ET")[1]
    pcode = full.pcode("kebele", code)
    parent = master.nodes[pcode]["parent"]
    nodes = {k: v for k, v in master.nodes.items() if k != pcode}
    geo = Geo(pack_root, nodes)
    assert geo.pcode("kebele", code) is None
    woreda_code = next(k.split("-ET")[1] for k, v in full.id_map.items() if k.startswith("woreda-") and v == parent)
    assert geo.lowest({"kebele": code, "woreda": woreda_code}) == (parent, "woreda")
