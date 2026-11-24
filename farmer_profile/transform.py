"""Odoo records to registry rows. Pure: no database, no network.

The field map follows the Farmer extension's README, "Migration from the
previous registries" (farmer-registry repository). Every value that cannot be carried over is recorded as an Issue
and left empty; nothing is guessed.

Record ids are uuid5 of the Odoo record, so the same Odoo record always gets
the same registry id and a rerun finds what is already migrated.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from openg2p_registry_farmer_extension.register_domain.derived import hectares, land_rollup, normalize_phone
from openg2p_registry_farmer_extension.register_domain.ethiopian_calendar import gregorian_to_ethiopic_string

from . import codes as C

NAMESPACE = uuid.UUID("5b0c7f0e-6f43-4c2e-9a39-6d0f0a7c2f11")
MIGRATED_BY = "farmer-profile-migration"
# A parcel above this many hectares is kept as is but reported
LARGE_PARCEL_HA = 100


def record_id(kind: str, odoo_id) -> str:
    return str(uuid.uuid5(NAMESPACE, f"farmer-profile/{kind}/{odoo_id}"))


@dataclass
class Issue:
    severity: str  # "skipped": not migrated; "dropped": a value left out; "check": migrated, worth a look
    entity: str
    odoo_id: object
    field: str
    value: object
    reason: str


@dataclass
class Result:
    households: list = field(default_factory=list)
    farmers: list = field(default_factory=list)
    members: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    lands: list = field(default_factory=list)
    crops: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    @classmethod
    def joined(cls, results):
        out = cls()
        for r in results:
            for name in ("households", "farmers", "members", "phones", "lands", "crops", "issues"):
                getattr(out, name).extend(getattr(r, name))
        return out

    def tables(self):
        # parents before children
        return [("Household", self.households), ("Farmer", self.farmers), ("HouseholdMember", self.members),
                ("FarmerPhone", self.phones), ("Land", self.lands), ("Crop", self.crops)]


def _base(kind, odoo_id, created, written, link=None):
    created = created or datetime.utcnow()
    return {"internal_record_id": record_id(kind, odoo_id), "link_internal_record_id": link,
            "created_by": MIGRATED_BY, "created_at": created,
            "last_approved_by": MIGRATED_BY, "last_approved_at": written or created,
            "record_status": "ACTIVE"}


def _name(*parts):
    return " ".join(str(p).strip() for p in parts if p and str(p).strip()) or None


def _key(value):
    """Free text as a code-list key: lower case, words joined by _ (as farmer profile's selections)."""
    text = str(value or "").strip().lower()
    return "_".join(text.replace("/", " ").split()) or None


def _float(value):
    return float(value) if value not in (None, "") else None


def _additional_info(text) -> dict:
    """additional_g2p_info: the free-text 'other' answers of the ODK form, a JSON
    object, sometimes stored as a JSON string of one."""
    import json
    value = text
    for _ in range(2):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return {}
    return dict(value) if isinstance(value, dict) else {}


def _ec(value):
    return gregorian_to_ethiopic_string(value) if isinstance(value, date) else None


class Transformer:
    def __init__(self, pack_codes: C.PackCodes, geo, master=None):
        """master: masterdata.MasterData. Every coded value is checked against
        it, and one it does not have is left empty and reported."""
        self.codes = pack_codes
        self.geo = geo
        self.master = master

    def __call__(self, data: dict) -> Result:
        out = Result()
        self.out = out
        ids, incomes, phones = {}, {}, {}
        for row in data["ids"]:
            ids.setdefault(row["partner_id"], {}).setdefault(row["id_type"], row["value"])
        for row in data["incomes"]:
            incomes.setdefault(row["partner_id"], []).append(row["name"])
        for row in data["phones"]:
            phones.setdefault(row["partner_id"], []).append(row)
        lands_of = {}
        for row in data["lands"]:
            lands_of.setdefault(row["partner_id"], []).append(row)
        crops_of = {}
        for row in data["crops"]:
            crops_of.setdefault(row["partner_id"], []).append(row)
        farmers = {f["id"]: f for f in data["farmers"]}
        groups = {h["id"]: h for h in data["households"]}

        # Households: Odoo groups, and one of their own for a farmer in none
        members_of = {}
        for m in data["memberships"]:
            members_of.setdefault(m["household_id"], []).append(m)
        household_of = {}
        in_households = {}
        for gid in sorted(members_of):
            for m in members_of[gid]:
                household_of.setdefault(m["farmer_id"], record_id("household", gid))
                in_households.setdefault(m["farmer_id"], []).append(gid)
        for fid, gids in in_households.items():
            if fid in farmers and len(set(gids)) > 1:
                self.issue("check", "farmer", fid, "household", ", ".join(map(str, gids)),
                           "in several households in farmer profile: linked to the lowest household id")
        for fid, farmer in farmers.items():
            if fid not in household_of:
                household_of[fid] = record_id("household", f"solo-{fid}")
                members_of[f"solo-{fid}"] = [{"id": f"solo-{fid}", "household_id": f"solo-{fid}", "farmer_id": fid,
                                              "kinds": "Head"}]
                self.issue("check", "farmer", fid, "household", None,
                           "in no household in farmer profile: given a household of their own, as its head")
                if C.yes_no(farmer["hh_is_household_head"]) is False:
                    self.issue("check", "farmer", fid, "hh_is_household_head", farmer["hh_is_household_head"],
                               "marked as not the household head, but in no household: is the head of the one given")

        for gid, memberships in members_of.items():
            self.household(gid, groups.get(gid), memberships, farmers, ids)

        for fid, farmer in farmers.items():
            farmer_row = self.farmer(farmer, household_of[fid], ids.get(fid, {}), incomes.get(fid, []))
            phone_rows = self.phones(fid, farmer_row, phones.get(fid, []))
            land_rows = self.lands(fid, farmer_row, lands_of.get(fid, []))
            self.crops(fid, land_rows, crops_of.get(fid, []))
            farmer_row.update(land_rollup((l["land_ownership_type"], l["area_in_hectare"]) for l in land_rows))
            if phone_rows:
                farmer_row["phone_numbers"] = [{"type": p["phone_type"].lower(), "number": p["phone_e164"],
                                                "is_primary": p["is_primary"]} for p in phone_rows]
            out.farmers.append(self.checked("Farmer", "farmer", fid, farmer_row))
        return out

    def checked(self, register, entity, odoo_id, row) -> dict:
        """Leave out every coded value Master Data does not have (a list keeps the values it has)."""
        if self.master is None:
            return row
        for column, value in row.items():
            allowed = self.master.allowed(register, column)
            if allowed is None or value is None or value == "" or value == []:
                continue
            lists = "/".join(sorted(self.master.bindings[(register, column)]))
            values = value if isinstance(value, list) else [value]
            missing = [v for v in values if v not in allowed]
            for v in missing:
                self.issue("dropped", entity, odoo_id, column, v, f"not in Master Data ({lists}): left empty")
            if missing:
                kept = [v for v in values if v in allowed]
                row[column] = (kept or None) if isinstance(value, list) else None
        return row

    def issue(self, severity, entity, odoo_id, field_, value, reason):
        self.out.issues.append(Issue(severity, entity, odoo_id, field_, value, reason))

    def code(self, entity, odoo_id, field_, value, table):
        result = C.lookup(table, value) if isinstance(table, dict) else table(value)
        if value not in (None, "") and result is None:
            self.issue("dropped", entity, odoo_id, field_, value, "no registry code for this value")
        return result

    def location(self, entity, odoo_id, codes: dict) -> dict:
        pcode, level = self.geo.lowest(codes)
        given = [lvl for lvl in ("kebele", "woreda", "zone", "region") if codes.get(lvl)]
        if given and pcode is None:
            self.issue("dropped", entity, odoo_id, "location", codes, "no P-code in Master Data for any level: left empty")
        elif given and level != given[0]:
            self.issue("check", entity, odoo_id, "location", codes.get(given[0]),
                       f"no P-code in Master Data for the {given[0]}: located at its {level} {pcode}")
        return {"geo_lowest_level_value_id": pcode, "geo_code_hierarchy_json": self.geo.hierarchy(pcode),
                "country_code": "ET"}

    # -- registers --------------------------------------------------------------------------

    def farmer(self, f, household_id, reg_ids, income_names) -> dict:
        fid = f["id"]
        row = _base("farmer", fid, f["create_date"], f["write_date"], link=household_id)
        extra = _additional_info(f["additional_g2p_info"])
        language = self.code("farmer", fid, "primary_Language", f["language"], self.codes.language)
        amharic = [f["first_name_amh"], f["family_name_amh"], f["gf_name_amh"]]
        other = [f["first_name_other"], f["family_name_other"], f["gf_name_other"]]
        # Gen2 keeps one set of local names: the Amharic ones, else the names in the farmer's own language
        if any(amharic):
            local, spoken = amharic, "AMHARIC"
            if any(other):
                self.issue("dropped", "farmer", fid, "first_name_other", _name(*other),
                           "names in a second local language: Gen2 keeps one set of local names (Amharic kept)")
        elif any(other):
            local, spoken = other, language
        else:
            local, spoken = [None, None, None], language
        income = [self.code("farmer", fid, "hh_income", name, C.INCOME) for name in income_names]
        others = [n for n, code in zip(income_names, income) if code is None]
        if extra.get("House Hold Income"):
            others.append(extra.pop("House Hold Income"))
        income = [c for c in income if c] + (["SOI_OTHERS"] if others and "SOI_OTHERS" not in income else [])
        foundational = reg_ids.get("UID") or reg_ids.get("FAN")
        disabled = f["disabled"] is not None
        row.update({
            "record_status": "INACTIVE" if disabled else "ACTIVE",
            "record_status_reason": (f["disabled_reason"] if disabled else None) or f["rejection_reason"],
            "functional_record_id": f["farmer_id"] or None,
            "first_name": f["given_name"], "middle_name": f["family_name"], "last_name": f["gf_name_eng"],
            "first_name_local": local[0], "middle_name_local": local[1], "last_name_local": local[2],
            "language_spoken": spoken, "local_language": language,
            "gender": self.code("farmer", fid, "gender", f["gender"], C.GENDER),
            "birth_date": f["birthdate"], "birth_date_ec": _ec(f["birthdate"]), "estimated_age": f["age_int"],
            "marital_status": self.code("farmer", fid, "martial_status", f["martial_status"], C.MARITAL_STATUS),
            "education_level": self.code("farmer", fid, "education", f["education"], C.EDUCATION),
            "disabled": C.yes_no(f["is_disabled"]),
            "farming_type": self.code("farmer", fid, "farming_type", f["farming_type"], C.FARMING_TYPE),
            "has_personal_phone": C.yes_no(f["has_personal_phone"]),
            "has_national_id": C.yes_no(f["has_national_id"]) if f["has_national_id"] else bool(foundational),
            "is_household_head": C.yes_no(f["hh_is_household_head"]),
            "is_psnp_user": f["is_psnp_user"],
            "is_farmer": C.yes_no(f["is_farmer"]) if f["is_farmer"] else True,
            "occupation": f["occupation"] or None, "address_line_1": f["address"] or None,
            "email": f["email"], "registration_date": f["registration_date"],
            "source_of_income": income[0] if len(income) == 1 else None,
            "income_sources": income or None,
            "source_of_income_other": ", ".join(others) or None,
            "foundational_id": foundational, "rid": reg_ids.get("RID"),
            "odk_farmer_id": reg_ids.get("Farmer ODK ACK ID"), "odk_instance_id": f["odk_instance_id"],
            "legacy_state": f["state"],
            "import_source": f["import_source"], "is_duplicated": f["is_duplicated"],
            "latitude": _float(f["partner_latitude"]), "longitude": _float(f["partner_longitude"]),
            "enumerator_name": f["enumerator_name"], "enumerator_user_id": f["enumerator_user_id"],
            "data_collection_date": f["data_collection_date"],
            "enumerator_latitude": _float(f["enum_latitude"]), "enumerator_longitude": _float(f["enum_longitude"]),
            "enumerator_altitude": _float(f["enum_altitude"]), "enumerator_accuracy": _float(f["enum_accuracy"]),
            "region_name": f["region_name"], "zone_name": f["zone_name"],
            "woreda_name": f["woreda_name"] or extra.pop("Woreda", None),
            "kebele_name": f["kebele_name"] or extra.pop("Kebele", None),
        })
        for key, value in extra.items():
            if value not in (None, ""):
                self.issue("dropped", "farmer", fid, f"additional_g2p_info.{key}", value, "free-text answer: no Gen2 column")
        if reg_ids.get("UID") and reg_ids.get("FAN"):
            self.issue("check", "farmer", fid, "foundational_id", None, "has both FIN (UID) and FAN: FIN kept")
        row.update(self.location("farmer", fid, {lvl: f[f"{lvl}_code"] for lvl in ("region", "zone", "woreda", "kebele")}))
        return row

    def household(self, gid, group, memberships, farmers, ids):
        members = [(m, farmers.get(m["farmer_id"])) for m in memberships]
        missing = [m["farmer_id"] for m, f in members if f is None]
        for fid in missing:
            self.issue("skipped", "household_member", fid, "individual", None, "member is not an active farmer")
        members = [(m, f) for m, f in members if f is not None]
        heads = [(m, f) for m, f in members if "head" in (m.get("kinds") or "").lower().split(",")]
        if len(heads) != 1:
            flagged = [(m, f) for m, f in members if C.yes_no(f["hh_is_household_head"])]
            heads = flagged[:1] if len(flagged) == 1 else members[:1]
            self.issue("check", "household", gid, "head", len(heads), "no single Head membership: head taken from "
                       + ("the farmer marked head" if len(flagged) == 1 else "the first member"))
        head_membership, head = heads[0]
        created = (group or {}).get("create_date") or head["create_date"]
        written = (group or {}).get("write_date") or head["write_date"]
        row = _base("household", gid, created, written)
        row.update({
            "household_head": _name(head["given_name"], head["family_name"], head["gf_name_eng"]),
            "size_of_group": head["size_of_family"] or len(members),
            "number_of_children": head["number_of_children_in_family"],
            "number_of_male_members": head["number_of_males_in_family"],
            "number_of_female_members": head["number_of_females_in_family"],
            "other_land_owner": C.yes_no(head["other_family_member_own_land"]),
            "other_farmer_in_household": C.yes_no(head["other_farmer_in_hh"]),
            "father_included": head["father_included"], "mother_included": head["mother_included"],
        })
        row.update(self.location("household", gid, {lvl: head[f"{lvl}_code"] for lvl in ("region", "zone", "woreda", "kebele")}))
        self.out.households.append(self.checked("Household", "household", gid, row))
        for m, f in members:
            is_head = m is head_membership
            kinds = [k for k in (m.get("kinds") or "").split(",") if k and k.lower() != "head"]
            relationship = "SELF" if is_head else self.code("household_member", m["id"], "kind",
                                                            kinds[0] if kinds else None, C.RELATIONSHIP)
            member = _base("member", m["id"], f["create_date"], f["write_date"], link=row["internal_record_id"])
            member.update({
                "first_name": f["given_name"], "middle_name": f["family_name"], "last_name": f["gf_name_eng"],
                "gender": C.lookup(C.GENDER, f["gender"]), "birth_date": f["birthdate"],
                "birth_date_ec": _ec(f["birthdate"]), "is_disabled": C.yes_no(f["is_disabled"]),
                "is_head": is_head, "relationship_to_the_head": relationship,
                "odk_member_id": ids.get(f["id"], {}).get("Member ODK ACK ID"),
            })
            self.out.members.append(self.checked("HouseholdMember", "household_member", m["id"], member))

    def phones(self, fid, farmer_row, rows) -> list:
        """The farmer's numbers that are not disabled, each once. The first one
        farmer profile marks primary is the primary (else the first number)."""
        out = []
        rows = sorted((p for p in rows if not p["disabled"]),
                      key=lambda p: (str(p["phone_type"] or "").lower() != "primary", p["id"]))
        for p in rows:
            national, e164 = normalize_phone(p["phone_no"], "ET")
            if not national:
                self.issue("dropped", "phone", p["id"], "phone_no", p["phone_no"], "not a readable Ethiopian number")
                continue
            if any(o["phone_number"] == national for o in out):
                self.issue("dropped", "phone", p["id"], "phone_no", p["phone_no"], "the farmer has this number already")
                continue
            row = _base("phone", p["id"], p["create_date"], p["write_date"], link=farmer_row["internal_record_id"])
            first = not out
            kind = str(p["phone_type"] or "").upper()
            row.update({"phone_type": "PRIMARY" if first else ("OTHER" if kind == "OTHER" else "SECONDARY"),
                        "phone_number": national, "phone_e164": e164, "country_code": "ET", "is_primary": first})
            out.append(self.checked("FarmerPhone", "phone", p["id"], row))
        self.out.phones.extend(out)
        return out

    def lands(self, fid, farmer_row, rows) -> list:
        out = []
        for l in rows:
            row = _base("land", l["id"], l["create_date"], l["write_date"], link=farmer_row["internal_record_id"])
            size = float(l["total_land_area"]) if l["total_land_area"] is not None else None
            if size is not None and size > LARGE_PARCEL_HA:
                self.issue("check", "land", l["id"], "total_land_area", size, f"over {LARGE_PARCEL_HA} ha: kept as is")
            year = l["year_of_acquisition"]
            row.update({
                "land_id": l["land_id"], "land_size": size, "unit": "HECTARE", "area_in_hectare": hectares(size, "HECTARE"),
                "land_ownership_type": self.code("land", l["id"], "ownership_type", l["ownership_type"], C.LAND_OWNERSHIP),
                "certificate_provided": l["certficate_provided"],
                "year_of_acquisition": year.year if isinstance(year, date) else None,
                "current_land_use": self.code("land", l["id"], "current_land_use", l["current_land_use"], C.CURRENT_LAND_USE),
                "means_of_acquisition": self.code("land", l["id"], "means_of_acquisition",
                                                  _key(l["means_of_acquisition"]), C.MEANS_OF_ACQUISITION),
                "soil_fertility": self.code("land", l["id"], "soil_fertility", _key(l["soil_fertility"]), C.SOIL_FERTILITY),
                "remark": l["remark"],
                "land_kebele": self.geo.pcode("kebele", l["kebele_code"]),
            })
            if l["kebele_code"] and not row["land_kebele"]:
                self.issue("dropped", "land", l["id"], "land_kebele", l["kebele_code"], "no P-code in Master Data for this kebele: left empty")
            row.update(self.shape(l))
            out.append(self.checked("Land", "land", l["id"], row))
        self.out.lands.extend(out)
        return out

    def shape(self, land) -> dict:
        """Odoo keeps [[lat, lon], ...]; the registry a GeoJSON Polygon, [lon, lat], closed."""
        import json
        text = land["polygon_data"]
        if not text:
            return {}
        try:
            points = [[float(lon), float(lat)] for lat, lon in json.loads(text)]
        except (ValueError, TypeError):
            self.issue("dropped", "land", land["id"], "polygon_data", text[:60], "not a list of [lat, lon] points")
            return {}
        if len(points) < 3:
            self.issue("dropped", "land", land["id"], "polygon_data", len(points), "fewer than 3 points")
            return {}
        if points[0] != points[-1]:
            points.append(points[0])
        return {"shape_type": "POLYGON", "shape_coordinates_json": {"type": "Polygon", "coordinates": [points]}}

    def infestation(self, crop, illnesses):
        """One INFESTATION_AGENT code: the first disease with an agent of its own,
        else AGENT_OTHER. The names that do not survive are reported."""
        if not illnesses:
            return None
        wheat = "wheat" in str(crop["crop"] or "").lower()
        codes = []
        for name in illnesses:
            key = name.strip().lower()
            code = C.INFESTATION_AGENT.get(key) or ("AGENT_WHEAT_RUST" if wheat and key in C.RUSTS else None)
            codes.append((code, name))
        specific = [(c, n) for c, n in codes if c]
        chosen = specific[0][0] if specific else "AGENT_OTHER"
        lost = [n for c, n in codes if c != chosen]
        if lost:
            self.issue("check" if not specific else "dropped", "crop", crop["id"], "illness_type", ", ".join(lost),
                       f"INFESTATION_AGENT has no code for it: disease_type = {chosen}")
        return chosen

    def crops(self, fid, land_rows, rows):
        for c in rows:
            if not land_rows:
                self.issue("skipped", "crop", c["id"], "land", None, "the farmer has no land: a crop belongs to a land")
                continue
            if len(land_rows) > 1:
                self.issue("check", "crop", c["id"], "land", len(land_rows),
                           "farmer profile does not say which land: put on the farmer's first land")
            row = _base("crop", c["id"], c["create_date"], c["write_date"], link=land_rows[0]["internal_record_id"])
            illnesses = [i for i in (c["illnesses"] or "").split(",") if i]
            row.update({
                "commodity": self.code("crop", c["id"], "crop", c["crop"], self.codes.crop),
                "season": self.code("crop", c["id"], "season", c["season"], self.codes.season),
                "planted_date": c["collected_gc"], "planted_date_ec": c["collected_ec"] or _ec(c["collected_gc"]),
                "is_diseased": C.yes_no(c["is_diseased"]),
                "disease_type": self.infestation(c, illnesses),
            })
            self.out.crops.append(self.checked("Crop", "crop", c["id"], row))
