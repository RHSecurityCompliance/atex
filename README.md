# ATEX

ATEX is a framework for a configurable test execution.

It is a set of Python-based abstract APIs and several implementations utilizing
them, providing building blocks for you to make simple Python-based scripts
that control the execution and result processing of your tests.

Its main building blocks are:

- [**Provisioners**](atex/provisioner) that give you systems to run tests on
- [**Executors**](atex/executor) that prepare and run the tests on them
- [**Aggregators**](atex/aggregator) that collect results from multiple tests
- [**Orchestrators**](atex/orchestrator) that string everything up together,
  using Provisioners to get systems for Executors to run tests on, calling
  an Aggregator to ingest all test results

ATEX is **not a linear pipeline** like `Provision -> Execute -> Report`,
the building blocks can be used **independently** and **at any time**.

Even during orchestration, Provisioners **run in parallel** to Executors,
so that re-runs of failed tests can get fresh systems, and tests can start
running as soon as one system is provisioned. Aggregators can upload to
3rd party services as soon as any one test finishes.

## You are in control

The key part is that this is a framework to be used by YOU. Your script controls
what gets used and how.

You can download / fetch tests from multiple repositories, modify their metadata
on-the-fly, do anything you want via normal Python code, and also call ATEX
building blocks to help you.

There is no "vendor lock in" to one tool or ecosystem. You don't need ATEX to
implement feature XYZ when you can write a trivial piece of Python code to
do it (ie. pre-processing test metadata, post-processing results).

There are no boundaries for you to stay within - **you don't need to implement
a Provisioner using the Provisioner API**. Just obtain the system *somehow*,
wrap its SSH details in an [SSHConnection](atex/connection/ssh), and give that
to an [FMFExecutor](atex/executor/fmf).

You don't need to write a "plugin for ATEX", you just write Python code.

## How it works

Each building block defines one or more abstract base classes, forming a sort-of
stable reference API for everyone to use:

```python
class Brewer:
    def intake(self, ingredients):
        """Input `ingredients` for brewing."""

    def brew(self):
        """Brew the beverage and return it."""
```

Note that **only the function names and their positional arguments are part
of the API**. Any other functions and or keyword arguments to the API functions
are left to the implementation.  
Similarly, return values are part of the API only where explicitly stated, and
up to the implementation otherwise.

```python
class CoffeeBrewer(Brewer):
    def __init__(self, kind, strength=None):
        self.kind = kind
        self.strength = strength if strength is not None else 5

    def _the_actual_brewing(self):
        ...

    def intake(self, ingredients, *, grind=True):
        ...

    def brew(self, *, speed=100):
        return self._the_actual_brewing()
```

Any piece of code can then state that it takes an initialized `Brewer` instance
as an argument, and have a guarantee that it will have `.intake(ingredients)`
and `.brew()` available, no matter the implementation.

```python
b = CoffeeBrewer("espresso", 1000)
serve_to_employees(brewer=b)
```

### `__init__` is not special

Note that `__init__` is subject to the statements above too:

- If the base API class defines it, an implementation can only extend it
  via keyword arguments.
- If it doesn't (as above), `__init__` of the implementation class can have
  any arguments possible.

---

## Environment variables

- `ATEX_DEBUG_TEST`
  - Set to `1` to print out detailed runner-related trace within the test output
    stream (as if it was printed out by the test).

## Testing this project

There are some limited sanity tests provided via `pytest`, although:

- Some require additional variables (ie. Testing Farm) and will ERROR
  without them.
- Some take a long time (ie. Testing Farm) due to system provisioning
  taking a long time, so install `pytest-xdist` and run with a large `-n`.

Currently, the recommended approach is to split the execution:

```
# synchronously, because podman CLI has concurrency issues
pytest tests/provision/test_podman.py

# in parallel, because provisioning takes a long time
export TESTING_FARM_API_TOKEN=...
export TESTING_FARM_COMPOSE=...
pytest -n 20 tests/provision/test_podman.py

# fast enough for synchronous execution
pytest tests/fmf
```

## Unsorted notes

TODO: codestyle from contest

```
- this is not tmt, the goal is to make a python toolbox *for* making runcontest
  style tools easily, not to replace those tools with tmt-style CLI syntax

  - the whole point is to make usecase-targeted easy-to-use tools that don't
    intimidate users with 1 KB long command line, and runcontest is a nice example

  - TL;DR - use a modular pythonic approach, not a gluetool-style long CLI
```

## What it stands for

ATEX = Ad-hoc Test EXecution, named after the most prominent Orchestrator,
originally the only one available.

The name comes from a (fairly unique to FMF/TMT ecosystem) approach that
allows provisioning a pool of systems and scheduling tests on them as one would
on an ad-hoc pool of thread/process workers - once a worker becomes free,
it receives a test to run.

This is in contrast to a more common approach of splitting a large list of
N tests onto M workers like N/M, which yields significant time penalties due
to tests having very varies runtimes.
