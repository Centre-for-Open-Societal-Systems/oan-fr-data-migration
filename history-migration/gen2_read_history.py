"""Read the version 1 rows back through the registry's own get_record_history (what the
Staff Portal's history tab calls). Runs inside the registry staff-api image with the
Farmer extension importable, against the records test_gen2_read.sh loads.
Prints one PASS/FAIL line per record; exit code 1 if any failed."""
import asyncio
import importlib
import os
import sys

sys.modules["openg2p_registry_extensions"] = importlib.import_module(
    os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_farmer_extension"))
importlib.import_module("openg2p_registry_staff_api.config").Settings.get_config()
importlib.import_module("openg2p_registry_extensions.app").Initializer()
from openg2p_registry_core.services import G2PRegisterService  # noqa: E402

# (register, record, tab, field, value): one version 1 row, written by the migration
EXPECTED = [("Farmer", "f11", "farmer_farmer_tab", "first_name", "Abebe"),
            ("Land", "l51", "farmer_land_tab", "land_size", "1.5"),
            ("Crop", "c61", "farmer_crop_tab", "commodity", "teff"),
            ("FarmerPhone", "p41", "farmer_farmer_tab", "phone_number", "0911000000"),
            ("Household", "h21", "household_household_tab", "record_name", "Household of Abebe"),
            ("HouseholdMember", "m31", "household_household_tab", "first_name", "Abebe")]


async def main():
    from openg2p_fastapi_common.context import get_async_session_maker
    from openg2p_registry_core.models import G2PRegisterDefinition
    from sqlalchemy import select
    async with get_async_session_maker()() as session:
        ids = {d.register_mnemonic: d.register_id for d in (await session.execute(select(G2PRegisterDefinition))).scalars()}
    service = G2PRegisterService.get_component()
    failed = 0
    for register, record, tab, field, value in EXPECTED:
        try:
            data = await service.get_record_history(ids[register], record, tab)
            got = [h.model_dump() for h in data.history_records]
            good = (len(got) == 1 and got[0]["change_request_source"] == "PARTNER"
                    and got[0]["approved_by"] == "farmer-profile-migration" and str(got[0].get(field)) == value)
            detail = (f"{len(got)} row(s); " + ", ".join(f"{h['section_id']} {h['change_request_source']} {h['approved_by']} "
                                                       f"{field}={h.get(field)}" for h in got))
        except Exception as e:  # noqa: BLE001 - report every failure the Staff Portal would show
            good, detail = False, f"{type(e).__name__}: {e}"
        failed += not good
        print(f"{'PASS' if good else 'FAIL'}: Gen2 reads the history of {register} {record}: {detail}")
    sys.exit(1 if failed else 0)


asyncio.run(main())
