"""migrated_record: every record's id in farmer profile and in the registry."""


def fill(world):
    """A household of three, a farmer in none, crops, a phone that cannot be read and a crop without a land."""
    world.farmers(4)
    world.household(9001, 1, 2, 3)
    world.source("INSERT INTO g2p_crop_information (id, partner_id) VALUES (64, 1), (65, 4)")
    world.source("INSERT INTO g2p_phone_number (id, partner_id, phone_no) VALUES (900, 1, '12')")
    world.farmers(1, 500)
    world.source("DELETE FROM g2p_land_information WHERE partner_id = 500")
    world.source("INSERT INTO g2p_crop_information (id, partner_id) VALUES (66, 500)")


def kinds(world):
    return dict(world.rows("SELECT kind, count(*) FROM migration.migrated_record GROUP BY 1"))


def test_every_record_has_both_ids(world):
    fill(world)
    code, out = world.migrate()
    assert code == 0, out[-3000:]
    assert world.unlinked() == ([], [])
    assert kinds(world) == {"household": 1, "farmer": 5, "member": 3, "phone": 5, "land": 8, "crop": 2,
                            "solo_household": 2, "solo_member": 2}
    # what is not migrated has no row
    assert world.rows("SELECT 1 FROM migration.migrated_record WHERE (kind, odoo_id) IN (('phone', 900), ('crop', 66))") == []


def test_one_id_is_found_from_the_other(world):
    fill(world)
    world.migrate()
    lookup = "SELECT r.{} FROM migration.migrated_record m JOIN g2p_register_{} r ON r.internal_record_id = m.gen2_id " \
             "WHERE m.kind = %s AND m.odoo_id = %s"
    assert world.one(lookup.format("first_name", "farmers"), "farmer", 2) == "Abebe2"
    assert world.one(lookup.format("land_id", "lands"), "land", 21) == "L2-1"
    assert world.one(lookup.format("phone_number", "farmer_phones"), "phone", 3) == "911000003"
    assert world.one(lookup.format("first_name", "household_members"), "member", 9001002) == "Abebe2"
    assert world.one(lookup.format("household_head", "households"), "household", 9001).startswith("Abebe1")
    assert world.one(lookup.format("household_head", "households"), "solo_household", 4).startswith("Abebe4")
    assert world.one(lookup.format("first_name", "household_members"), "solo_member", 4) == "Abebe4"
    back = "SELECT m.kind, m.odoo_id FROM migration.migrated_record m JOIN g2p_register_{} r " \
           "ON r.internal_record_id = m.gen2_id WHERE r.{} = %s"
    assert world.rows(back.format("farmers", "first_name"), "Abebe2") == [("farmer", 2)]
    assert world.rows(back.format("lands", "land_id"), "L2-1") == [("land", 21)]
    # a crop is on the land it was put on
    assert world.one("SELECT l.land_id FROM migration.migrated_record m JOIN g2p_register_crops c ON c.internal_record_id "
                     "= m.gen2_id JOIN g2p_register_lands l ON l.internal_record_id = c.link_internal_record_id "
                     "WHERE m.kind = 'crop' AND m.odoo_id = 64") == "L1-1"


def test_a_failed_household_has_none_until_it_loads(world):
    fill(world)
    world.source("UPDATE res_partner SET birthdate = '20023-01-01' WHERE id = 2")
    assert world.migrate()[0] == 3
    assert "household" not in kinds(world) and world.unlinked() == ([], [])
    world.source("UPDATE res_partner SET birthdate = '1980-01-01' WHERE id = 2")
    assert world.migrate()[0] == 0
    assert kinds(world)["member"] == 3 and world.unlinked() == ([], [])


def test_a_changed_household_keeps_the_ones_it_has(world):
    fill(world)
    world.migrate()
    before = world.contents()
    world.source("INSERT INTO g2p_land_information (id, partner_id, total_land_area) VALUES (9999, 4, 2)")
    world.migrate()
    assert world.progress()["solo-4"] == "CHANGED" and world.contents() == before


def test_adopted_data_gets_them(world):
    fill(world)
    world.migrate()
    before = world.contents()
    world.rows("DROP SCHEMA migration CASCADE")
    assert world.migrate()[0] == 0
    assert world.contents() == before and world.unlinked() == ([], [])
