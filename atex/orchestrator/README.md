> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.\
> IOW there exist several Orchestrators for different use cases, but they all
> follow the API described here.

# Orchestrator

A scheduler for organizing complex multi-test execution.

It uses one more more [Provisioners](../provisioner) to get resources
(systems/machines) for [Executors](../executor) to run tests on them, collecting
any test results via an [Aggregator](../aggregator) common to all.

```python
with Orchestrator(...) as o:
    o.serve_forever()  # until all tests are executed
```

One Python program (thread) can process multiple Orchestrators by using the
non-blocking `.serve_once()` instead of `.serve_forever()`:

```python
with Orchestrator(...) as o1, Orchestrator(...) as o2:
    alive = [o1, o2]
    while alive:
        alive = [o for o in alive if o.serve_once()]
        time.sleep(0.1)
```

An Orchestrator can be started/stopped using a context manager, or manually via
`.start()` and `.stop()`:

```python
o = Orchestrator(...)
try:
    o.start()
    o.serve_forever()
finally:
    o.stop()
```

## Use pattern

```python
Orchestrator(platform, tests, provisioners, aggregator, executor)

Orchestrator(
    "cs10@x86_64",
    ["first test", "second test"],
    [some_provisioner_instance, another_one],
    some_aggregator_instance,
    SomeExecutorClass,
)
```

Orchestrators take a list of tests as any iterator (or set/list/etc.) and
gradually pick tests from it to be run on [Remotes](../provisioner) provided
by one of the [Provisioners](../provisioner) given.

For each new Remote, they create a new Executor instance, passing the Remote
to the Executor as a Connection (each Remote inherits from Connection), and
use that Executor instance for running tests.

This Executor instance is then used to run tests on the Remote.

Any other logic like

- test ordering,
- test re-running,
- subdividing tests into matrices,
- division of tests between Remotes,
- synchronizing two or more Remotes+tests to be run in tandem ("multihost"),
- prioritizing some Provisioners over others,
- etc.

is up to the implementation of a given Orchestrator.
