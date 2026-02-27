# Connection

TODO: better docs?


A unified API for connecting to a remote system, running multiple commands,
rsyncing files to/from it and checking for connection state.

```python
conn = Connection()
conn.connect()
proc = conn.cmd(["ls", "/"])
#proc = conn.cmd(["ls", "/"], func=subprocess.Popen)  # non-blocking
#output = conn.cmd(["ls", "/"], func=subprocess.check_output)  # stdout
conn.rsync("-v", "remote:/etc/passwd", "passwd")
conn.disconnect()

# or as try/except/finally
conn = Connection()
try:
    conn.connect()
    ...
finally:
    conn.disconnect()

# or via Context Manager
with Connection() as conn:
    ...
```

Note that internal connection handling must be implemented as thread-aware,
ie. `disconnect()` might be called from a different thread while `connect()`
or `cmd()` are still running.  
Similarly, multiple threads may run `cmd()` or `rsync()` independently.

TODO: document that any exceptions raised by a Connection should be children
of ConnectionError

If any connection-related error happens, a ConnectionError (or an exception
derived from it) must be raised.
