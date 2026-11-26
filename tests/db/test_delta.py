"""Gen1 changes after the migration: a rerun of --all brings them, unless the registry has edited the household."""
import openpyxl
import pytest

from conftest import TABLES

CHANGES = {
    "joins a household": lambda w: w.household(9005, 10, 60, head=60),
    "leaves the household": lambda w: w.source("UPDATE g2p_group_membership SET is_ended = true WHERE individual = 2"),
    "a new member": lambda w: (w.farmers(1, 500), w.household(9001, 500, head=1)),
    "another head": lambda w: w.source("UPDATE g2p_group_membership_g2p_group_membership_kind_rel SET "
                                       "g2p_group_membership_kind_id = 5 - g2p_group_membership_kind_id"),
    "another primary phone": lambda w: (
        w.source("UPDATE g2p_phone_number SET phone_type = 'secondary' WHERE partner_id = 10"),
        w.source("INSERT INTO g2p_phone_number (id, partner_id, phone_no, phone_type) VALUES (9999, 10, '0922000001', 'primary')")),
    "another land": lambda w: w.source("INSERT INTO g2p_land_information (id, partner_id, total_land_area) VALUES (9999, 10, 2)"),
    "a land deleted": lambda w: w.source("DELETE FROM g2p_land_information WHERE id = 101"),
    "a phone disabled": lambda w: w.source("UPDATE g2p_phone_number SET disabled = now() WHERE partner_id = 10"),
    "another name": lambda w: w.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10"),
    "a farmer archived": lambda w: w.source("UPDATE res_partner SET active = false WHERE id = 10"),
    "a member archived": lambda w: w.source("UPDATE res_partner SET active = false WHERE id = 3"),
    "a farmer disabled": lambda w: w.source("UPDATE res_partner SET disabled = now() WHERE id = 10"),
}


def start(world):
    world.farmers(60)
    world.household(9001, 1, 2, 3)
    code, out = world.migrate()
    assert code == 0, out[-3000:]


def active(world):
    """Every record that is in, as a fresh migration would write it: without what was set inactive."""
    out = {}
    for t in TABLES:
        out[t] = world.rows(f"SELECT (to_jsonb(x) - 'functional_record_id')::text FROM g2p_register_{t} x WHERE "
                            "internal_record_id NOT IN (SELECT gen2_id FROM migration.migrated_record "
                            "WHERE removed_run_id IS NOT NULL) ORDER BY 1")
    return out


def fresh(world):
    """The registry as a first migration of Gen1, as it is now, makes it."""
    world.rows("TRUNCATE " + ", ".join(f"g2p_register_{t}" for t in TABLES)
               + ", g2p_functional_id_generation_queue; DROP SCHEMA migration CASCADE")
    code, out = world.migrate()
    assert code == 0, out[-3000:]
    return active(world)


@pytest.mark.parametrize("change", CHANGES)
def test_a_rerun_brings_what_changed(world, change):
    start(world)
    CHANGES[change](world)
    code, out = world.migrate()
    assert code == 0, out[-3000:]
    assert world.one("SELECT count(*) FROM migration.change") > 0, out[-3000:]
    assert world.unlinked() == ([], [])
    assert world.rows("SELECT link_internal_record_id FROM g2p_register_household_members WHERE is_head "
                      "AND record_status = 'ACTIVE' GROUP BY 1 HAVING count(*) > 1") == []
    after, again = active(world), world.migrate()
    assert again[0] == 0 and active(world) == after  # nothing more to do
    assert world.one("SELECT count(*) FROM migration.change WHERE run_id = (SELECT max(run_id) FROM migration.run)") == 0
    assert after == fresh(world)


def test_what_changed_is_recorded_value_by_value(world):
    start(world)
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    world.migrate()
    rows = world.rows("SELECT action, kind, odoo_id, field, old_value, new_value FROM migration.change "
                      "WHERE field NOT IN ('last_approved_at')")
    assert ("UPDATED", "farmer", 10, "first_name", "Abebe10", "X") in rows
    assert world.progress()["solo-10"] == "LOADED"
    assert world.one("SELECT first_name FROM g2p_register_farmers WHERE first_name = 'X'") == "X"


def test_what_the_registry_fills_is_kept(world):
    start(world)
    number = world.one("SELECT functional_record_id FROM g2p_register_farmers WHERE first_name = 'Abebe10'")
    world.rows("UPDATE g2p_register_farmers SET functional_record_id = 'FR-77' WHERE first_name = 'Abebe10'")
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    world.migrate()
    assert number and world.one("SELECT functional_record_id FROM g2p_register_farmers WHERE first_name = 'X'") == "FR-77"


def test_a_household_the_registry_edited_is_a_conflict(world):
    start(world)
    world.edited("farmers", "first_name = 'Abebe10'")
    world.rows("UPDATE g2p_register_farmers SET first_name = 'Staff' WHERE first_name = 'Abebe10'")
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    world.source("UPDATE res_partner SET given_name = 'Y' WHERE id = 11")
    code, out = world.migrate()
    assert code == 3 and "--resolve" in out, out[-3000:]
    assert world.progress()["solo-10"] == "CONFLICT" and world.progress()["solo-11"] == "LOADED"
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE first_name = 'Staff'") == 1
    assert world.issues("conflict")[0][0] == "solo-10"
    assert world.statuses()[-1] == "COMPLETED_WITH_CONFLICTS"
    assert world.migrate()[0] == 3  # still a conflict
    code, out = world.run("--resolve", "solo-10")
    assert code == 0, out[-2000:]
    assert world.progress()["solo-10"] == "LOADED" and not world.issues("conflict")
    assert world.migrate()[0] == 0
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE first_name = 'Staff'") == 1
    world.source("UPDATE res_partner SET given_name = 'Z' WHERE id = 10")  # changed again: a conflict again
    assert world.migrate()[0] == 3


def test_a_removal_in_a_household_the_registry_edited_is_a_conflict(world):
    start(world)
    world.edited("farmers", "first_name = 'Abebe10'")
    world.source("UPDATE res_partner SET active = false WHERE id = 10")
    code, out = world.migrate()
    assert code == 3, out[-3000:]
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE record_status = 'INACTIVE'") == 0
    assert world.issues("conflict")
    world.run("--resolve", "solo-10")
    assert not world.issues("conflict") and world.migrate()[0] == 0
    assert world.one("SELECT count(*) FROM migration.migrated_record WHERE removed_run_id = 'KEPT'") > 0
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE record_status = 'INACTIVE'") == 0


def test_a_removed_farmer_is_inactive_not_deleted(world):
    start(world)
    n = world.counts()
    world.source("UPDATE res_partner SET active = false WHERE id = 10")
    assert world.migrate()[0] == 0
    assert world.counts() == n
    assert world.rows("SELECT DISTINCT record_status FROM g2p_register_farmer_phones p JOIN migration.migrated_record m "
                      "ON m.gen2_id = p.internal_record_id WHERE m.kind = 'phone' AND m.odoo_id = 10") == [("INACTIVE",)]
    assert world.progress()["solo-10"] == "REMOVED"
    world.source("UPDATE res_partner SET active = true WHERE id = 10")  # back
    assert world.migrate()[0] == 0
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE record_status = 'INACTIVE'") == 0
    assert world.progress()["solo-10"] == "LOADED"
    assert world.one("SELECT count(*) FROM migration.change WHERE action = 'ACTIVE_AGAIN'") > 0


def test_only_all_sets_inactive(world):
    start(world)
    world.source("UPDATE res_partner SET active = false WHERE id = 10")
    world.source("DELETE FROM g2p_land_information WHERE id = 111")
    assert world.migrate("--ids", "11")[0] == 0
    assert world.one("SELECT count(*) FROM migration.migrated_record WHERE removed_run_id IS NOT NULL") == 0
    assert world.one("SELECT count(*) FROM migration.migrated_record WHERE orphaned") == 1  # the land, until --all


def test_a_dry_run_changes_nothing(world):
    start(world)
    before = world.contents()
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    world.source("UPDATE res_partner SET active = false WHERE id = 11")
    code, out = world.migrate("--all", "--dry-run")
    assert code == 0, out[-3000:]
    assert world.contents() == before and world.one("SELECT count(*) FROM migration.change") == 0
    assert "updated from farmer profile" in out


def test_the_sql_file_refuses_updates(world):
    start(world)
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    code, out = world.migrate("--all", "--sql-out")
    assert code == 1 and "only adds records" in out


@pytest.mark.parametrize("fault", ["kill_before_commit:1", "kill_after_commit:1"])
def test_a_killed_update_goes_on(world, fault):
    start(world)
    CHANGES["joins a household"](world)
    CHANGES["another name"](world)
    world.migrate("--all", "--batch-size", "10", fault=fault)
    assert world.migrate()[0] == 0
    assert active(world) == fresh(world)


def test_scores_are_computed_again(world):
    world.rows("UPDATE g2p_register_definitions SET completion_score_required = true WHERE register_mnemonic = 'Farmer'")
    section = {"section_id": "s1", "register_id": "r-f", "section_register_id": "r-f", "is_list": False}
    for column, kind in world.rows("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = "
                                   "'g2p_register_sections' AND is_nullable = 'NO' AND column_default IS NULL"):
        section.setdefault(column, False if kind == "boolean" else 0 if kind in ("integer", "numeric", "double precision", "bigint", "smallint", "real") else "s1")
    world.rows(f"INSERT INTO g2p_register_sections ({', '.join(section)}) VALUES ({', '.join(['%s'] * len(section))})",
               *section.values())
    try:
        start(world)
        world.rows("UPDATE g2p_completion_score_computation_queue SET compute_status = 'COMPLETED'")
        world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
        world.migrate()
        assert world.one("SELECT count(*) FROM g2p_completion_score_computation_queue WHERE compute_status = 'PENDING'") == 1
    finally:
        world.rows("UPDATE g2p_register_definitions SET completion_score_required = false")


def test_verify_and_health_after_a_rerun(world):
    start(world)
    CHANGES["joins a household"](world)
    CHANGES["a farmer archived"](world)
    world.migrate()
    code, out = world.verify()
    assert code == 0, out[-4000:]
    world.health()
    assert world.measured("Out of scope since, set inactive", "farmer")[0] == 1
    assert world.measured("Out of scope since, still active", "farmer")[2] == "GREEN"
    assert world.measured("Conflicts not settled", "household")[2] == "GREEN"
    # a removal not brought yet is red
    world.source("UPDATE res_partner SET active = false WHERE id = 12")
    world.health()
    assert world.measured("Out of scope since, still active", "farmer")[2] == "RED"
    # an edit in the registry is not a difference for verify
    world.migrate()
    world.edited("farmers", "first_name = 'Abebe13'")
    world.rows("UPDATE g2p_register_farmers SET first_name = 'Staff' WHERE first_name = 'Abebe13'")
    code, out = world.verify()
    assert code == 0 and "edited in the registry" in out, out[-4000:]


def test_the_report_lists_them(world):
    start(world)
    world.edited("farmers", "first_name = 'Abebe12'")
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id IN (10, 12)")
    world.source("UPDATE res_partner SET active = false WHERE id = 11")
    world.migrate()
    wb = openpyxl.load_workbook(world.folder() / "migration-report.xlsx")
    assert wb["Conflicts"]["A2"].value == "solo-12"
    assert any(r[2].value == "UPDATED" and r[6].value == "first_name" for r in wb["Updated"].iter_rows(min_row=2))
    assert any(r[2].value == "SET_INACTIVE" for r in wb["Set inactive"].iter_rows(min_row=2))


def conflicts(world, *ids):
    """These farmers edited in the registry, and changed in Gen1."""
    for i in ids:
        world.edited("farmers", f"first_name = 'Abebe{i}'")
        world.rows(f"UPDATE g2p_register_farmers SET first_name = 'Staff{i}' WHERE first_name = 'Abebe{i}'")
        world.source(f"UPDATE res_partner SET given_name = 'Gen1{i}' WHERE id = {i}")
    assert world.migrate()[0] == 3


def test_resolve_takes_several_households(world):
    start(world)
    conflicts(world, 10, 11, 12)
    code, out = world.run("--resolve", "solo-10", "solo-11")
    assert code == 0, out[-2000:]
    assert [k for k, _ in world.issues("conflict")] == ["solo-12"]
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE first_name LIKE 'Staff%'") == 3


def test_overwrite_writes_gen1_over_the_edits(world):
    start(world)
    conflicts(world, 10, 11, 12)
    code, out = world.run("--overwrite", "solo-10", "solo-11")
    assert code == 0, out[-3000:]
    names = {r[0] for r in world.rows("SELECT first_name FROM g2p_register_farmers")}
    assert {"Gen110", "Gen111", "Staff12"} <= names and "Staff10" not in names
    assert [k for k, _ in world.issues("conflict")] == ["solo-12"]
    assert world.progress()["solo-10"] == "LOADED"
    assert ("OVERWRITTEN", "first_name", "Staff10", "Gen110") in world.rows(
        "SELECT action, field, old_value, new_value FROM migration.change")
    # the edits before the overwrite count no more: a later change in Gen1 is brought
    world.source("UPDATE res_partner SET given_name = 'Later' WHERE id = 10")
    assert world.migrate()[0] == 3  # solo-12 is still a conflict
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE first_name = 'Later'") == 1
    # a new edit after it does
    world.edited("farmers", "first_name = 'Later'")
    world.source("UPDATE res_partner SET given_name = 'Again' WHERE id = 10")
    world.migrate()
    assert world.progress()["solo-10"] == "CONFLICT"


def test_overwrite_sets_inactive_what_gen1_no_longer_has(world):
    start(world)
    world.edited("farmers", "first_name = 'Abebe10'")
    world.source("UPDATE res_partner SET active = false WHERE id = 10")
    assert world.migrate()[0] == 3
    code, out = world.run("--overwrite", "solo-10")
    assert code == 0, out[-3000:]
    assert world.one("SELECT count(*) FROM g2p_register_farmers WHERE record_status = 'INACTIVE'") == 1
    assert not world.issues("conflict") and world.migrate()[0] == 0


def test_overwrite_refuses_an_unknown_household(world):
    start(world)
    code, out = world.run("--overwrite", "household-777")
    assert code == 1 and "no such household" in out
