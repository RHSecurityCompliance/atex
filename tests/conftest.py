import os
from pathlib import Path

import pytest


# change CWD for each test to the directory containing the test_*.py file
# (don't use the cleaner monkeypatch, it doesn't apply to setup fixtures)
@pytest.fixture(autouse=True, scope="module")
def change_test_dir(request):
    old_cwd = Path.cwd()
    os.chdir(request.path.parent)
    yield
    os.chdir(old_cwd)
