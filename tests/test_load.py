"""prepare() runs the registry's hooks in memory; the SQL it loads with is well formed."""
from datetime import date, datetime

from test_transform import data, farmer, land  # noqa: F401  (the same hand-made rows)


def test_prepare_runs_the_registry_hooks_without_a_database(models, pack_root):
    from farmer_profile import load
    from farmer_profile.codes import PackCodes
    from farmer_profile.geo import Geo
    from farmer_profile.transform import Transformer
    result = Transformer(PackCodes(pack_root), Geo(pack_root))(data([farmer(1)], lands=[land(1, 1)]))
    prepared = load.prepare(result)
    names, rows = prepared.tables["g2p_register_farmers"]
    row = dict(zip(names, rows[0]))
    assert row["record_name"] and "Abebe" in row["record_name"]          # core's / the extension's name hook
    assert row["search_text"] and "abebe" in row["search_text"].lower()  # core's search hook
    assert row["record_status"] == "ACTIVE"
    names, rows = prepared.tables["g2p_register_lands"]
    assert dict(zip(names, rows[0]))["record_name"]
    assert list(prepared.tables) == ["g2p_register_households", "g2p_register_farmers",  # parents first
                                     "g2p_register_household_members", "g2p_register_farmer_phones",
                                     "g2p_register_lands", "g2p_register_crops"]


def test_copy_text_format():
    from farmer_profile.load import copy_data
    line = copy_data([(None, True, "a\tb\nc\\d", {"k": [1, "é"]}, date(2020, 1, 2), datetime(2020, 1, 2, 3, 4, 5), 1.5)])
    assert line == '\\N\tt\ta\\tb\\nc\\\\d\t{"k": [1, "é"]}\t2020-01-02\t2020-01-02T03:04:05\t1.5\n'


def test_sql_file_is_one_transaction(tmp_path):
    from farmer_profile.load import Prepared, SqlFile
    p = Prepared()
    p.tables["g2p_register_crops"] = (["internal_record_id", "commodity"], [("x", "CROP_TEFF")])
    f = SqlFile(tmp_path / "m.sql", ["header"])
    f.add(p)
    f.finish([], [("queue", "SELECT 1")])
    text = (tmp_path / "m.sql").read_text()
    assert text.index("BEGIN;") < text.index("COPY") < text.index("INSERT INTO") < text.index("SELECT 1") < text.index("COMMIT;")
    assert "ON CONFLICT (internal_record_id) DO NOTHING" in text
    assert "x\tCROP_TEFF\n\\.\n" in text
