# Podman Connection

This wraps `podman exec` in a [Connection](..) API, running commands inside
a running Podman container. Again - note that this doesn't start containers
(`podman start` or `podman run`), it just executes within already-running ones.

Extra care is taken to run `rsync` correctly and pass its arguments too.

Since `podman exec` just unshares / sets Linux Namespaces, this does not require
any functional network, sshd, etc. in the container.

The `.connect()` and `.disconnect()` methods are a no-op.

```python
with PodmanConnection("container_name_or_id"):
    c.cmd(["ls", "/"])
    ...
```
