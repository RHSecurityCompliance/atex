> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# AnyConnectionProvisioner

A simple Provisioner that is effectively just a wrapper around a Connection
class, providing the Provisioner API.

```python
from atex.provisioner.anyconn import AnyConnectionProvisioner
from atex.connection.local import LocalConnection

with AnyConnectionProvisioner(LocalConnection) as p:
    p.provision(1)
    remote = p.get_remote()
    remote.cmd(("echo", "hello world"))
    remote.release()
```

It takes a Connection type and its constructor arguments. The returned Remote
inherits from both `Remote` and the connection type, so `isinstance()` checks
for the connection type work as expected. `.release()` simply calls
`.disconnect()` and frees the remote.

If you need to parametrize the creation process, pass `conn_args` and/or
`conn_kwargs`:

```python
from atex.provisioner.anyconn import AnyConnectionProvisioner
from atex.connection.ssh import StatelessSSHConnection

opts = {"Hostname": "foo.bar", "User": "root", "IdentityFile": "/tmp/key"}

with AnyConnectionProvisioner(StatelessSSHConnection, conn_args=(opts,)) as p:
    ...
```

This is mainly useful for:

- Testing any code that consumes the Provisioner API but doesn't need actual
  remote systems.

- Passing Connections (e.g. ManagedSSHConnection) to a pre-existing remote OS,
  to an Orchestrator, to run tests in parallel across those connections.
