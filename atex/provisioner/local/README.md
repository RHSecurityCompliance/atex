> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# LocalProvisioner

A simple Provisioner that provides Remotes backed by
[LocalConnection](../../connection/local), running commands on the local
system. No external resources are allocated, and releasing a LocalRemote
is a no-op.

```python
from atex.provisioner.local import LocalProvisioner

with LocalProvisioner() as p:
    p.provision(1)
    remote = p.get_remote()
    remote.cmd(("echo", "hello world"))
    remote.release()
```

This is useful for testing or for any code that consumes the Provisioner
API but doesn't need actual remote systems.
