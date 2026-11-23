"""The field map names only Gen2 columns that exist, and every column the
transform writes is accounted for in it."""
from farmer_profile import fieldmap as F


def test_every_named_gen2_column_exists(models):
    missing = []
    for (model, field), entry in F.SOURCE.items():
        for target in entry["targets"]:
            register, column = target.split(".")
            cls = getattr(models, f"G2PRegister{register}", None)
            if cls is None or column not in cls.__table__.columns:
                missing.append(f"{model}.{field} -> {target}")
    for register, column in F.TARGET:
        if column not in getattr(models, f"G2PRegister{register}").__table__.columns:
            missing.append(f"TARGET {register}.{column}")
    assert not missing, missing


def test_registers_exist(models):
    for register in F.REGISTERS:
        assert hasattr(models, f"G2PRegister{register}")


def test_unknown_field_is_unreviewed_and_odoo_field_is_technical():
    assert F.source_status("res.partner", "brand_new_field", ["g2p_ati"])["status"] == F.UNREVIEWED
    assert F.source_status("res.partner", "color", ["base"])["status"] == F.TECHNICAL
    assert F.source_status("res.partner", "given_name", ["g2p_ati"])["status"] == F.MIGRATED
