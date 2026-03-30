> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.\
> IOW there exist several Aggregators for different use cases, but they all
> follow the API described here.

# Aggregator

A test result collector and organizer.

It collects [Test Artifacts](../executor), for archival, logging, or further
post-processing, using one algorithm, implemented by the Aggregator.

```python
with Aggregator() as a:
    a.ingest("platform_name", "/some/test", test_artifacts_dir)
    a.ingest("platform_name", "/another/test", other_artifacts_dir)

    a.ingest("another/platform", "some wild test", wild_artifacts_dir)
```

- The `platform` specified to `.ingest()` may be any arbitrary string, but
  is commonly used for OS version, HW architecture, or CI service name,
  ie. `9.6` or `rhel-9.6` or `9@x86_64` or `centos-10 Gitlab`.

- The `test_name` given to `.ingest()` may similarly be any arbitrary string
  or `str()`-capable object, identifying the test within the `platform`.

An Aggregator can be started/stopped using a context manager, or manually via
`.start()` and `.stop()`:

```python
a = Aggregator()

try:
    a.start()

    a.ingest(...)
    a.ingest(...)
    ...

finally:
    a.stop()
```

## Semantics

### Thread safety

An Aggregator must implement `.ingest()` in a thread-safe way, as it may be
called from any thread, possibly at the same time.

It may rely on `.start()` and `.stop()` to be called only by the thread
which created the specific Aggregator instance.

It may also rely on `.ingest()` being called only after `.start()`.
