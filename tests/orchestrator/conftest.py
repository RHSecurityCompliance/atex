import tempfile
from pathlib import Path

import pytest
import testutil


@pytest.fixture(scope="function", autouse=True)
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(60):
        yield
