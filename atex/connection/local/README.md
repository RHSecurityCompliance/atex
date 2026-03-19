# Local Connection

This is just a simple translation layer between the `subprocess` module and
the [Connection](..) API, running all commands locally on the OS.

The `.connect()` and `.disconnect()` methods are a no-op.

```python
with LocalConnection():
    c.cmd(["ls", "/"])
    ...
```
