import subprocess
import tempfile
from pathlib import Path

import pytest
import testutil

from atex.provisioner.podman import PodmanProvisioner, build_container_with_deps, pull_image
from tests.provisioner.test_podman import IMAGE


@pytest.fixture(scope="module")
def provisioner():
    pulled = pull_image(IMAGE)
    custom_image = build_container_with_deps(pulled)
    try:
        with PodmanProvisioner(custom_image) as prov:
            yield prov
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", custom_image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="module")
def provisioner_systemd():
    pulled = pull_image(IMAGE)

    pkgs = ("systemd",)
    content = "RUN systemctl mask systemd-oomd systemd-resolved systemd-hostnamed"
    custom_image = build_container_with_deps(pulled, extra_pkgs=pkgs, extra_content=content)

    opts = ("--systemd=always", "--restart=always")
    cmd = ("/sbin/init",)
    try:
        with PodmanProvisioner(custom_image, run_options=opts, run_command=cmd) as prov:
            yield prov
    finally:
        subprocess.run(
            ("podman", "image", "rm", "-f", custom_image),
            check=True,
            stdout=subprocess.DEVNULL,
        )


@pytest.fixture(scope="function", autouse=True)
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# safeguard against blocking API function freezing pytest
@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(300):
        yield
