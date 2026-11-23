"""The Master Data Service's code lists and locations: a value is migrated only if it is there.

The registry validates coded values and builds location hierarchies from
Master Data (core helpers/master_data.MasterDataClient). The migration loads
the same data once, through the same client, and checks every coded column
and every location against it before writing. A value Master Data does not
have is left empty and reported, so the registry never holds a code it cannot
show or validate.

Which code list a column uses is the registry's own setting: the
widget-data-source of the column's widget in g2p_register_sections.

Settings: MDS_API_URL, MDS_TOKEN_URL, MDS_CLIENT_ID, MDS_CLIENT_SECRET (as the
chart's Jobs get them), or the core's REGISTRY_CORE_MASTER_DATA_* names.
Without them a run must say --pack-only, and then checks against the country
pack (local tests only: the pack is what Master Data was seeded from, not
what it holds now).
"""
import asyncio
import collections
import glob
import json
import os
from pathlib import Path

from sqlalchemy import text

_ENV = {"MDS_API_URL": "MASTER_DATA_API_URL", "MDS_TOKEN_URL": "MASTER_DATA_TOKEN_URL",
        "MDS_CLIENT_ID": "MASTER_DATA_CLIENT_ID", "MDS_CLIENT_SECRET": "MASTER_DATA_CLIENT_SECRET"}
# The registry reads its settings under the running service's prefix: in this
# process the staff API's Settings stand in for core's.
_PREFIXES = ("REGISTRY_CORE_", "REGISTRY_STAFF_PORTAL_API_")


def configure_env():
    """Give the registry's Master Data client the MDS_* settings. Call before its settings load."""
    for ours, name in _ENV.items():
        for prefix in _PREFIXES:
            if os.environ.get(ours) and not os.environ.get(prefix + name):
                os.environ[prefix + name] = os.environ[ours]


def service_url():
    return next((os.environ[p + "MASTER_DATA_API_URL"] for p in _PREFIXES if os.environ.get(p + "MASTER_DATA_API_URL")),
                os.environ.get("MDS_API_URL", ""))


class MasterData:
    def __init__(self, codes: dict, nodes: dict, source: str):
        self.codes = codes          # attribute id -> set of value codes
        self.nodes = nodes          # P-code -> {level_mnemonic, level_value_mnemonic, level_value_id, parent}
        self.source = source
        self.bindings = {}          # (register, column) -> set of attribute ids

    def describe(self):
        return f"{self.source}: {len(self.codes)} code lists, {len(self.nodes)} locations"

    @classmethod
    def from_service(cls):
        from openg2p_registry_core.helpers.master_data import MasterDataClient
        client = MasterDataClient()
        if not client.is_configured():
            raise SystemExit("Master Data is not configured: set MDS_API_URL (and MDS_TOKEN_URL, MDS_CLIENT_ID, "
                             "MDS_CLIENT_SECRET), or run with --pack-only for a local test")

        async def load():
            return await client.get_attribute_codes(), await client._load_geo_index()

        codes, index = asyncio.run(load())
        if not codes or not index:
            raise SystemExit(f"Master Data at {service_url()} returned {len(codes)} code lists and {len(index)} "
                             "locations: refusing to migrate against an empty Master Data")
        nodes = {k: {"level_mnemonic": v["level_mnemonic"], "level_value_mnemonic": v["level_value_mnemonic"],
                     "level_value_id": v["level_value_id"], "parent": v.get("parent_level_value_id")}
                 for k, v in index.items()}
        return cls({k: set(v) for k, v in codes.items()}, nodes, f"Master Data Service {service_url()}")

    @classmethod
    def from_pack(cls, pack_root):
        codes = collections.defaultdict(set)
        for path in sorted(glob.glob(os.path.join(pack_root, "**", "*.json"), recursive=True)):
            try:
                doc = json.load(open(path, encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            for item in doc if isinstance(doc, list) else [doc]:
                if isinstance(item, dict) and item.get("attribute_id") and isinstance(item.get("values"), list):
                    codes[item["attribute_id"]].update(v.get("value_code") for v in item["values"] if isinstance(v, dict))
        pack = Path(pack_root) / "ETH-OAN"
        levels = {lvl["level_id"]: lvl["level_mnemonic"]
                  for lvl in json.loads((pack / "levels.json").read_text(encoding="utf-8"))}
        values = json.loads((pack / "values.json").read_text(encoding="utf-8"))
        values = values if isinstance(values, list) else next(v for v in values.values() if isinstance(v, list))
        nodes = {v["level_value_id"]: {"level_mnemonic": levels.get(v["level_id"]),
                                       "level_value_mnemonic": v["level_value_mnemonic"],
                                       "level_value_id": v["level_value_id"],
                                       "parent": v.get("parent_level_value_id")} for v in values}
        return cls(dict(codes), nodes, f"country pack {pack_root} (--pack-only: NOT checked against Master Data)")

    def load_bindings(self, engine):
        """Which code list each register column uses, from the registry's section metadata."""
        with engine.connect() as conn:
            registers = dict(conn.execute(text("SELECT register_id, register_mnemonic FROM g2p_register_definitions")).all())
            for register_id, column, attribute in conn.execute(text(BINDINGS)).all():
                if registers.get(register_id):
                    self.bindings.setdefault((registers[register_id], column), set()).add(attribute)
        return self

    def allowed(self, register, column):
        """The codes a column may hold, or None when it is not a coded column."""
        attributes = self.bindings.get((register, column))
        if not attributes:
            return None
        return set().union(*(self.codes.get(a, set()) for a in attributes))


BINDINGS = """
SELECT DISTINCT
       CASE WHEN w->>'widget-data-path' LIKE '%.%' THEN split_part(w->>'widget-data-path', '.', 1)
            ELSE s.section_register_id END AS register_id,
       regexp_replace(w->>'widget-data-path', '^.*[.]', '') AS column_name,
       w->'widget-data-source'->'params'->>'attribute_id' AS attribute
  FROM g2p_register_sections s, jsonb_path_query(s.section_ui_schema, 'strict $.**') w
 WHERE jsonb_typeof(w) = 'object' AND w->'widget-data-source'->'params' ? 'attribute_id'
"""
