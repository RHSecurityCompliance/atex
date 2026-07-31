import os
import subprocess
import uuid

import pytest
import testutil

from atex import util
from atex.provisioner.podman import pull_image
from tests.conftest import IMAGES


def _fixup_vault_repos(image):
    """Build an intermediate image with mirror.centos.org swapped to vault."""
    tag = str(uuid.uuid4())
    proc = subprocess.run(
        ("podman", "build", "-q", "-t", tag, "--build-arg", f"SRC_IMG={image}", "-f", "-", "."),
        input=(
            "ARG SRC_IMG\n"
            "FROM $SRC_IMG\n"
            "RUN sed -i"
            " -e 's/^mirrorlist/#mirrorlist/'"
            " -e 's/^#baseurl/baseurl/'"
            " -e 's/mirror\\.centos\\.org/vault.centos.org/'"
            " /etc/yum.repos.d/CentOS-*.repo\n"
            "RUN if command -v dnf >/dev/null; then"
            " dnf -q clean all;"
            " else"
            " yum -q clean all;"
            " fi\n"
        ),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return proc.stdout.strip()


@pytest.fixture(params=("podman", "ssh"))
def backend(request):
    return request.param


@pytest.fixture(
    scope="session",
    # allow override via user-provided BASE_IMAGE env var (name/id)
    params=(_base,) if (_base := os.environ.get("BASE_IMAGE")) else IMAGES,
)
def base_image(request):
    if base := os.environ.get("BASE_IMAGE"):
        yield base
        return
    url = IMAGES[request.param]
    pulled = pull_image(url)
    if request.param in ("centos7", "centos8"):
        fixed = _fixup_vault_repos(pulled)
        try:
            yield fixed
        finally:
            subprocess.run(
                ("podman", "image", "rm", "-f", fixed),
                check=False,
                stdout=subprocess.DEVNULL,
            )
    else:
        yield pulled


@pytest.fixture(scope="session")
def ssh_key(tmp_path_factory):
    key_dir = tmp_path_factory.mktemp("ssh")
    return util.ssh_keygen(key_dir)


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield


def pytest_collection_modifyitems(items):
    if os.environ.get("BASE_IMAGE"):
        return
    for item in items:
        # skip ssh backend on old images (slow systemd boot)
        if item.nodeid.endswith(("[centos7-ssh]", "[centos8-ssh]")):
            item.add_marker(pytest.mark.skip(
                reason="ssh backend too slow on centos7/centos8 (systemd boot)",
            ))
            continue

        if "[centos7-" in item.nodeid:
            # cgroup v1/v2 conflict with modern host kernels
            if (
                "fmf/test_reboot.py" in item.nodeid
                or "beakerlib/test_reboot.py" in item.nodeid
            ):
                item.add_marker(pytest.mark.skip(
                    reason="centos7 reboot tests fail due to cgroup v1/v2 conflict",
                ))
                continue

            # YUM exits 0 even when some packages fail to install
            if "fmf/test_pkgs.py::test_require_fail" in item.nodeid:
                item.add_marker(pytest.mark.skip(
                    reason="centos7 YUM exits 0 on partial install failure",
                ))
                continue
