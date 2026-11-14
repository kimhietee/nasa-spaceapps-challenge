import os
import tempfile
from pathlib import Path

import pytest

from firewatch.pipeline import run_pipeline


@pytest.fixture(scope="session")
def db_file():
    path = Path(tempfile.mkdtemp()) / "test.db"
    run_pipeline(None, path)
    os.environ["FIREWATCH_DB"] = str(path)
    return path
