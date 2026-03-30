> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# Podman Provisioner

This creates podman containers on the local OS and provides the Provisioner
API for them.

```python
with PodmanProvisioner("fedora:latest") as p:
    p.provision(3)
    for _ in range(3):
        remote = p.get_remote()
        remote.cmd(["cat", "/etc/passwd"])
        remote.release()
```

This works by running some background command (customizable as `run_command`
passed to `__init__()`) to keep the container alive while `.cmd()` calls run
on the running container.

Note that `podman exec`, **not ssh**, is used for `.cmd()` and `.rsync()`,
allowing you to run commands even in network-less containers.

## Pre-built images

Given that `.rsync()` needs `rsync` on the container and that re-installing
it via `dnf` every time is very costly, it's a good idea to pre-build an image
with it included, and pass that image to the Provisioner.

```python
from atex.provisioner.podman import build_container_with_deps, pull_image

pulled = pull_image("fedora:latest")
custom_image = build_container_with_deps(pulled)

with PodmanProvisioner(custom_image) as p:
    ...

subprocess.run(("podman", "image", "rm", "-f", custom_image), check=True)
```

See docstrings of these functions for more options.

## Systemd

To boot up a container with full systemd init, pre-build an image with systemd,
and pass it to the Provisioner.

```python
from atex.provisioner.podman import build_container_with_deps, pull_image

pulled = pull_image("fedora:latest")
custom_image = build_container_with_deps(
    pulled,
    extra_pkgs=["systemd"],
    extra_content=(
        # these tend to cause issues in containers, allegedly
        "RUN systemctl mask "
        "systemd-oomd systemd-resolved systemd-hostnamed"
    ),
)

p = PodmanProvisioner(
    custom_image,
    run_options=["--systemd=always", "--restart=always"],
    run_command=["/sbin/init"],
)

with p:
    ...
```

This loosely follows various web sources for how to run systemd under podman.

## Using remote podman hosts

Podman can talk to remote hosts using a REST API and the `--remote` and
`--connection` CLI options. Since this Provisioner is just a wrapper around this
CLI, you can pass them via `run_options` just fine.
