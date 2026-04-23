> [!NOTE]
> This describes a specific implementation of the abstract Executor API.
> See also the [documentation of the generic API](..).

# FMFExecutor

This Executor is built around [fmf](https://github.com/teemtee/fmf/), the
Flexible Metadata Format used by some test repositories. It **does not**
use [tmt](https://github.com/teemtee/tmt) to execute tests, but does emulate
several tmt features (see further below).

```python
from atex.executor.fmf import FMFExecutor, discover

# discover tests
fmf_tests = discover(
    "path/to/repo_with_tests",
    plan="/plans/sanity",
    context={"distro": "rhel-9.6", "arch": "x86_64"},
)

# run them
with FMFExecutor(conn, fmf_tests=fmf_tests) as e:
    e.run_test(...)
```

You are free to modify the discovered FMFTests prior to passing them to
the Executor. See documented FMFTests instance attributes.\
Ie. to double allowed 'duration':

```python
from atex.executor.fmf import duration_to_seconds

for data in fmf_tests.data.values():
    duration = data.get("duration", "5m")
    secs = duration_to_seconds(duration)
    data["duration"] = str(secs * 2)
```

## Test discovery

1. Tests are discovered using the `discover()` function, which uses the fmf
   python module to either read on-disk metadata definitions, or fetch them
   remotely via git cloning (it has its own cache in `~/.cache/fmf`).\
   The function populates a single FMFTests dataclass instance, returning it.
1. This instance is used by FMFExecutor to rsync the tests via the provided
   Connection and run them remotely.

These two steps are intentionally separate - you are free to supply custom
logic for making a FMFTests instance, or customize the pre-made one.

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
  - Multiple (list) sections are supported, incl. remote URL-referenced
    trees, using fmf module fetching. See a separate section below.
  - `when` is not supported (use the more standard `adjust` to conditionally
    add extra list items to `discover`)
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
  - Beakerlib libraries are also supported
    - Via a `type: library` dict (or any dict without `type`)
    - Via a legacy `library(foo/bar)` syntax with RPM fallback
- `recommend`
  - Same as `require`, but the `dnf` transaction is run with `--skip-broken`
  - Unlike tmt, **beakerlib libraries are not supported in `recommend`**,
    since doing so felt like replicating a bug, not a compatibility helper
- `duration`
  - Supported, the command used to execute the test (Connection process) is
    SIGKILLed upon reaching it and a TestAbortedError is raised
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
    before the connection disconnects (due to an OS reboot).
    - See `disconnect` and `noop` in [TEST_CONTROL.md](TEST_CONTROL.md)
- `path`
  - Currently not implemented, may be supported in the future
- `manual`
  - Not supported, but if defined and `true`, the fmf node is skipped/ignored
- `component`
  - Ignored
- `tier`
  - Ignored
- `tty`
  - Supported, with `false` as default.
  - With `true`, it actually goes above and beyond to provide a reasonable
    terminal, resized to 80x24 and with `TERM` set.

### Stories

Not supported, but if the `story` key exists, the fmf node is skipped/ignored.

### Multiple discover sections

Multiple `discover` list sections are supported, but they all **must**
define `name`s.

```yaml
discover:
  - how: fmf
    name: external
    url: https://some/external/repo
  - how: fmf
    name: internal
```

Note that tmt doesn't enforce this and instead names each unnamed section
`default-0`, `default-1`, etc., likely as a result of tmt's implementation
specifics (separate worktree for each discover).

Finally, just like tmt, one source can be used multiple times, possibly
duplicating the tests, ie. this would run local tests twice:

```yaml
discover:
  - name: first
    how: fmf
  - name: second
    how: fmf
```

### Prepare/finish section CWD

In tmt, the plan `prepare` / `finish` sections (as well as the `TMT_TREE` env
var) are set to the plan's own metadata tree. This means that remotely
discovered (ie. with `url` or `path`) tests using `TMT_TREE` or relying on files
created by plan-level scripts won't work.

In fact, if no tests are discovered locally, the plan's own tree (git repo)
is also copied over, just for the plan scripts to have access to their tree.

FMFExecutor takes a different stance - if only one discover section is defined
(without `name`), the plan scripts see that tree's contents. This matches how
tmt does it.\
If multiple sections are defined (or if the one has `name`), their CWD contains
directories named after `name`s of the sections, containing the remotely
discovered contents.

Since this all lives in one plan, it is easy to access any discovered tests
via known prefixes:

```yaml
discover:
  - name: internal
    how: fmf
  - name: external
    how: fmf
    url: https://some/external/repo

prepare:
  - how: shell
    script: |
      echo URL=https://some/internal/service > internal/service.env
      echo URL=https://some/external/service > external/service.env
  - how: shell
    script: pkgs=$(cat internal/deps) && dnf install -y $pkgs
```

The `TMT_TREE` variable then points to the same place as the CWD of the
scripts - here, it would contain `internal` and `external` dirs.

## Environment variables

- `ATEX_DEBUG_NO_EXITCODE`
  - Set to `1` to avoid the test wrapper sending an automatic `exitcode` keyword
    over [Test Control](TEST_CONTROL.md).
  - Useful mainly for testing FMFExecutor itself.
- Compatibility with tmt
  - `TMT_TREE` - slightly different to tmt, see above
  - `TMT_PLAN_ENVIRONMENT_FILE`
  - `TMT_TEST_NAME`
  - `TMT_TEST_METADATA`
  - `TMT_REBOOT_COUNT`
  - `TMT_TEST_RESTART_COUNT`
