> [!NOTE]
> This describes a specific implementation of the abstract Executor API.
> See also the [documentation of the generic API](..).

# FMFExecutor

This Executor is built around [fmf](https://github.com/teemtee/fmf/), the
Flexible Metadata Format used by some test repositories. It **does not**
use [tmt](https://github.com/teemtee/tmt) to execute tests, but does emulate
several tmt features (see further below).

```python
# discover tests
fmf_tests = FMFTests(
    "path/to/repo_with_tests",
    plan="/plans/sanity",
    context={"distro": "rhel-9.6", "arch": "x86_64"},
)

# run them
with FMFExecutor(conn, fmf_tests=fmf_tests) as e:
    e.run_test(...)
```

You are free to modify the discovered FMFTests prior to passing them to
the Executor. See FMFTests instance attributes (commented in code).  
Ie. to double allowed 'duration':

```python
from atex.executor.fmf import duration_to_seconds

for data in fmf_tests.tests.values():
    duration = data.get("duration", "5m")
    secs = duration_to_seconds(duration)
    data["duration"] = str(secs * 2)
```

## Test Control channel

Tests run under this Executor have access to a "test control" stream, for
communicating with the Executor - reporting results, modifying duration limits,
safely rebooting, and others.

See [TEST_CONTROL.md](TEST_CONTROL.md) for details, including how results are
supposed to be reported by tests (there's a fallback for simple tests too).

## FMF/TMT features supported

### fmf

Everything supported by fmf should work, incl.

- YAML-based test metadata - inheritance, `name+` appends, file naming, ..
- `adjust` modifying metadata based on fmf-style Context (distro, arch, ..)
- `filter`, `condition` filtering (tags, ..) provided by fmf

### Plans

Plans are a tmt, not fmf feature. As such, FMFExecutor reimplements only *some*
of tmt features on top of what fmf already provides.

- `environment`
  - Supported as dict or list, exported for prepare scripts and tests
- `discover`
  - `-h fmf` only
  - `filter` support (via fmf module)
  - `test` support (via fmf module)
  - `exclude` support (custom `re`-based filter, not in fmf)
  - No remote git repo (aside from what fmf supports natively), no `check`,
    no `modified-only`, no `adjust-tests`, etc.
  - Tests from multiple `discover` sections are added together, eg. any order
    of the `discover` sections in the fmf is (currently) not honored
- `provision`
  - Ignored (not relevant to an ATEX Executor)
- `prepare`
  - Only `-h install` and `-h shell` supported
  - `install` reads just `package` as string/list of RPMs to install from
    standard system-wide repositories via `dnf`, nothing else
  - `shell` reads a string/list and runs it via `bash` on the machine
- `execute`
  - Ignored (might support `-h shell` in the future)
- `report`
  - Ignored (not relevant to an ATEX Executor)
- `finish`
  - Only `-h shell` supported
- `login` and `reboot`
  - Ignored (at least for now)
- `plans` and `tests` (as tmt plan YAML keywords)
  - Ignored (discover is done via FMFTests and its fmf-based filters)
- `context`
  - Ignored (at least for now), I'm not sure what it is useful for if it doesn't
    apply to `adjust`ing tests, per tmt docs. Would require double test
    discovery / double adjust as the plan itself would need to be `adjust`ed
    with the FMFTests-provided context

### Tests

- `test`
  - Supported, `test` itself is executed as an input to `bash`
  - Any fmf nodes without `test` key defined are ignored (not tests)
- `require`
  - Supported as a string/list of RPM packages to install via `dnf`
  - No support for beakerlib libraries, path requires, etc
    - Non-string elements (ie. dict) are silently ignored to allow the test
      to be tmt-compatible
- `recommend`
  - Same as `require`, but the `dnf` transaction is run with `--skip-broken`
- `duration`
  - Supported, the command used to execute the test (wrapper) is SIGKILLed
    upon reaching it and a TestAbortedError is raised
  - See [TEST_CONTROL.md](TEST_CONTROL.md) on how to adjust it during runtime
- `environment`
  - Supported as dict or list, exported for `test`
- `check`
  - Ignored, it falls outside of the scope of a simple Executor
  - If you need dmesg grepping or coredump handling, use a test library or
    do it yourself via `.cmd()` of the Connection before/after `.run_test()`
- `framework`
  - Ignored
- `result`
  - Ignored, intentionally, see [RESULTS.md](RESULTS.md)
  - The intention is for you to be able to use **both** tmt and ATEX
    reporting if you want to, so `result` is for when you run under tmt
- `restart`
  - Ignored, restart how many times you want until `duration`
  - The only requirement is that you `disconnect` the control channel cleanly
    before the connection disconnects (due to a OS reboot).
    - See `disconnect` and `noop` in [TEST_CONTROL.md](TEST_CONTROL.md)
- `path`
  - Currently not implemented, may be supported in the future
- `manual`
  - Not supported, but if defined and `true`, the fmf node is skipped/ignored
- `component`
  - Ignored
- `tier`
  - Ignored

### Stories

Not supported, but the `story` key exists, the fmf node is skipped/ignored.
