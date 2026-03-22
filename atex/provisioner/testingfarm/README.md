> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# Testing Farm Provisioner

This Provisioner uses [Testing Farm](https://testing-farm.io/) by scheduling
"dummy" tests that hold systems reserved (while being almost a no-op
themselves), similarly to how the official `testing-farm reserve` CLI command
does it.

```json
with TestingFarmProvisioner("CentOS-Stream-9", max_remotes=4) as p:
    p.provision(10)
    for _ in range(10):
        remote = p.get_remote()
        remote.cmd(["cat", "/etc/passwd"])
        remote.release()
```

The keyword arguments you can pass extends beyond just TestingFarmProvisioner,
any extra ones are passed to the underlying [Reserve API class](api.py).

## Reservation time

Note that there is a limited reservation time that starts immediately after
the Provisioner submits a "request" to Testing Farm (typically with the first
`.provision()` call) and that, while Remotes are typically returned in the order
they were requested from Testing Farm, it isn't a guarantee.

So set the `timeout=` keyword argument to the maximum possible time your plan
to run for - ie. a 6h-limited CI job would set it to ~5h.
