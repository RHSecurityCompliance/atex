# Executor

This is a minimalistic re-implementation of some of the features of
[tmt](https://github.com/teemtee/tmt), without re-inventing the test metadata
([fmf](https://github.com/teemtee/fmf/) parsing part, which we simply import
and use as-is.

## Why?

(You will be probably asking this first.)

The main reason for this is one `tmt` process using ~90 MB of RAM while
a test is running, which doesn't scale well to ~100 instances and beyond,
without needing many GBs on the orchestrating system.  
This is not the fault of `tmt`, but of it being a Python process (which are
expensive) being spawned many times in parallel without sharing CPython
resources.

The secondary reason is to avoid the many "gotchas" we used to run into when
trying to bend tmt to our needs, ie.

- it being unable to easily run plan/prepare and then execute tests ad-hoc
  via our invocation without re-running previous steps (technically possible,
  but `TMT_PLAN_ENVIRONMENT_FILE` would need to be re-linked by us, it would
  require extra shuffling of fake tmt data dirs, etc., etc.)
- it having race conditions when multiple instances are run under one user,
  needing to be run with fake `HOME`, `TMPDIR`, etc., with cleanup
- it implicitly using SSH Master socket, incompatible with our Master socket
  in `provision -h connect` cases, and `--ssh-option` doesn't help as it just
  adds extra options on top
- it trying to re-spawn `rsync` (and thus `ssh`) many times, taking >60 minutes
  just to figure out that the SUT has died (reservation expired) before
  returning
- it needing YAML or full-file JSON for test results, neither of which can
  be written atomically (without hacks) or read as a stream (no line-JSON
  support) - using YAML for large data leads to large memory usage spikes
- it not having an exit code from which we could differentiate between
  an infrastructure failure (test rsync, etc.) and a test failure (as reported
  by the test result), leading to mysterious "tmt has failed and we don't know
  if it is serious or just a test result"
- it copying the whole test suite into every datadir, even for simple tasks
  like discover, needing us to (1) create tmp datadir, (2) run tmt, (3) extract
  the useful bits elsewhere, (4) delete datadir, or risk filling up disk space
  after a few 1000s of tmt runs
- it using the same datadir path on host and guest, leading to unexpected
  denials when using a datadir in `/home/myuser/.cache/*` on the host and
  trying to access/create it on the guest, or using `/tmp/*` on the host
  and losing the contents on the guest upon reboot, leading to mysterious
  test errors
- it using a hard-to-parse datadir structure, requiring dynamically loading
  of YAML metadata just to continue accessing subdirectories, ie. reading
  `$datadir/run.yaml` to find plan name, to access
  `$datadir/plans/$plan_name/*`, similarly for directories inside `execute/`
- (cutting this short, there is more)

TL;DR - it just seemed easier to reimplement a few tmt-plan-related bits and
pieces of fmf metadata, than to deal with all of the above.

(No hate towards the full-fat tmt, it has many more features and complexity.)

## Compatibility

This implementation is designed to be mostly-compatible with tmt in most simple
use cases, the idea is that you should be able to write tests that **work with
both**, easily.

Our main problem with the ecosystem around tmt is that it is heavily
Beakerlib-inspired, with tools relying on a small subset of tmt functionality
and they break otherwise.  
(Or, if fixed, would likely provide sub-par experience for most tmt users.)

So the goal here is to write tests that

- run under full tmt in some "compatibility" mode
  - reporting just one basic pass/fail result via exit code
  - having no additional logs, letting tmt use `output.txt` as test output,
    renamed to `testout.log` by Testing Farm
  - not trying to be fancy
- run under atex in a more "wild" mode, without those limitations
  - tens of millions of results
  - logs with full paths
  - etc.

Hopefully running well under Testing Farm / OSCI / etc., while being more
useful when run via the tooling in this git repo.

## Scope

### fmf

Everything supported by fmf should work, incl.

- YAML-based test metadata - inheritance, `name+` appends, file naming, ..
- `adjust` modifying metadata based on fmf-style Context (distro, arch, ..)
- `filter`, `condition` filtering (tags, ..) provided by fmf

### Plans

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
    of the `discover` sections in the fmf is (currently) not honored.
- `provision`
  - Ignored (custom provisioning logic used)
- `prepare`
  - Only `-h install` and `-h shell` supported
  - `install` reads just `package` as string/list of RPMs to install from
    standard system-wide repositories via `dnf`, nothing else
  - `shell` reads a string/list and runs it via `bash` on the machine
- `execute`
  - Ignored (might support `-h shell` in the future)
- `report`
  - Ignored (custom reporting logic used)
- `finish`
  - Only `-h shell` supported
- `login` and `reboot`
  - Ignored (at least for now)
- `plans` and `tests`
  - Ignored (CLI option used for plan, choose tests via `discover`)
- `context`
  - Ignored (at least for now), I'm not sure what it is useful for if it doesn't
    apply to `adjust`ing tests, per tmt docs. Would require double test
    discovery / double adjust as the plan itself would need to be `adjust`ed
    using CLI context first

### Tests

- `test`
  - Supported, `test` itself is executed as an input to `bash`
  - Any fmf nodes without `test` key defined are ignored (not tests)
- `require`
  - Supported as a string/list of RPM packages to install via `dnf`
  - No support for beakerlib libraries, path requires, etc
    - Non-string elements (ie. dict) are silently ignored to allow the test
      to be full-tmt-compatible
- `recommend`
  - Same as `require`, but the `dnf` transaction is run with `--skip-broken`
- `duration`
  - Supported, the command used to execute the test (wrapper) is SIGKILLed
    upon reaching it and the entire machine is discarded (for safety)
  - See [TEST_CONTROL.md](TEST_CONTROL.md) on how to adjust it during runtime
- `environment`
  - Supported as dict or list, exported for `test`
- `check`
  - Ignored, we don't fail your test because of unrelated AVCs
  - If you need dmesg grepping or coredump handling, use a test library
- `framework`
  - Ignored
- `result`
  - Ignored, intentionally, see [RESULTS.md](RESULTS.md) below
  - The intention is for you to be able to use **both** tmt and atex
    reporting if you want to, so `result` is for when you want full tmt
- `restart`
  - Ignored, restart how many times you want until `duration`
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

### Test interface

A test has write-only access to a "test control" stream, as a feature currently
unsupported by tmt, for adjusting external test environment, reporting results,
uploading logs and otherwise communicating with the test runner.

The details are in [TEST_CONTROL.md](TEST_CONTROL.md).
