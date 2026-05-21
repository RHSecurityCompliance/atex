> [!NOTE]
> This describes a specific implementation of the abstract Executor API.
> See also the [documentation of the generic API](..).

# CommandExecutor

A minimal Executor that runs individual commands on a Connection.

```python
from atex.executor.command import CommandExecutor

tests = {
    "check_hostname": ("hostname",),
    "list_root": ("ls", "-la", "/"),
}

with CommandExecutor(conn, tests) as e:
    e.run_test("check_hostname", artifacts_dir1)
    e.run_test("list_root", artifacts_dir2)
```

Each command's stdout and stderr are captured into the test artifacts,
and the exit code determines the result status (`pass` for 0, `fail` otherwise).

This is customizable by subclassing CommandExecutor and overriding
`.evaluate()`:

```python
class GrepExecutor(CommandExecutor):
    def evaluate(self, exit_code, output):
        if b"FAIL" in output.read_bytes():
            return "fail"
        return "pass" if exit_code == 0 else "fail"
```
