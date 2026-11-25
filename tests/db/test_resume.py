"""Stops, crashes, bad records and changes: what a rerun finds and leaves."""
import csv
import signal
import time

import pytest

SMALL = ("--all", "--batch-size", "50", "--workers", "2")


@pytest.fixture
def reference(world):
    """The tables after an uninterrupted run over 200 farmers and two households."""
    def fill():
        world.farmers(200)
        world.household(9001, 1, 2, 3)
        world.household(9002, 4, 5)
    fill()
    code, out = world.migrate(*SMALL)
    assert code == 0, out[-3000:]
    contents, queued = world.contents(), world.one("SELECT count(*) FROM g2p_functional_id_generation_queue")
    world.reset()
    fill()
    return contents, queued


@pytest.mark.parametrize("fault", ["kill_mid_insert:3", "kill_before_commit:1", "kill_before_commit:3",
                                   "kill_after_commit:2", "kill_in_finalize"])
def test_a_killed_run_goes_on_where_it_stopped(world, reference, fault):
    contents, queued = reference
    code, _ = world.migrate(*SMALL, fault=fault)
    assert code == -signal.SIGKILL
    before = {k for k, s in world.progress().items() if s == "LOADED"}
    assert world.one("SELECT count(*) FROM g2p_register_households") == \
        sum(1 for k in before if k.startswith("solo-")) + world.one(
            "SELECT count(*) FROM migration.migrated_record WHERE kind = 'household'")  # progress and data agree
    prepared = world.tmp / "prepared"
    assert world.unlinked() == ([], [])
    code, out = world.migrate(*SMALL, COUNT_PREPARED=str(prepared))
    assert code == 0, out[-3000:]
    assert world.contents() == contents
    assert world.one("SELECT count(*) FROM g2p_functional_id_generation_queue") == queued
    again = set(prepared.read_text().split()) if prepared.exists() else set()
    assert not again & before and len(again | before) == 197
    assert world.statuses() == ["INTERRUPTED", "COMPLETED"]


def test_the_same_command_twice_adds_nothing(world, reference):
    world.migrate(*SMALL)
    first, queued = world.contents(), world.one("SELECT count(*) FROM g2p_functional_id_generation_queue")
    code, _ = world.migrate(*SMALL)
    assert code == 0 and world.contents() == first
    assert world.one("SELECT count(*) FROM g2p_functional_id_generation_queue") == queued
    assert world.summary()["households"]["already in"] == 197


def test_two_runs_at_once(world):
    world.farmers(200)
    first = world.start(*SMALL, fault="slow:30")  # long enough for two more to start and be refused
    deadline = time.time() + 200
    while time.time() < deadline and not world.one("SELECT to_regclass('migration.run') IS NOT NULL"):
        time.sleep(0.2)
    while time.time() < deadline and not world.one("SELECT count(*) FROM migration.run"):
        time.sleep(0.2)
    code, out = world.migrate(*SMALL)
    assert code == 1 and "another migration run is active" in out
    code, out = world.migrate("--finalize-only")
    assert code == 1 and "another migration run is active" in out
    assert first.poll() is None  # it was still going
    assert world.wait(first)[0] == 0
    assert world.counts()["farmers"] == 200
    assert world.one("SELECT count(*) - count(DISTINCT internal_record_id) FROM g2p_functional_id_generation_queue") == 0


def test_sigterm_finishes_the_batch_and_reports(world):
    world.farmers(200)
    code, out = world.migrate(*SMALL, fault="term_in_batch:2")
    assert code == 1, out[-2000:]
    assert world.counts()["farmers"] == 100
    assert world.statuses() == ["STOPPED"]
    for name in ("summary.txt", "summary.json", "migration-report.xlsx", "issues.csv"):
        assert (world.folder() / name).exists()
    assert world.summary()["households"]["remaining"] == 100
    assert world.migrate(*SMALL)[0] == 0 and world.counts()["farmers"] == 200


def test_a_dead_worker_is_noticed(world):
    world.farmers(200)
    code, out = world.migrate(*SMALL, fault="worker:solo-70")  # fails if it hangs
    assert code == 1 and "a worker process died twice" in out
    assert world.statuses() == ["FAILED"] and "FAILED" not in world.progress().values()
    assert world.migrate(*SMALL)[0] == 0 and world.counts()["farmers"] == 200


def test_a_worker_that_dies_once_costs_nothing(world):
    world.farmers(200)
    code, out = world.migrate(*SMALL, fault="worker_once:solo-70", COUNT_PREPARED=str(world.tmp / "c"))
    assert code == 0, out[-2000:]
    assert world.counts()["farmers"] == 200


@pytest.mark.parametrize("fault", ["lose_connection:2", "lose_answer:2"])
def test_a_lost_database_connection_is_retried(world, fault):
    world.farmers(200)
    code, out = world.migrate(*SMALL, fault=fault)
    assert code == 0, out[-3000:]
    assert world.counts()["farmers"] == 200 and set(world.progress().values()) == {"LOADED"}


def test_one_bad_record_costs_one_household(world):
    world.farmers(2000)
    world.household(9001, 700, 701)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 700")  # no driver reads this
    code, out = world.migrate("--all")
    assert code == 3, out[-3000:]
    assert world.counts()["farmers"] == 1998
    assert world.progress()["household-9001"] == "FAILED"
    failed = world.issues("failed")
    assert [k for k, _ in failed] == ["household-9001"] and "year" in failed[0][1]
    # what loaded is queued although a household failed
    assert world.one("SELECT count(*) FROM g2p_functional_id_generation_queue WHERE register_id = 'r-f'") == 1998
    assert "household-9001" in (world.folder() / "summary.txt").read_text()
    assert world.statuses() == ["COMPLETED_WITH_FAILURES"]
    # still bad: tried again, still one issue
    assert world.migrate("--all")[0] == 3 and len(world.issues("failed")) == 1
    assert world.one("SELECT attempts FROM migration.household_progress WHERE household_key = 'household-9001'") == 2
    world.source("UPDATE res_partner SET birthdate = '1980-01-01' WHERE id = 700")
    assert world.migrate("--all")[0] == 0
    assert world.counts()["farmers"] == 2000 and world.progress()["household-9001"] == "LOADED"
    assert not world.issues("failed") and len(world.issues("failed", "RESOLVED")) == 1


def test_a_value_the_registry_refuses_costs_one_household(world):
    world.farmers(200)
    world.source("UPDATE res_partner SET farmer_id = 'FR-1' WHERE id IN (70, 71)")
    code, out = world.migrate(*SMALL)
    assert code == 3, out[-2000:]
    assert world.counts()["farmers"] == 199
    (key, reason), = world.issues("failed")
    assert key in ("solo-70", "solo-71") and "functional_record_id" in reason


def test_a_fault_in_every_record_stops_the_run(world):
    world.farmers(200)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01'")
    code, out = world.migrate(*SMALL, "--max-failures", "20")
    assert code == 1 and "--max-failures" in out and world.statuses() == ["FAILED"]
    assert world.one("SELECT count(*) FROM migration.household_progress WHERE status = 'FAILED'") == 50


def test_stop_on_error(world):
    world.farmers(200)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 70")
    code, _ = world.migrate(*SMALL, "--stop-on-error")
    assert code == 1 and world.counts()["farmers"] == 99


def test_a_missing_gen1_column_is_nobodys_fault(world):
    world.farmers(60)
    world.source("ALTER TABLE g2p_phone_number RENAME phone_no TO phone_gone")
    try:
        code, out = world.migrate(*SMALL)
    finally:
        world.source("ALTER TABLE g2p_phone_number RENAME phone_gone TO phone_no")
    assert code == 1 and "could not be prepared" in out and not world.progress()


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
    "another name": lambda w: w.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10"),
}


@pytest.mark.parametrize("change", CHANGES)
def test_what_changed_since_it_was_migrated_is_reported_not_touched(world, change):
    world.farmers(60)
    world.household(9001, 1, 2)
    assert world.migrate()[0] == 0
    before = world.contents()
    CHANGES[change](world)
    code, out = world.migrate()
    assert code == 0, out[-2000:]
    # a farmer who left is a household of their own now: not loaded twice either
    assert world.contents() == before
    assert "CHANGED" in world.progress().values() and world.issues("changed")
    assert world.rows("SELECT link_internal_record_id FROM g2p_register_household_members WHERE is_head "
                      "GROUP BY 1 HAVING count(*) > 1") == []


def test_a_change_that_is_undone_is_no_change(world):
    world.farmers(60)
    world.migrate()
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")
    world.migrate()
    assert world.progress()["solo-10"] == "CHANGED"
    assert "(farmers)" in world.issues("changed")[0][1]
    world.source("UPDATE res_partner SET given_name = 'Abebe10' WHERE id = 10")
    world.migrate()
    assert world.progress()["solo-10"] == "LOADED" and not world.issues("changed")


def test_a_migrated_record_that_cannot_be_read_any_more_is_not_failed(world):
    world.farmers(60)
    world.migrate()
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    assert world.migrate()[0] == 0
    assert world.progress()["solo-10"] == "CHANGED" and not world.issues("failed")
    assert "cannot be read" in world.issues("changed")[0][1]


def test_odoos_own_bookkeeping_is_no_change(world):
    world.farmers(60)
    world.migrate()
    world.source("UPDATE res_partner SET write_date = now(), age_int = 46")
    world.source("UPDATE g2p_land_information SET write_date = now()")
    world.migrate()
    assert set(world.progress().values()) == {"LOADED"}


def test_a_new_household_still_loads(world):
    world.farmers(60)
    world.migrate()
    world.farmers(2, 500)
    world.household(9001, 500, 501)
    assert world.migrate()[0] == 0
    assert world.counts()["farmers"] == 62 and world.progress()["household-9001"] == "LOADED"


def test_another_farmer_profile_database_is_refused(world):
    world.farmers(60)
    world.migrate()
    world.source("UPDATE ir_config_parameter SET value = 'another'")
    world.farmers(1, 500)
    code, out = world.migrate()
    assert code == 1 and "another farmer profile database" in out and world.counts()["farmers"] == 60
    assert world.migrate("--all", "--dry-run")[0] == 1
    assert world.migrate("--all", "--accept-source", "wrong")[0] == 1
    assert world.migrate("--all", "--accept-source", "another")[0] == 0 and world.counts()["farmers"] == 61


def test_data_from_before_the_tables_is_adopted(world):
    world.farmers(60)
    world.household(9001, 1, 2)
    world.migrate()
    before = world.contents()
    world.rows("DROP SCHEMA migration CASCADE")
    assert world.migrate()[0] == 0
    assert world.contents() == before and set(world.progress().values()) == {"LOADED"}
    assert world.one("SELECT bool_and(adopted) FROM migration.household_progress")
    # and when only some of a household is there
    world.rows("DROP SCHEMA migration CASCADE")
    world.rows("DELETE FROM g2p_register_lands WHERE land_id = 'L10-1'")
    world.migrate()
    assert world.progress()["solo-10"] == "CHANGED" and world.counts()["lands"] == 119
    assert "partly in the registry" in world.issues("changed")[0][1]


def test_a_farmer_in_two_households_is_one_unit(world):
    world.farmers(6)
    world.household(9002, 3, 4)
    world.household(9001, 1, 2, 3, head=1)
    assert world.migrate("--ids", "4")[0] == 0   # whole, whoever was asked for
    assert world.counts() == {**world.counts(), "farmers": 4, "households": 2, "household_members": 5}
    assert list(world.progress()) == ["household-9001"]
    assert any("several households" in r for _, r in world.issues("check"))
    # linked to the lowest household id
    from farmer_profile.transform import record_id
    assert world.one("SELECT link_internal_record_id FROM g2p_register_farmers WHERE internal_record_id = %s",
                     record_id("farmer", 3)) == record_id("household", 9001)


def test_a_farmer_marked_not_head_is_reported(world):
    world.farmers(2)
    world.source("UPDATE res_partner SET hh_is_household_head = 'no' WHERE id = 1")
    world.migrate()
    assert [k for k, r in world.issues("check") if "not the household head" in r] == ["solo-1"]


def test_a_dry_run_keeps_nothing(world):
    world.farmers(60)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    code, out = world.migrate("--all", "--dry-run")
    assert code == 3, out[-2000:]
    assert world.counts()["farmers"] == 0 and world.one("SELECT to_regclass('migration.run') IS NULL")
    rows = list(csv.DictReader(open(world.folder() / "issues.csv")))
    assert [r["household"] for r in rows if r["severity"] == "failed"] == ["solo-10"]


def test_the_sql_file(world):
    world.farmers(60)
    world.household(9001, 1, 2)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    code, out = world.migrate("--all", "--sql-out")
    assert code == 3 and world.counts()["farmers"] == 0, out[-2000:]
    path = world.folder() / "migration.sql"

    def psql():
        return world.apply(path)
    assert psql() is None
    assert world.unlinked() == ([], [])
    assert world.counts()["farmers"] == 59 and world.progress()["solo-10"] == "FAILED"
    before = world.contents()
    assert "already been applied" in psql() and world.contents() == before
    # a direct run goes on from it
    world.source("UPDATE res_partner SET birthdate = '1980-01-01' WHERE id = 10")
    assert world.migrate("--all")[0] == 0 and world.counts()["farmers"] == 60
    # a file written before something else was migrated
    world.farmers(1, 500)
    world.migrate("--all", "--sql-out")
    path = world.folder() / "migration.sql"
    world.farmers(1, 501)
    world.migrate("--ids", "501")
    assert "write it again" in psql() and world.counts()["farmers"] == 61


def test_a_household_that_failed_and_is_gone_is_retired(world):
    world.farmers(60)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    world.migrate()
    world.source("UPDATE res_partner SET active = false WHERE id = 10")
    assert world.migrate()[0] == 0
    assert "solo-10" not in world.progress() and not world.issues("failed")


def test_status(world):
    code, out = world.migrate("--status")
    assert code == 0 and "nothing has been migrated" in out
    world.farmers(60)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    world.migrate()
    code, out = world.migrate("--status")
    assert code == 0 and "failed 1" in out and "COMPLETED_WITH_FAILURES" in out


def test_the_report(world):
    import openpyxl
    world.farmers(60)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 10")
    world.migrate()
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 11")
    world.migrate()
    wb = openpyxl.load_workbook(world.folder() / "migration-report.xlsx")
    assert wb.sheetnames == ["Health", "Summary", "Failed households", "Changed in Gen1", "Issues summary", "Issues", "Runs",
                             "Batches", "Mapping - Gen1 fields", "Mapping - Gen2 columns", "Mapping - key"]
    assert wb["Failed households"]["A2"].value == "solo-10"
    assert wb["Changed in Gen1"]["A2"].value == "solo-11"
    assert wb["Runs"].max_row == 3


def test_verify(world):
    world.farmers(60)
    world.household(9001, 1, 2, 3)
    world.migrate()
    code, out = world.verify()
    assert code == 0, out[-4000:]
    world.source("UPDATE res_partner SET given_name = 'X' WHERE id = 10")      # changed: a warning
    code, out = world.verify()
    assert code == 0 and "1 warnings" in out or "WARN" in out, out[-4000:]
    world.farmers(1, 500)                                                        # missing: a failure
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 500")
    world.migrate()
    code, out = world.verify()
    assert code == 1 and "no household failed" in out, out[-4000:]
