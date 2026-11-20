import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("REGISTRY_EXTENSION_MODULE", "openg2p_registry_farmer_extension")


@pytest.fixture(scope="session")
def models():
    import importlib
    import migrate
    migrate.init_registry()
    return importlib.import_module("openg2p_registry_extensions.register_domain.models")


@pytest.fixture(scope="session")
def pack_root():
    root = os.environ.get("PACK_ROOT", "/pack/packs")
    if not Path(root).is_dir():
        pytest.skip(f"no country pack at {root}")
    return root
