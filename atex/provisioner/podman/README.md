> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# Podman Provisioner

This creates podman containers on the local OS and provides the Provisioner
API for them.

```python
from atex.provisioner.podman import PodmanProvisioner

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
import subprocess

from atex.provisioner.podman import (
    PodmanProvisioner,
    build_container_with_deps,
    pull_image,
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
import subprocess

from atex.provisioner.podman import (
    SystemdPodmanProvisioner,
    build_systemd_container_with_deps,
    pull_image,
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
    SystemdPodmanProvisioner,
    pull_image,
)

pulled = pull_image("fedora:latest")
with SystemdPodmanProvisioner.build_from(pulled) as p:
    ...
```

## Multiple provisioner instances and `isolate=True`

Podman is a very buggy piece of software when it comes to parallel `podman`
commands being executed - even v6.0 has frequent race conditions and SQLite
DB corruptions. As such, **never use multiple PodmanProvisioner instances**
under a single user (or root), and even with a single one, never issue manual
`podman` commands while the ATEX-using script is running.

If you have root, the ideal solution is to add multiple unprivileged users,
and configure each PodmanProvisioner instance to use `sudo`:

```python
from atex.provisioner.podman import PodmanProvisioner

inst = PodmanProvisioner(...)
inst.podman_command = ("sudo", "-i", "-u", "foobar1", "--", "podman")
inst.crun_command = ("sudo", "-i", "-u", "foobar1", "--", "crun")
```

Otherwise, PodmanProvisioner can partially isolate its container storage
to avoid at least the DB-corrupting race conditions, at the cost of a small
slowdown during container creation:

```python
from atex.provisioner.podman import PodmanProvisioner

with PodmanProvisioner(..., isolate=True):
    ...
```

This creates a temporary directory under the regular container storage dir,
e.g. `/var/lib/containers` or `~/.local/share/containers`, and passes extra
CLI args to `podman` to use it.

## Fedora/RHEL inotify instances limit

When running many SystemdPodmanProvisioner containers with `--userns=auto`,
the default Fedora `fs.inotify.max_user_instances` limit of 128 is shared
across all containers - inotify instances in child user namespaces count
against the init namespace's ceiling via hierarchical ucounts accounting.

Each systemd instance uses ~15-20 inotify instances, so the ~9th container
fails with `EMFILE` on `inotify_init1()`, preventing D-Bus from starting.

If you want to run many systemd-enabled containers, just increase the limit
on the host:

```bash
sysctl -w fs.inotify.max_user_instances=65536
```
