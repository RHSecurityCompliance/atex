> [!NOTE]
> This describes a specific implementation of the abstract Connection API.
> See also the [documentation of the generic API](..).

# Podman Connection

This wraps a `podman exec` style command in a [Connection](..) API, running
commands inside a running Podman container. Again - note that this doesn't
start containers (`podman start` or `podman run`), it just executes within
already-running ones.

Extra care is taken to run `rsync` correctly and pass its arguments too.

Since we're just executing commands across Linux Namespaces, this Connection
does not require any functional network, sshd, etc. in the container.

```python
from atex.connection.podman import PodmanConnection

with PodmanConnection("container_name_or_id") as c:
    c.cmd(["ls", "/"])
    ...
```

The actual implementation does not use `podman exec` due to it being a "heavy"
way of running commands, using session tracking and "conmon", which breaks
SIGPIPE handling - instead, it uses `crun exec` to run commands as directly
as possible, wrapped in `systemd-run` to enter the container's cgroup, exactly
like `podman exec` and its "conmon" would have done.

## Systemd-aware version

A SystemdPodmanConnection further adds waiting for OS bootup, supporting
container reboot use cases.

Obviously, it only works on systemd-enabled containers where systemd is used
as an init system.
