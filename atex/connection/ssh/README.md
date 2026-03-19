# SSH Connection

This wraps the `ssh` (OpenSSH) client with a [Connection](..) API.

Any SSH options are passed via dictionaries of options, and later translated
to `-o` client CLI options, incl. Hostname, User, Port, IdentityFile, etc.

**No "typical" ssh CLI switches are used.**

This allows for a nice flexibility from Python code - this module provides
some sensible option defaults (for scripted use), but you are free to
overwrite any options via class or function arguments (where appropriate).
See [ssh_config(5)](https://linux.die.net/man/5/ssh_config).

Note that `.cmd()` quotes arguments to really execute individual arguments
as individual arguments in the remote shell, so you need to give it a proper
iterable (like for other Connections), not a single string with spaces.

Also note that (unlike an interactive CLI `ssh` client), this doesn't allocate
TTY by default, behaving exactly like `ssh` does when given a command to run,
ie. `ssh user@host some_cmd`. Override it with 'RequestTTY' in options.

## StatelessSSHConnection

This is a simple literal `ssh` command wrapper. It executes one `ssh` process
for every single `.cmd()` - the client connects, authenticates, logs in, and
then executes the command.

The `.connect()` and `.disconnect()` methods are a no-op.

```python
opts = {
    "Hostname": "foo.example.com",
    "Port": "22",
    "User": "joe",
    "IdentityFile": "/path/to/ssh_key"
}

with StatelessSSHConnection(opts):
    c.cmd(["ls", "/"])
    ...
```

## ManagedSSHConnection

This uses `.connect()` to spawn a background "master" ssh client, which connects
to the remote host, authenticates, logs in, etc., but doesn't actually spawn
a shell. Any subsequent `.cmd()` or `.rsync()` commands then use `ssh` commands
which use this "master" connection to run.

This has **significant** latency improvements - ie. if StandaloneSSHConnection
takes 3 seconds to run a command, ManagedSSHConnection can typically do it in
0.3 seconds once the "master" connects.

For running one long-running command, StatelessSSHConnection is still better
(because it's simpler), but for running many commands, consider using
ManagedSSHConnection.

See the ControlMaster and ControlPath ssh client options for implementation.

```python
opts = {
    "Hostname": "bar.example.com",
    "Port": "2222",
    "User": "moe",
    "IdentityFile": "/path/to/ssh_key"
}

with ManagedSSHConnection(opts):
    c.cmd(["ls", "/"])
    c.cmd(["cat", "/etc/passwd"])
    c.cmd(["df", "-h"])
    ...
```

Note that ManagedSSHConnection further implements `.forward()` as an extension
to the Connection API.
