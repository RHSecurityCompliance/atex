# Executor

This is a minimalistic re-implementation of some of the features of
[tmt](https://github.com/teemtee/tmt), without re-inventing the test metadata
([fmf](https://github.com/teemtee/fmf/) parsing part, which we simply import
and use as-is.

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
