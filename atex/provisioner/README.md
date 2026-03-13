> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.  
> IOW there exist several Provisioners for different use cases, but they all
> follow the API described here.

# Provisioner

A resource (machine/system) provider.

The idea is to request machines (a.k.a. Remotes, or class Remote instances)
to be reserved via the `.provision()` method and for them to be retrieved
through the `.get_remote()` method when they become available.

```python
with Provisioner() as p:
    p.provision(1)
    remote1 = p.get_remote()  # remote1 is class Remote instance

    p.provision(3)
    remote2 = p.get_remote()
    remote3 = p.get_remote()
    remote4 = p.get_remote()
    ...
```

The argument given to `.provision()` represents the count of systems to be
reserved and eventually gradually returned via `.get_remote()`.

Each Remote instance has its own `.release()` for freeing (de-provisioning) it
once the user doesn't need it anymore. The Provisioner does this automatically
to all Remotes during shutdown (`.stop()` or context manager exit).

A Provisioner can be started/stopped using a context manager, or manually via
`.start()` and `.stop()`:

```python
p = Provisioner()

try:
    p.start()

    p.provision(count=1)
    remote = p.get_remote()
    remote.cmd(["ls", "/"])
    remote.release()

finally:
    p.stop()
```

## Remote

A representation of a provisioned (reserved) remote system, providing
a [Connection](../connection)-like API in addition to `.release()`.

```python
with Provisioner() as p:
    p.provision(10)
    for _ in range(10):
        remote = p.get_remote()
        remote.rsync("/etc/passwd", "remote:/tmp/.")
        remote.cmd(["cat", "/tmp/passwd"])
        remote.release()
```

Note that Remote can be used via context manager, but does not do automatic
`.release()` upon context manager exit. The manager only handles the built-in
Connection. The intention is for a Provisioner to run via its own context
manager and release all Remotes upon its exit (if they weren't released by
an explicit `.release()` as shown above).

If you need automatic release of one Remote, use a try/finally block, ie.

```python
try:
    remote.cmd(...)
    ...
finally:
    remote.release()
```

## Semantics

### Relationship between `.provision()` and `.get_remote()`

Note that there is no exact precise relation between `.provision()` counts
and how many remotes `.get_remote()` calls return.

With `.provision(3)`, you *ask politely* the Provisioner for 3 Remotes.

It may return 2 right away, but let you wait for hours with the 3rd one.
Or it may return 5 remotes instantly if you call `.get_remote()` more times.
Similarly, the Provisioner might ignore your `.provision()` requests and
just give you remotes via `.get_remote()` at its own pace.

The point is:
- If you want 3 Remotes via `.get_remote()`, call `.provision(3)`.
- If you want as many Remotes as you can get, call `.provision(math.inf)`.
- Don't rely on `.get_remote()` blocking until you `.provision()`.

### Clearing `.provision()` requests

The `.clear()` Provisioner method tells it to disregard any previous
`.provision()` calls. Any further meaning is implementation-specific.

The Provisioner may still reserve systems in the background, just withhold
them from `.get_remote()` until you `.provision()` again. Or it may ignore
`.clear()` completely and just continue provisioning, if it ignored all
`.provision()` calls in the first place.

More realistically, a Provisioner would clear any not-yet-submitted requests
for reservation, and let existing in-progress reservations finish, to be
returned via `.get_remote()`.

Mainly, `.clear()` is the only way to undo `.provision(math.inf)`.

### Thread safety

A Provisioner must implement `.provision()`, `.get_remote()` and `.clear()`
to be safe to call from any thread, possibly at the same time.

It may rely on `.start()` and `.stop()` to be called only by the thread
which created the specific Provisioner instance.

It may also rely on `.provision()`, `.get_remote()` or `.clear()` being called
only after `.start()`.
