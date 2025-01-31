# Minitmt

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
- it implicitly using SSH Master socket, incompatible with our Master socket,
  and `--ssh-option` doesn't help as it just adds extra options on top
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
- it hard-killing a test when testtime is reached, breaking any cleanups
  performed by tests on signal, incl. python Context Manager logic, etc.,
  needing us to implement a custom testtime-parsing watchdog that signals
  the test a few minutes before tmt kills everything
- it using a hard-to-parse datadir structure, requiring dynamically loading
  of YAML metadata just to continue accessing subdirectories, ie. reading
  `$datadir/run.yaml` to find plan name, to access
  `$datadir/plans/$plan_name/*`, similarly for directories inside `execute/`
- (cutting this short, there is more)

TL;DR - it just seemed easier to reimplement a few tmt-plan-related bits and
pieces of fmf metadata, than to deal with all of the above.

(No hate towards the full-fat tmt, it has many more features and complexity.)

## Compatibility

Minitmt is designed to be mostly-compatible with tmt in most simple use cases,
the idea is that you should be able to write tests that **work with both**,
easily.

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
- run under minitmt in a more "wild" mode, without those limitations
  - tens of millions of results
  - logs with full paths
  - cross-test result reporting
  - etc.

Hopefully running well under Testing Farm / OSCI / etc., while being extra
useful when run via the tooling in this git repo.

## Scope

### fmf

Everything supported by fmf should work, incl.

- YAML-based test metadata - inheritance, `name+` appends, file naming, ..
- `adjust` modifying metadata based on fmf-style Context (distro, arch, ..)
- `filter`, `condition` filtering (tags, ..) provided by fmf

### Plans

- `discover`
  - `-h fmf` only
  - `filter` support (via fmf module)
  - `test` support (via fmf module)
  - `exclude` support (custom implementation, not in fmf)
  - No remote git repo (aside from what fmf supports natively, no `check`,
    no `modified-only`, no `adjust-tests`, ..
- `provision`
  - Completely ignored (custom provisioning logic used)
- `prepare`
  - Only `-h install` and `-h shell` supported
  - `install` reads just `package` as string/list of RPMs to install from
    standard system-wide repositories via `dnf`, nothing else
  - `shell` reads a string/list and runs it via `/bin/bash` on the machine
- `execute`
  - Completely ignored (might support `-h shell` in the future)
- `report`
  - Completely ignored (custom reporting logic used)
- `finish`
  - Only `-h shell` supported
- `login` and `reboot`
  - Completely ignored (at least for now)
- `plans` and `tests`
  - Completely ignored (CLI option used for plan, choose tests via `discover`)

### Tests

- `test`
  - Supported, `test` itself is executed via `/bin/bash`
  - Any fmf nodes without `test` key defined are ignored (not tests)
- `require`
  - Supported as a string/list of RPM packages to install via `dnf`
  - No support for beakerlib libraries, path requires, etc.
- `duration`
  - Supported, test receives `SIGINT` after expiration and is given up to
    5 minutes to clean up, and if it doesn't exit, we `SIGKILL`.
  - **Unlike tmt, we do not simply disconnect**, we use a separate ssh shell
    to kill the entire process group (by parent PID) running the test, to ensure
    a re-use of the machine doesn't spawn a second running copy of the test.
  - This is meant to be an emergency measure, please use timeout logic in your
    tests if you need longer cleanup.
  - We track time precisely (setting end and comparing to it), not by repeated
    `sleep 1` which accumulates error quickly.
- `environment`
  - Supported as dict, exported for `test`
- `check`
  - Completely ignored, we don't fail your test because of unrelated AVCs
- `framework`
  - Completely ignored
- `result`
  - Completely ignored, intentionally, see [RESULTS.md](RESULTS.md)
    below
  - The intention is for you to be able to use **both** tmt and minitmt
    reporting if you want to, so `result` is for when you want full tmt
- `restart`
  - Completely ignored, restart how many times you want until `duration`
- `path`
  - Currently not implemented, may be supported in the future
- `manual`
  - Not supported, but if defined and `true`, the fmf node is skipped/ignored
- `component` and `tier`
  - Completely ignored

### Stories

Not supported, but the `story` key exists, the fmf node is skipped/ignored.

### Test interface

A test has acces to a "control file" available as a unix socket, as an
innovation not currently supported by tmt, and is able to use that file to
adjust external test environment by communicating with the test runner,
report test result(s) to it, upload files/logs through it, etc.

The details are in [CONTROL_FILE.md](CONTROL_FILE.md).

### Implementation overview

TODO

- importing fmf
- parsing fmf metadata tree, searching for tests to run?
- preparing a wrapper script to be run on the SUT
  - the back/forth protocol between minitmt and the script; tmpdir, socket path, etc.
- using SSHConn to run a test
  - forced tty, logging
  - trimming 'Connection closed ...' by not logging ssh stderr as test output
    (because forced tty will route everything to stdout of the ssh process)

