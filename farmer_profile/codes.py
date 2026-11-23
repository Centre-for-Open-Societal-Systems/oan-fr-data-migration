"""Odoo (g2p_ati) values to the registry's codes.

The codes are the country pack's (openg2p-data packs/ETH and ETH-OAN), the
lists Master Data serves to the registry. A value with no code returns None
and the caller records it as a problem: nothing is guessed.
"""
import json
import re
from pathlib import Path

GENDER = {"male": "MALE", "female": "FEMALE"}
MARITAL_STATUS = {"single": "SINGLE", "married": "MARRIED", "widowed": "WIDOWED",
                  "divorced": "DIVORCED", "separated": "SEPARATED"}
EDUCATION = {"illiterate": "ILLITERATE", "read_write": "CAN_READ_AND_WRITE", "non_formal": "NON_FORMAL",
             "basic": "BASIC", "primary": "PRIMARY", "intermediary": "INTERMEDIARY",
             "secondary": "SECONDARY", "tertiary": "TERTIARY", "higher_education": "HIGHER_EDUCATION"}
FARMING_TYPE = {"crop_farming": "CROP", "livestock_farming": "LIVESTOCK", "mixed_farming": "MIXED"}
LAND_OWNERSHIP = {"owner": "OWNER", "tenant": "TENANT", "crop_share": "CROP_SHARE"}
CURRENT_LAND_USE = {"agricultural": "AGRICULTURAL", "residential": "RESIDENTIAL",
                    "grazing": "GRAZING", "forest": "FOREST"}
# g2p_land_information.means_of_acquisition (free text in farmer profile)
MEANS_OF_ACQUISITION = {"inheritance": "MOA_INHERITANCE", "inherited": "MOA_INHERITANCE",
                        "donation": "MOA_DONATION_GIFT", "gift": "MOA_DONATION_GIFT", "donation_gift": "MOA_DONATION_GIFT", "donation_or_gift": "MOA_DONATION_GIFT",
                        "expropriation": "MOA_EXPROPRIATION", "rent": "MOA_RENTING_LEASING",
                        "renting": "MOA_RENTING_LEASING", "lease": "MOA_RENTING_LEASING",
                        "leasing": "MOA_RENTING_LEASING", "renting_leasing": "MOA_RENTING_LEASING", "renting_or_leasing": "MOA_RENTING_LEASING",
                        "reallocation": "MOA_REALLOCATION", "allocation": "MOA_REALLOCATION",
                        "divorce": "MOA_DIVORCE_SETTLEMENT", "divorce_settlement": "MOA_DIVORCE_SETTLEMENT"}
SOIL_FERTILITY = {"high": "SF_HIGH", "medium": "SF_MEDIUM", "moderate": "SF_MEDIUM", "low": "SF_LOW"}
# g2p_illness_type names (crop) -> INFESTATION_AGENT. The registry's list is coarser:
# a disease without its own agent is AGENT_OTHER (reported with its name)
INFESTATION_AGENT = {"mlnd": "AGENT_MAIZE_LETHAL_NECROSIS", "maize lethal necrosis": "AGENT_MAIZE_LETHAL_NECROSIS",
                     "septoria leaf spot": "AGENT_SEPTORIA", "septoria": "AGENT_SEPTORIA",
                     "fall armyworm": "AGENT_FALL_ARMYWORM", "desert locust": "AGENT_DESERT_LOCUST",
                     "stalk borer": "AGENT_STALK_BORER", "aphids": "AGENT_APHIDS", "aphid": "AGENT_APHIDS",
                     "striga": "AGENT_STRIGA", "parthenium": "AGENT_PARTHENIUM"}
# rusts are the wheat-rust agent on wheat only
RUSTS = {"stem rust", "yellow rust", "leaf rust", "stripe rust"}
# g2p_hh_income names
INCOME = {"crop production": "SOI_CROP_PRODUCTION", "livestock production": "SOI_LIVESTOCK_PRODUCTION",
          "government/ ngo support": "SOI_GOVERNMENT_NGO_SUPPORT", "government/ngo support": "SOI_GOVERNMENT_NGO_SUPPORT",
          "others": "SOI_OTHERS"}
# g2p_group_membership_kind names; the head is marked separately (is_head)
RELATIONSHIP = {"head": "SELF", "wife - head": "SPOUSE", "husband - head": "SPOUSE",
                "wife": "SPOUSE", "husband": "SPOUSE", "son": "CHILD", "daughter": "CHILD",
                "child": "CHILD", "parent": "PARENT", "sibling": "SIBLING", "other": "OTHER_RELATIVE"}
# Odoo crop names whose pack name differs (as odk/transform.py's CROPS)
CROP_ALIASES = {"wheat": "CROP_BREAD_WHEAT", "maize (corn)": "CROP_MAIZE", "maize": "CROP_MAIZE",
                "food barley": "CROP_BARLEY", "malt barley": "CROP_MALT_BARLEY", "nug": "CROP_NOUG",
                "false banana": "CROP_ENSET", "korerima": "CROP_KORARIMA"}
LANGUAGE_ALIASES = {"afaan oromoo": "AFAAN_OROMO", "afaan oromo": "AFAAN_OROMO", "oromiffa": "AFAAN_OROMO",
                    "other languages": "OTHER"}


def yes_no(value):
    """Odoo stores yes/no answers as text; None when not answered or unreadable."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return True if text in ("yes", "true", "1") else False if text in ("no", "false", "0") else None


def lookup(table: dict, value):
    """The code for an Odoo selection value, None when it has none."""
    if value is None or value == "":
        return None
    return table.get(str(value).strip().lower())


def _items(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


class PackCodes:
    """Code lists from the country pack, matched by code or by display name."""

    def __init__(self, pack_root: Path):
        self.root = Path(pack_root)
        self.crops = self._index("ETH/domains/agriculture/crop_commodity.json")
        self.seasons = self._index("ETH/domains/agriculture/crop_season.json")
        self.languages = self._index("ETH-OAN/codelists/language.json")

    def _index(self, relative: str) -> dict[str, str]:
        index = {}
        for item in _items(self.root / relative):
            code = item["value_code"]
            index[_key(code)] = code
            index[_key(item.get("value_display") or "")] = code
            # "Meher (main rains)" is also called "Meher", "Guragigna (Gurage)" "Gurage"
            display = item.get("value_display") or ""
            index.setdefault(_key(re.sub(r"\(.*\)", "", display)), code)
            for inner in re.findall(r"\(([^)]*)\)", display):
                index.setdefault(_key(inner), code)
        index.pop("", None)
        return index

    def crop(self, name):
        if not name:
            return None
        alias = CROP_ALIASES.get(str(name).strip().lower())
        return alias or self.crops.get(_key(name)) or self.crops.get(_key("crop " + str(name)))

    def season(self, name):
        if not name:
            return None
        return self.seasons.get(_key(name)) or self.seasons.get(_key("season " + str(name)))

    def language(self, name):
        if not name:
            return None
        return LANGUAGE_ALIASES.get(str(name).strip().lower()) or self.languages.get(_key(name))
