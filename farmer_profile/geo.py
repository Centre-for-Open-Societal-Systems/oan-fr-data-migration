"""Odoo locations (g2p_region, g2p_zone, g2p_woreda, g2p_kebele) to P-codes.

Odoo keeps the old catalogue's codes, often as numbers that lost their leading
zero (zone 313 is 0313). The country pack's migration/id_map.csv maps every old
code to its P-code. The locations themselves (each P-code's name and parent)
come from Master Data (masterdata.py): a P-code Master Data does not have is
not used, so a location falls back to the next level up. The hierarchy is
built the way core's Master Data client builds it
(openg2p_registry_core.helpers.master_data.get_geo_hierarchy).
"""
import csv
import json
from pathlib import Path

LEVELS = ("region", "zone", "woreda", "kebele")
WIDTH = {"region": 2, "zone": 4, "woreda": 6, "kebele": 12}


class Geo:
    def __init__(self, pack_root: Path, nodes: dict | None = None):
        """nodes: Master Data's locations (MasterData.nodes); default: the pack's."""
        pack = Path(pack_root) / "ETH-OAN"
        with open(pack / "migration" / "id_map.csv", encoding="utf-8") as handle:
            self.id_map = {row["source_id"]: row["pack_id"] for row in csv.DictReader(handle)}
        if nodes is not None:
            self.nodes = nodes
            return
        levels = {level["level_id"]: level["level_mnemonic"]
                  for level in json.loads((pack / "levels.json").read_text(encoding="utf-8"))}
        values = json.loads((pack / "values.json").read_text(encoding="utf-8"))
        values = values if isinstance(values, list) else next(v for v in values.values() if isinstance(v, list))
        self.nodes = {v["level_value_id"]: {"level_mnemonic": levels.get(v["level_id"]),
                                            "level_value_mnemonic": v["level_value_mnemonic"],
                                            "level_value_id": v["level_value_id"],
                                            "parent": v.get("parent_level_value_id")} for v in values}

    def pcode(self, level: str, odoo_code) -> str | None:
        """The P-code for an Odoo location code, None when there is none or Master Data does not have it."""
        if odoo_code is None or str(odoo_code).strip() == "":
            return None
        digits = str(odoo_code).strip().upper().removeprefix("ET")
        if not digits.isdigit():
            return None
        code = self.id_map.get(f"{level}-ET{digits.zfill(WIDTH[level])}")
        return code if code in self.nodes else None

    def lowest(self, codes: dict) -> tuple[str | None, str | None]:
        """(P-code, level) of the lowest location that maps, kebele first."""
        for level in reversed(LEVELS):
            code = self.pcode(level, codes.get(level))
            if code:
                return code, level
        return None, None

    def hierarchy(self, pcode: str | None) -> dict | None:
        """{"hierarchy": [...]} from the country down to pcode, as core stores it."""
        chain, current, seen = [], pcode, set()
        while current and current not in seen and current in self.nodes:
            seen.add(current)
            node = self.nodes[current]
            chain.append({k: node[k] for k in ("level_mnemonic", "level_value_mnemonic", "level_value_id")})
            current = node["parent"]
        return {"hierarchy": list(reversed(chain))} if chain else None
