> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.  
> IOW there exist several Connections for different use cases, but they all
> follow the API described here.

# Connection

A channel to a resource (machine/system) for running commands and transferring
files.

```python
with Connection() as c:
    c.cmd(["ls", "/"])  # outputs to your console

    output = c.cmd(["ls", "/"], func=subprocess.check_output)

    proc = c.cmd(
        ["ls", "/"],
        func=subprocess.run,
        stdout=subprocess.PIPE,  # kwargs passed to func
        text=True,
        check=True,
    )
    print(proc.stdout)

    c.rsync("/etc/passwd", "remote:/tmp/.")
```

Note that both `.cmd()` and `.rsync()` expect `func=` to behave like one of
the `subprocess` functions (`.run()`, `.check_output()`, `.Popen()`, etc.),
giving it a command to execute and any other kwargs you specify.

A Connection can be connected/disconnected using a context manager (above)
or manually via `.connect()` and `.disconnect()`:

```python
c = Connection()

c.connect()
proc = c.cmd(["ls", "/"])
c.disconnect()
```

Or via `try`/`finally` to guard against exceptions:

```python
c = Connection()

try:
    c.connect()
    ...
finally:
    c.disconnect()
```
