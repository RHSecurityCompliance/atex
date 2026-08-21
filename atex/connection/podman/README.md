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

## Systemd-aware version

A SystemdPodmanConnection further adds waiting for OS bootup, supporting
container reboot use cases.

Obviously, it only works on systemd-enabled containers where systemd is used
as an init system.

## Implementation notes

### Using `systemd-run` and `crun`

The actual implementation does not use `podman exec` due to it being a "heavy"
way of running commands, using session tracking and "conmon", which breaks
SIGPIPE handling - instead, it uses `crun exec` to run commands as directly
as possible.

This also neatly avoids all the /dev/shm and SQLite race condition bugs and
lock contention that parallel `podman exec` suffers from.

For rootless podman, `crun exec` is wrapped in `systemd-run --user --scope`
to place it in the user's cgroup hierarchy. This is needed because cgroup v2
process migration requires write access to `cgroup.procs` of the common
ancestor of source and destination cgroups - without the wrapper, `crun exec`
inherits the caller's cgroup, which for an unprivileged user is almost never
under the user's delegated cgroup subtree (e.g. a login session lives in
a logind-owned `session-X.scope`), so the common ancestor's `cgroup.procs`
is owned by root and the migration fails. For rootful podman, no wrapper
is needed as root has `CAP_DAC_OVERRIDE`.

### Rootless vs rootful podman vs `crun`

There's a "runtime root" directory for managing a running container across
OCI container tools.

`crun` expects it under `XDG_RUNTIME_DIR` (if defined), with a fallback
default `/run/crun`, or an override of `--root` passed via CLI.

Podman doesn't pass it to crun in any way, but it sneakily unsets
`XDG_RUNTIME_DIR` if running rootful (and not rootless), making `crun` use
`/run/crun` **even though root sessions have valid `XDG_RUNTIME_DIR`**.
That's a pretty ugly hack, but it's right there in podman's Go source.

When `crun` is spawned by a user (like us) from a valid systemd session,
it runs with `XDG_RUNTIME_DIR` set and tries to find runtime root under
`XDG_RUNTIME_DIR` which fails because it != `/run/crun`.

So the PodmanConnection tries to detect rootful/rootless operation and,
if running rootful, unset `XDG_RUNTIME_DIR` just like Podman would, to make
any `crun` executions fully compatible with Podman.
