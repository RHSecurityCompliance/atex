> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.\
> IOW there exist several Orchestrators for different use cases, but they all
> follow the API described here.

# Orchestrator

A scheduler for organizing complex multi-test execution.

It uses one or more [Provisioners](../provisioner) to get resources
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

Generally speaking, Orchestrators take a list (sequence) of tests and gradually
pick tests from it to be run on [Remotes](../provisioner) provided by one of
the [Provisioners](../provisioner) given to the Orchestrators.

```
+-------------+                                  +----------+
| Provisioner |                                  | Executor |
+-------------+                                  +----------+
                        +--------------+         | Executor |
+-------------+  <--->  | Orchestrator |  <--->  +----------+
| Provisioner |         +--------------+         | Executor |
+-------------+                |                 +----------+
                               v                 | Executor |
+-------------+         +--------------+         +----------+
| Provisioner |         |  Aggregator  |
+-------------+         +--------------+
```

For each new Remote they get from a Provisioner, they instantiate an Executor
to run tests on that Remote.

Any other logic like

- test ordering,
- test re-running,
- subdividing tests into matrices,
- division of tests between Remotes,
- synchronizing two or more Remotes+tests to be run in tandem ("multihost"),
- prioritizing some Provisioners over others,
- etc.

is up to the implementation of a given Orchestrator.
