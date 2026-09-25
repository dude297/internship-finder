import os
from collections.abc import Iterator

import pytest

from app.core.config import Settings, get_settings

# Tests control configuration explicitly. Done at import time, before test modules import
# app.main (which builds the app from settings), so a developer's backend/.env or shell
# variables can't change test results. The app itself still loads backend/.env normally.
Settings.model_config["env_file"] = None
for _name in Settings.model_fields:
    os.environ.pop(_name.upper(), None)


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
