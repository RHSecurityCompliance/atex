"""
Connection API implementation using the OpenSSH ssh(1) client.

Any SSH options are passed via dictionaries of options, and later translated
to '-o' client CLI options, incl. Hostname, User, Port, IdentityFile, etc.
No "typical" ssh CLI switches are used.

This allows for a nice flexibility from Python code - this module provides
some sensible option defaults (for scripted use), but you are free to
overwrite any options via class or function arguments (where appropriate).

Note that .cmd() quotes arguments to really execute individual arguments
as individual arguments in the remote shell, so you need to give it a proper
iterable (like for other Connections), not a single string with spaces.
"""

import os
import time
import shlex
import tempfile
import threading
import subprocess
from pathlib import Path

from .. import util
from . import Connection


DEFAULT_OPTIONS = {
    "LogLevel": "ERROR",
    "StrictHostKeyChecking": "no",
    "UserKnownHostsFile": "/dev/null",
    "ConnectionAttempts": "3",
    "ServerAliveCountMax": "4",
    "ServerAliveInterval": "5",
    "TCPKeepAlive": "no",
    "EscapeChar": "none",
    "ExitOnForwardFailure": "yes",
}


class SSHError(ConnectionError):
    pass


class DisconnectedError(SSHError):
    """
    Raised when an already-connected ssh session goes away (breaks connection).
    """
    pass


class NotConnectedError(SSHError):
    """
    Raised when an operation on ssh connection is requested, but the connection
    is not yet open (or has been closed/disconnected).
    """
    pass


class ConnectError(SSHError):
    """
    Raised when a to-be-opened ssh connection fails to open.
    """
    pass


def _shell_cmd(command, sudo=None):
    """
    Make a command line for running 'command' on the target system.
    """
    quoted_args = (shlex.quote(str(arg)) for arg in command)
    if sudo:
        return " ".join((
            "exec", "sudo", "--no-update", "--non-interactive", "--user", sudo, "--", *quoted_args,
        ))
    else:
        return " ".join(("exec", *quoted_args))


def _options_to_cli(options):
    """
    Assemble an ssh(1) or sshpass(1) command line with -o options.
    """
    list_opts = []
    for key, value in options.items():
        if isinstance(value, (list, tuple, set)):
            list_opts += (f"-o{key}={v}" for v in value)
        else:
            list_opts.append(f"-o{key}={value}")
    return list_opts


def _options_to_ssh(options, password=None, extra_cli_flags=()):
    """
    Assemble an ssh(1) or sshpass(1) command line with -o options.
    """
    cli_opts = _options_to_cli(options)
    if password:
        return (
            "sshpass", "-p", password,
            "ssh", *extra_cli_flags, "-oBatchMode=no", *cli_opts,
            "ignored_arg",
        )
    else:
        # let cli_opts override BatchMode if specified
        return ("ssh", *extra_cli_flags, *cli_opts, "-oBatchMode=yes", "ignored_arg")


# return a string usable for rsync -e
def _options_to_rsync_e(options, password=None):
    """
    Return a string usable for the rsync -e argument.
    """
    cli_opts = _options_to_cli(options)
    batch_mode = "-oBatchMode=no" if password else "-oBatchMode=yes"
    return " ".join(("ssh", *cli_opts, batch_mode))  # no ignored_arg inside -e


def _rsync_host_cmd(*args, options, password=None, sudo=None):
    """
    Assemble a rsync command line, noting that
      - 'sshpass' must be before 'rsync', not inside the '-e' argument
      - 'ignored_arg' must be passed by user as destination, not inside '-e'
      - 'sudo' is part of '--rsync-path', yet another argument
    """
    return (
        *(("sshpass", "-p", password) if password else ()),
        "rsync",
        "-e", _options_to_rsync_e(options, password=password),
        "--rsync-path", _shell_cmd(("rsync",), sudo=sudo),
        *args,
    )


class StatelessSSHConn(Connection):
    """
    Implements the Connection API using a ssh(1) client using "standalone"
    (stateless) logic - connect() and disconnect() are no-op, .cmd() simply
    executes the ssh client and .rsync() executes 'rsync -e ssh'.

    Compared to ManagedSSHConn, this may be slow for many .cmd() calls,
    but every call is stateless, there is no persistent connection.

    If you need only one .cmd(), this will be faster than ManagedSSHConn.
    """

    def __init__(self, options, *, password=None, sudo=None):
        """
        Prepare to connect to an SSH server specified in 'options'.

        If 'password' is given, spawn the ssh(1) command via 'sshpass' and
        pass the password to it.

        If 'sudo' specifies a username, call sudo(8) on the remote shell
        to run under a different user on the remote host.
        """
        self.options = DEFAULT_OPTIONS.copy()
        self.options.update(options)
        self.password = password
        self.sudo = sudo
        self._tmpdir = None
        self._master_proc = None

    def connect(self, block=True):
        """
        Optional, .cmd() and .rsync() work without it, but it is provided here
        for compatibility with the Connection API.
        """
        # TODO: just wait until .cmd(['true']) starts responding ?
        pass

    def disconnect(self):
        pass

    # have options as kwarg to be compatible with other functions here
    def cmd(self, command, options=None, func=util.subprocess_run, **func_args):
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        if command:
            unified_options["RemoteCommand"] = _shell_cmd(command, sudo=self.sudo)
        return func(
            _options_to_ssh(unified_options, password=self.password),
            skip_frames=1,
            **func_args,
        )

    def rsync(self, *args, options=None, func=util.subprocess_run, **func_args):
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        return func(
            _rsync_host_cmd(
                *args,
                options=unified_options,
                password=self.password,
                sudo=self.sudo,
            ),
            skip_frames=1,
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )


# Note that when ControlMaster goes away (connection breaks), any ssh clients
# connected through it will time out after a combination of
#   ServerAliveCountMax + ServerAliveInterval + ConnectionAttempts
# identical to the ControlMaster process.
# Specifying different values for the clients, to make them exit faster when
# the ControlMaster dies, has no effect. They seem to ignore the options.
#
# If you need to kill the clients quickly after ControlMaster disconnects,
# you need to set up an independent polling logic (ie. every 0.1sec) that
# checks .assert_master() and manually signals the running clients
# when it gets DisconnectedError from it.

class ManagedSSHConn(Connection):
    """
    Implements the Connection API using one persistently-running ssh(1) client
    started in a 'ControlMaster' mode, with additional ssh clients using that
    session to execute remote commands. Similarly, .rsync() uses it too.

    This is much faster than StatelessSSHConn when executing multiple commands,
    but contains a complex internal state (what if ControlMaster disconnects?).

    Hence why this implementation provides extra non-standard-Connection methods
    to manage this complexity.
    """

    # TODO: thread safety and locking via self.lock ?

    def __init__(self, options, *, password=None, sudo=None):
        """
        Prepare to connect to an SSH server specified in 'options'.

        If 'password' is given, spawn the ssh(1) command via 'sshpass' and
        pass the password to it.

        If 'sudo' specifies a username, call sudo(8) on the remote shell
        to run under a different user on the remote host.
        """
        self.lock = threading.RLock()
        self.options = DEFAULT_OPTIONS.copy()
        self.options.update(options)
        self.password = password
        self.sudo = sudo
        self._tmpdir = None
        self._master_proc = None

    def assert_master(self):
        proc = self._master_proc
        if not proc:
            raise NotConnectedError("SSH ControlMaster is not running")
        # we need to consume any potential proc output for the process to
        # actually terminate (stop being a zombie) if it crashes
        out = proc.stdout.read()
        code = proc.poll()
        if code is not None:
            self._master_proc = None
            out = f":\n{out.decode()}" if out else ""
            raise DisconnectedError(
                f"SSH ControlMaster on {self._tmpdir} exited with {code}{out}",
            )

    def disconnect(self):
        proc = self._master_proc
        if not proc:
            return
        util.debug(f"disconnecting: {self.options}")
        proc.kill()
        # don't zombie forever, return EPIPE on any attempts to write to us
        proc.stdout.close()
        proc.wait()
        (self._tmpdir / "control.sock").unlink(missing_ok=True)
        self._master_proc = None

    def connect(self, block=True):
        if not self._tmpdir:
            # _tmpdir_handle just prevents the TemporaryDirectory instance
            # from being garbage collected (and removed on disk)
            # TODO: create/remove it explicitly in connect/disconnect
            #       so the removal happens immediately, even if GC delays cleaning
            self._tmpdir_handle = tempfile.TemporaryDirectory(prefix="atex-ssh-")
            self._tmpdir = Path(self._tmpdir_handle.name)

        sock = self._tmpdir / "control.sock"

        if not self._master_proc:
            util.debug(f"connecting: {self.options}")
            options = self.options.copy()
            options["SessionType"] = "none"
            options["ControlMaster"] = "yes"
            options["ControlPath"] = sock
            self._master_proc = util.subprocess_Popen(
                _options_to_ssh(options, password=self.password),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self._tmpdir),
                start_new_session=True,  # resist Ctrl-C
            )
            os.set_blocking(self._master_proc.stdout.fileno(), False)

        # NOTE: ideally, we would .read() before checking .poll() because
        #       if the process writes a lot, it gets stuck in the pipe
        #       (in kernel) and the process never ends; but output-appending
        #       code would be obscure, and ssh(1) never outputs that much ..

        proc = self._master_proc
        if block:
            while proc.poll() is None:
                if sock.exists():
                    break
                time.sleep(0.1)
            else:
                code = proc.poll()
                out = proc.stdout.read()
                self._master_proc = None
                raise ConnectError(
                    f"SSH ControlMaster failed to start on {self._tmpdir} with {code}:\n{out}",
                )
        else:
            code = proc.poll()
            if code is not None:
                out = proc.stdout.read()
                self._master_proc = None
                raise ConnectError(
                    f"SSH ControlMaster failed to start on {self._tmpdir} with {code}:\n{out}",
                )
            elif not sock.exists():
                raise BlockingIOError("SSH ControlMaster not yet ready")

    def forward(self, forward_type, *spec, cancel=False):
        """
        Add (one or more) ssh forwarding specifications as 'spec' to an
        already-connected instance. Each specification has to follow the
        format of LocalForward or RemoteForward (see ssh_config(5)).
        Ie. "1234 1.2.3.4:22" or "0.0.0.0:1234 1.2.3.4:22".

        'forward_type' must be either LocalForward or RemoteForward.

        If 'cancel' is True, cancel the forwarding instead of adding it.
        """
        assert forward_type in ("LocalForward", "RemoteForward")
        self.assert_master()
        options = DEFAULT_OPTIONS.copy()
        options[forward_type] = spec
        options["ControlPath"] = self._tmpdir / "control.sock"
        action = "forward" if not cancel else "cancel"
        util.subprocess_run(
            _options_to_ssh(options, extra_cli_flags=("-O", action)),
            skip_frames=1,
            check=True,
        )

    def cmd(self, command, *, options=None, func=util.subprocess_run, **func_args):
        self.assert_master()
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        if command:
            unified_options["RemoteCommand"] = _shell_cmd(command, sudo=self.sudo)
        unified_options["ControlPath"] = self._tmpdir / "control.sock"
        return func(
            _options_to_ssh(unified_options),
            skip_frames=1,
            **func_args,
        )

    def rsync(self, *args, options=None, func=util.subprocess_run, **func_args):
        self.assert_master()
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        unified_options["ControlPath"] = self._tmpdir / "control.sock"
        return func(
            _rsync_host_cmd(
                *args,
                options=unified_options,
                sudo=self.sudo,
            ),
            skip_frames=1,
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )
