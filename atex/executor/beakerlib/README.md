> [!NOTE]
> This describes a specific implementation of the abstract Executor API.
> See also the [documentation of the generic API](..).

# BeakerlibExecutor

This extends [FMFExecutor](../fmf) with
[Beakerlib](https://github.com/beakerlib/beakerlib) support, allowing bash
tests written using Beakerlib to run smoothly.

Specifically,

- The `beakerlib` package is installed by default.
  - The `beakerlib-redhat` package too, if available in repositories.
- `BEAKERLIB_DIR` is exported.
  - This allows a test to store persistent data between reboots,
    just like in Beaker / tmt.
- `TESTID` is exported to a random UUID.
  - This allows `rlFileSubmit` to safely work for multiple tests.
- "Beakerlib libraries" are supported.
  - The `require: type: library` metadata is parsed for each test,
    and the referenced library downloaded for `rlImport`.
  - Any type-less `library(some/name)` specified in `require` is also
    translated to `require: type: library` using an implicit
    `https://github.com/beakerlib/some` git repository URL.
- Subtests / phases are reported natively.
  - A custom wrapper is provided around the `result` command of the
    [Test Control](../fmf/TEST_CONTROL.md), and exported via
    `BEAKERLIB_COMMAND_REPORT_RESULT` for `rlReport` to use.
- Files are uploaded on-the-fly.
  - This works by setting `BEAKERLIB_COMMAND_SUBMIT_LOG` to a helper that uses
    [Test Control](../fmf/TEST_CONTROL.md) to submit `partial:true` results
    with uploaded logs.
- Reboot support is made easy.
  - The `disconnect` logic of the [Test Control](../fmf/TEST_CONTROL.md)
    along with waiting-for-`noop` and shutting down `sshd`, etc., is all
    wrapped into `rhts-reboot` and `tmt-reboot`, as those are commonly
    used by Beakerlib tests.

Aside from these, the Executor is essentially identical to FMFExecutor.

```python
from atex.executor.beakerlib import BeakerlibExecutor
from atex.executor.fmf import discover

# discover tests
fmf_tests = discover(
    "path/to/repo_with_tests",
    plan="/plans/sanity",
    context={"distro": "rhel-9.6", "arch": "x86_64"},
)

# run them
with BeakerlibExecutor(conn, fmf_tests=fmf_tests) as e:
    e.run_test(...)
```
