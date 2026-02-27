# Provisioner

A remote resource (machine/system) provider.

TODO: better docs ? more examples?

The idea is to request machines (a.k.a. Remotes, or class Remote instances)
to be reserved via a non-blocking `.provision()` and for them to be
retrieved through blocking / non-blocking `.get_remote()` when they
become available.

Each Remote has its own `.release()` for freeing (de-provisioning) it once
the user doesn't need it anymore. The Provisioner does this automatically
to all Remotes during `.stop()` or Context Manager exit.

```python
p = Provisioner()
p.start()
p.provision(count=1)
remote = p.get_remote()
remote.cmd(["ls", "/"])
remote.release()
p.stop()
```

Or with a Context Manager:

```python
with Provisioner() as p:
    p.provision(count=2)
    remote1 = p.get_remote()
    remote2 = p.get_remote()
    ...
```

Note that `.provision()` is not a guarantee that `.get_remote()` will ever
return a Remote. Ie. the caller can call `.provision(count=math.inf)` to
receive as many remotes as the Provisioner can possibly supply.

## Remote

Representation of a provisioned (reserved) remote system, providing
a [Connection](../connection)-like API in addition to system management
helpers.

An instance of Remote is typically prepared by a Provisioner and returned
to the caller for use and an eventual `.release()`.

Also note that Remote can be used via Context Manager, but does not
do automatic `.release()`, the manager only handles the built-in Connection.
The intention is for a Provisioner to run via its own Contest Manager and
release all Remotes upon exit.

If you need automatic release of one Remote, use a try/finally block, ie.

```python
try:
    remote.cmd(...)
    ...
finally:
    remote.release()
```
