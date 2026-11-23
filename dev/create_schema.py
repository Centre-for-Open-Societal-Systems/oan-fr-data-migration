"""Create the registry tables in an empty database, the way CI does.

Runs inside the registry staff-api image, with the Farmer extension importable
(see target-db.sh). TARGET_DSN names the database.
"""
import importlib
import os
import sys

from sqlalchemy import create_engine, text

sys.modules["openg2p_registry_extensions"] = importlib.import_module(os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_farmer_extension"))
importlib.import_module("openg2p_registry_staff_api.config").Settings.get_config()
importlib.import_module("openg2p_registry_extensions.app").Initializer()
from openg2p_fastapi_common.models import BaseORMModel  # noqa: E402

engine = create_engine(os.environ["TARGET_DSN"])
with engine.begin() as connection:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
BaseORMModel.metadata.create_all(engine)
print(f"created {len(BaseORMModel.metadata.tables)} tables")
