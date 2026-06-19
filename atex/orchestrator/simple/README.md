> [!NOTE]
> This describes a specific implementation of the abstract Orchestrator API.
> See also the [documentation of the generic API](..).

# SimpleOrchestrator

This is a very simple Orchestrator built mostly as a working example of how to
make a bare-bones Orchestrator.

It just takes an iterable of test names and goes over them one-by-one, passing
them to an Executor, and calling an Aggregator to ingest any results.

```python
from atex.orchestrator.simple import SimpleOrchestrator

with SomeAggregator(...) as aggr, SomeProvisioner(...) as prov:
    o = SimpleOrchestrator(
        platform="cs10@x86_64",
        tests=["/first/test", "/second/test"],
        provisioner=prov,
        executor=lambda conn: SomeExecutor(conn, ...),
        aggregator=aggr,
    )
    with o:
        o.serve_forever()
```

It only ever acquires one Remote from the given Provisioner to execute tests on
one-by-one, except when given `destructive=True`, which causes it to acquire
a new Remote for each new executed test, throwing away the old one.\
Useful for tests that require a fresh environment.
