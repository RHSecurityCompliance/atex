import os
from pathlib import Path

import pytest

# used for testing via podman containers
IMAGES = {
    "fedora": "registry.fedoraproject.org/fedora:latest",
    "centos10": "quay.io/centos/centos:stream10",
    "centos9": "quay.io/centos/centos:stream9",
    "centos8": "quay.io/centos/centos:stream8",
    "centos7": "quay.io/centos/centos:centos7.9.2009",
}
DEFAULT_IMAGE = "fedora"


# change CWD for each test to the directory containing the test_*.py file
# (don't use the cleaner monkeypatch, it doesn't apply to setup fixtures)
@pytest.fixture(autouse=True, scope="module")
def change_test_dir(request):
    old_cwd = Path.cwd()
    os.chdir(request.path.parent)
    yield
    os.chdir(old_cwd)
