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

See also the related [PodmanConnection](../../connection/podman).

## Pre-built images

Given that `.rsync()` needs `rsync` on the container and that re-installing
it via `dnf` every time is very costly, it's a good idea to pre-build an image
with it included, and pass that image to the Provisioner.

```python
from atex.provisioner.podman import (
    pull_image,
    build_container_with_deps,
    PodmanProvisioner,
)

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
from atex.provisioner.podman import (
    pull_image,
    build_systemd_container_with_deps,
    SystemdPodmanProvisioner,
)

pulled = pull_image("fedora:latest")
custom_image = build_systemd_container_with_deps(pulled)

with SystemdPodmanProvisioner(custom_image) as p:
    ...

subprocess.run(("podman", "image", "rm", "-f", custom_image), check=True)
```

The `build_systemd_container_with_deps()` is just a wrapper around
`build_container_with_deps()` that includes systemd-specific setup.

### Automatic systemd-enabled image

If you need the image for just one Provisioner instance, use `.build_from()`
which wraps the Provisioner and its context manager in a custom image build +
removal.

```python
from atex.provisioner.podman import (
    pull_image,
    SystemdPodmanProvisioner,
)

pulled = pull_image("fedora:latest")
with SystemdPodmanProvisioner.build_from(pulled) as p:
    ...
```
