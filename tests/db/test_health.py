"""health.py: where every record went, what is wrong, and that it says so without personal data."""
import openpyxl
import pytest


def groups(world, kind):
    from farmer_profile.health import GROUPS
    return {k: world.measured(label, kind)[0] for k, label in GROUPS.items() if world.measured(label, kind)[0]}


def workbook(world):
    folder = sorted((world.tmp / "out").glob("*-health*"))[-1]
    return openpyxl.load_workbook(folder / "health-report.xlsx")


def test_every_record_is_in_one_group(world):
    world.farmers(8)
    world.household(9001, 1, 2, 3)
    world.source("INSERT INTO g2p_group_membership (id, \"group\", individual, is_ended) VALUES (77, 9001, 4, true)")
    world.source("UPDATE res_partner SET active = false WHERE id = 6")
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 7")
    world.source("UPDATE g2p_phone_number SET disabled = now() WHERE id = 8")
    world.source("INSERT INTO g2p_phone_number (id, partner_id, phone_no) VALUES (900, 1, '12')")
    world.farmers(1, 500)
    world.source("DELETE FROM g2p_land_information WHERE partner_id = 500")
    world.source("INSERT INTO g2p_crop_information (id, partner_id) VALUES (64, 1), (66, 500)")
    assert world.migrate()[0] == 3
    # in Gen1 since: a land of a migrated farmer, and a farmer
    world.source("INSERT INTO g2p_land_information (id, partner_id, total_land_area) VALUES (9999, 4, 2)")
    world.farmers(1, 600)
    code, out = world.health()
    assert code == 3, out[-3000:]  # a household failed
    assert groups(world, "farmer") == {"loaded": 7, "failed": 1, "out_of_scope": 1, "not_reached": 1}
    assert groups(world, "household") == {"loaded": 1}
    assert groups(world, "member") == {"loaded": 3, "out_of_scope": 1}
    assert groups(world, "phone") == {"loaded": 6, "failed": 1, "left_out": 1, "out_of_scope": 2, "not_reached": 1}
    assert groups(world, "land") == {"loaded": 12, "failed": 2, "not_added": 1, "out_of_scope": 2, "not_reached": 2}
    assert groups(world, "crop") == {"loaded": 1, "left_out": 1}
    for kind in ("farmer", "household", "member", "phone", "land", "crop"):
        assert sum(groups(world, kind).values()) == world.measured("Gen1 records", kind)[0]
    assert world.measured("Failed households still open", "household") == (1, None, "RED")
    from farmer_profile.health import MADE
    assert world.measured(MADE, "household")[0] == 4 and world.measured(MADE, "land")[0] == 0
    sheet = workbook(world)["Reconciliation"]
    adds_up = [c.value for c in sheet[1]].index("Adds up")
    assert [r[adds_up].value for r in sheet.iter_rows(min_row=2)] == [True] * 6


def test_a_record_that_disappeared_is_unexplained(world):
    world.farmers(3)
    world.migrate()
    world.rows("DELETE FROM g2p_register_lands WHERE land_id = 'L2-1'")
    code, out = world.health()
    assert code == 3 and "HEALTH: RED" in out
    assert world.measured("Unexplained", "land") == (1, 6, "RED")


def test_a_record_never_loaded_is_unexplained(world):
    """Its household is in and unchanged, and nothing says why it is not."""
    world.farmers(3)
    world.migrate()
    world.rows("DELETE FROM g2p_register_lands WHERE land_id = 'L2-1'")
    world.rows("DELETE FROM migration.migrated_record WHERE kind = 'land' AND odoo_id = 21")
    assert world.health()[0] == 3
    assert world.measured("Unexplained", "land")[0] == 1


BREAKS = {
    "head": ("UPDATE g2p_register_household_members SET is_head = false WHERE first_name = 'Abebe1'",
             "Breaks the rule: every household has exactly one head member", ""),
    "phone": ("UPDATE g2p_register_farmer_phones SET is_primary = false WHERE phone_number = '911000001'",
              "Breaks the rule: every farmer with a phone has exactly one primary number", ""),
    "link": ("UPDATE g2p_register_crops SET link_internal_record_id = 'nowhere'", "Breaks the rule: every Crop links to a Land", ""),
    "both ids": ("DELETE FROM migration.migrated_record WHERE kind = 'phone' AND odoo_id = 2",
                 "Migrated records with both IDs saved", "phone"),
    "farmer id": ("UPDATE g2p_register_farmers SET functional_record_id = 'FR-X' WHERE first_name = 'Abebe2'",
                  "Gen1 Farmer IDs that arrived unchanged", "farmer"),
    "last run": ("UPDATE migration.run SET status = 'STOPPED'", "Last run completed", ""),
}


@pytest.mark.parametrize("what", BREAKS)
def test_each_blocking_check_turns_red(world, what):
    world.farmers(3)
    world.source("INSERT INTO g2p_crop_information (id, partner_id) VALUES (64, 1)")
    world.source("UPDATE res_partner SET farmer_id = 'FR-0000000002' WHERE id = 2")
    world.migrate()
    sql, metric, kind = BREAKS[what]
    assert world.measured(metric, kind)[2] == "GREEN"  # as measured after the load
    world.rows(sql)
    code, out = world.health()
    assert code == 3, out[-2000:]
    assert world.measured(metric, kind)[2] == "RED"


def test_it_is_not_green_before_verify(world):
    world.farmers(3)
    assert world.migrate()[0] == 0
    values = "Values matching Gen1 (verify)"
    assert world.measured(values)[2] == "NOT CHECKED"
    assert world.one("SELECT overall FROM migration_report.snapshot") == "AMBER"
    assert world.verify("--limit", "1")[0] == 0   # not everything: does not count
    assert world.health()[0] == 0 and world.measured(values)[2] == "NOT CHECKED"
    assert world.verify()[0] == 0
    assert world.health()[0] == 0
    count, total, result = world.measured(values)
    assert result == "GREEN" and count == total > 0
    # what is wrong now is red
    world.rows("UPDATE g2p_register_farmers SET first_name = 'X' WHERE first_name = 'Abebe2'")
    assert world.verify()[0] == 1
    assert world.health()[0] == 3 and world.measured(values)[2] == "RED"
    # a later load: what verify said is of before it
    world.farmers(1, 600)
    world.migrate()
    assert world.health()[0] == 0 and world.measured(values)[2] == "NOT CHECKED"


def test_numbers(world):
    world.farmers(6)
    world.source("UPDATE res_partner SET farmer_id = 'FR-0000000001' WHERE id = 1")
    world.migrate()
    farmer = "(SELECT internal_record_id FROM g2p_register_farmers WHERE first_name = '{}')"
    world.rows(f"UPDATE g2p_register_farmers SET functional_record_id = 'FR-9' WHERE internal_record_id = {farmer.format('Abebe2')}")
    world.rows(f"UPDATE g2p_functional_id_generation_queue SET id_allocation_status = 'FAILED' "
               f"WHERE internal_record_id = {farmer.format('Abebe3')}")
    world.rows(f"DELETE FROM g2p_functional_id_generation_queue WHERE internal_record_id = {farmer.format('Abebe4')}")
    world.health()
    got = {w: world.measured(f"Farmer numbers {w}", "farmer")[0]
           for w in ("copied from Gen1", "generated by Gen2", "waiting", "failed", "not queued")}
    assert got == {"copied from Gen1": 1, "generated by Gen2": 1, "waiting": 2, "failed": 1, "not queued": 1}
    assert world.measured("Farmer numbers failed", "farmer")[2] == "AMBER"
    assert world.measured("Household numbers waiting", "household")[0] == 6


def test_a_number_that_is_taken(world):
    world.farmers(3)
    world.source("UPDATE res_partner SET farmer_id = 'FR-0000000002' WHERE id IN (2, 3)")
    world.migrate()
    world.health()
    assert world.measured("Households left out because a farmer's number is taken", "household")[0] == 1


def test_lost_values_and_shared_ids(world):
    world.farmers(6)
    world.source("UPDATE res_partner SET martial_status = 'married', state = CASE WHEN id = 1 THEN 'draft' ELSE 'approved' END")
    world.source("UPDATE res_partner SET martial_status = 'unheard of' WHERE id = 3")
    world.source("INSERT INTO g2p_reg_id (id, partner_id, id_type, value) VALUES (1, 1, 1, '1234 5678 9012'), "
                 "(2, 2, 1, '123456789012'), (3, 3, 1, '2222 2222 2222'), (4, 3, 2, '3333333333333333')")
    world.migrate()
    married = ("Filled in Gen2, of filled in Gen1", "farmer", "martial_status -> marital_status")
    assert world.measured(*married) == (5, 6, "INFO")          # one left empty, with a reason
    assert world.measured("Values lost without a reason", "farmer")[0] == 0
    assert world.measured("Farmers sharing a Fayda ID with another migrated farmer", "farmer") == (2, None, "AMBER")
    assert world.measured("FANs not carried: the farmer has a UID too", "farmer")[0] == 1
    assert world.measured("Gen1 status to Gen2 status", "farmer", "draft -> ACTIVE")[0] == 1
    world.rows("UPDATE g2p_register_farmers SET marital_status = NULL WHERE first_name = 'Abebe2'")
    # a farmer registered in Gen2 itself, and one edited there
    world.rows("UPDATE g2p_register_farmers SET created_by = 'staff', foundational_id = '222222222222' WHERE first_name = 'Abebe6'")
    world.rows("UPDATE g2p_register_farmers SET last_approved_by = 'staff', marital_status = NULL WHERE first_name = 'Abebe5'")
    world.health()
    assert world.measured("Values lost without a reason", "farmer") == (1, None, "AMBER")
    assert world.measured("Farmers sharing a Fayda ID with a farmer already in Gen2", "farmer")[0] == 1
    assert world.measured("Edited in Gen2 since (not compared)", "farmer")[0] == 1


def test_required_fields(world):
    world.rows("""INSERT INTO g2p_register_sections (section_id, register_id, section_register_id, section_mnemonic,
                    is_core_section, documents_required, no_of_verifications_required, is_list, section_weightage,
                    cr_auto_approve_for_bene_portal, cr_auto_approve_for_agent_portal, cr_auto_approve_for_staff_portal,
                    cr_auto_approve_for_partner, section_ui_schema)
                  VALUES ('s1', 'r-f', 'r-f', 's', true, false, 0, false, 1, false, false, false, false, %s)""",
               '{"widgets": [{"widget-required": true, "widget-data-path": "marital_status"}, '
               '{"widget-required": true, "widget-data-path": "first_name"}, {"widget-data-path": "gender"}]}')
    world.farmers(3)
    world.migrate()
    assert world.measured("Required by Gen2's forms, and empty", "farmer", "marital_status")[:2] == (3, 3)
    assert world.measured("Required by Gen2's forms, and empty", "farmer", "first_name")[:2] == (0, 3)
    assert world.rows("SELECT 1 FROM migration_report.measure WHERE split_value = 'gender' AND metric LIKE 'Required%'") == []


def test_no_personal_data(world):
    world.farmers(6)
    world.source("UPDATE res_partner SET farmer_id = 'FR-0000000002' WHERE id IN (2, 3)")
    world.source("INSERT INTO g2p_phone_number (id, partner_id, phone_no) VALUES (900, 1, '0911-bad-55')")
    world.source("INSERT INTO g2p_reg_id (id, partner_id, id_type, value) VALUES (1, 1, 1, '1234 5678 9012'), (2, 4, 1, '1234 5678 9012')")
    world.source("UPDATE res_partner SET martial_status = 'secret value' WHERE id = 5")
    world.migrate()
    world.verify()
    world.health()
    stored = " ".join(str(v) for row in world.rows("SELECT area, metric, record_type, split_by, split_value, target FROM "
                                                   "migration_report.measure") for v in row)
    shown = " ".join(str(c.value) for ws in workbook(world) for row in ws.iter_rows() for c in row)
    for secret in ("Abebe", "Kebede", "0911", "911000", "bad-55", "1234", "FR-0", "secret", "solo-", "already exists"):
        assert secret not in stored, secret
        assert secret not in shown, secret


def test_the_workbooks(world):
    world.farmers(3)
    world.migrate()
    wb = openpyxl.load_workbook(world.folder() / "migration-report.xlsx")
    assert wb.sheetnames[0] == "Health" and wb["Health"]["B2"].value == "AMBER"
    assert any(r[1].value == "Values matching Gen1 (verify)" and r[10].value == "NOT CHECKED" for r in wb["Health"].iter_rows())
    assert "HEALTH: AMBER" in (world.folder() / "summary.txt").read_text()
    world.health()
    wb = workbook(world)
    assert wb.sheetnames == ["Overview", "Reconciliation", "Run health", "Quality", "IDs", "By region, source and status", "Trend"]
    assert wb["Trend"].max_column == 3 + 2  # the load's own, and this one
    # a dry run measures nothing
    world.migrate("--all", "--dry-run")
    wb = openpyxl.load_workbook(world.folder() / "migration-report.xlsx")
    assert wb.sheetnames[0] == "Health" and wb["Health"]["A2"].value.startswith("Measured after a load")
    assert world.one("SELECT count(*) FROM migration_report.snapshot") == 2


def test_a_report_that_fails_does_not_fail_the_load(world):
    world.rows("CREATE SCHEMA migration_report; CREATE TABLE migration_report.snapshot (something_else int)")
    world.farmers(3)
    code, out = world.migrate()
    assert code == 0 and "the load is not affected" in out, out[-2000:]
    assert world.counts()["farmers"] == 3 and world.statuses() == ["COMPLETED"]
    wb = openpyxl.load_workbook(world.folder() / "migration-report.xlsx")
    assert wb["Health"]["A2"].value.startswith("The health could not be measured")


def test_nothing_migrated_yet(world):
    code, out = world.health()
    assert code == 1 and "nothing has been migrated yet" in out
