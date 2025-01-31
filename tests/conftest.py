import os
import pytest

from pathlib import Path


# change CWD for each test to the directory containing the test_*.py file
# (don't use the cleaner monkeypatch, it doesn't apply to setup fixtures)
@pytest.fixture(autouse=True, scope="module")
def change_test_dir(request):
    old_cwd = Path.cwd()
    # request.fspath is a py.path.local, its str() is the filesystem path
    os.chdir(str(request.fspath.dirname))
    yield
    os.chdir(old_cwd)
