# ATEX = Ad-hoc Test EXecutor

A collections of Python APIs to provision operating systems, collect
and execute [FMF](https://github.com/teemtee/fmf/)-style tests, gather
and organize their results and generate reports from those results.

The name comes from a (fairly unique to FMF/TMT ecosystem) approach that
allows provisioning a pool of systems and scheduling tests on them as one would
on an ad-hoc pool of thread/process workers - once a worker becomes free,
it receives a test to run.  
This is in contrast to splitting a large list of N tests onto M workers
like N/M, which yields significant time penalties due to tests having
very varies runtimes.

Above all, this project is meant to be a toolbox, not a silver-plate solution.
Use its Python APIs to build a CLI tool for your specific use case.  
The CLI tool provided here is just for demonstration / testing, not for serious
use - we want to avoid huge modular CLIs for Every Possible Scenario. That's
the job of the Python API. Any CLI should be simple by nature.

---

## License

Unless specified otherwise, any content within this repository is distributed
under the GNU GPLv3 license, see the [COPYING.txt](COPYING.txt) file for more.

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
