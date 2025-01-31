import os
import time
import tempfile
import subprocess
from pathlib import Path

from . import util

DEFAULT_OPTIONS = {
    'LogLevel': 'ERROR',
    'StrictHostKeyChecking': 'no',
    'UserKnownHostsFile': '/dev/null',
    'ConnectionAttempts': '3',
    'ServerAliveCountMax': '4',
    'ServerAliveInterval': '5',
    'TCPKeepAlive': 'no',
    'EscapeChar': 'none',
    'ExitOnForwardFailure': 'yes',
#     'RequestTTY': 'force',
}


def _shell_cmd(args, sudo=None):
    """
    Make a command line for running 'args' on the target system.
    """
    if sudo:
        cmd = ('exec', 'sudo', '--no-update', '--non-interactive', '--user', sudo, '--', *args)
    else:
        cmd = ('exec', '--', *args)
    return ' '.join(cmd)


def _options_to_cli(options):
    """
    Assemble an ssh(1) or sshpass(1) command line with -o options.
    """
    list_opts = []
    for key, value in options.items():
        if isinstance(value, str):
            list_opts.append(f'-o{key}={value}')
        else:
            if len(value) == 0:
                raise ValueError(f"key {key} has an empty iterable value")
            list_opts += (f'-o{key}={v}' for v in value)
    return list_opts


def _options_to_ssh(options, password=None, extra_cli_flags=()):
    """
    Assemble an ssh(1) or sshpass(1) command line with -o options.
    """
    cli_opts = _options_to_cli(options)
    if password:
        return (
            'sshpass', '-p', password,
            'ssh', *extra_cli_flags, '-oBatchMode=no', *cli_opts,
            'ignored_arg',
        )
    else:
        # let cli_opts override BatchMode if specified
        return ('ssh', *extra_cli_flags, *cli_opts, '-oBatchMode=yes', 'ignored_arg')


# return a string usable for rsync -e
def _options_to_rsync_e(options, password=None):
    """
    Return a string usable for the rsync -e argument.
    """
    cli_opts = _options_to_cli(options)
    batch_mode = '-oBatchMode=no' if password else '-oBatchMode=yes'
    return ' '.join(('ssh', *cli_opts, batch_mode))  # no ignored_arg inside -e


def _rsync_host_cmd(*args, options, password=None, sudo=None):
    """
    Assemble a rsync command line, noting that
      - 'sshpass' must be before 'rsync', not inside the '-e' argument
      - 'ignored_arg' must be passed by user as destination, not inside '-e'
      - 'sudo' is part of '--rsync-path', yet another argument
    """
    return (
        *(('sshpass', '-p', password) if password else ()),
        'rsync',
        '-e', _options_to_rsync_e(options, password=password),
        '--rsync-path', _shell_cmd(('rsync',), sudo=sudo),
        *args,
    )


class SSHConn:
    r"""
    Represents a persistent SSH connection to a host (ControlMaster).

    When instantiated, it attempts to connect to the specified host, with any
    subsequent instance method calls using that connection, or raising
    ConnectionResetError when it is lost.

    The ssh(1) command is parametrized purely and solely via ssh_config(5)
    options, including 'Hostname', 'User', 'Port', etc.
    Pass any overrides or missing options as 'options' (dict).

        options = {
            'Hostname': '1.2.3.4',
            'User': 'testuser',
            'IdentityFile': '/home/testuser/.ssh/id_rsa',
        }

        # with a persistent ControlMaster
        conn = SSHConn(options)
        conn.connect()
        output = conn.run('ls /')
        #proc = conn.Popen('ls /')  # non-blocking
        conn.disconnect()

        # or as try/except/finally
        conn = SSHConn(options)
        try:
            conn.connect()
            ...
        finally:
            conn.disconnect()

        # or via Context Manager
        with SSHConn(options) as conn:
            ...
    """

    def __init__(self, options, *, password=None):
        """
        Connect to an SSH server specified in 'options'.

		If 'password' is given, spawn the ssh(1) command via 'sshpass' and
		pass the password to it.

		If 'sudo' specifies a username, call sudo(8) on the remote shell
		to run under a different user on the remote host.
        """
        self.options = DEFAULT_OPTIONS.copy()
        self.options.update(options)
        self.password = password
        self.tmpdir = None
        self.proc_master = None

    def _assert_master(self):
        proc = self.master_proc
        if not proc:
            raise RuntimeError("SSH ControlMaster is not running")
        # we need to consume any potential proc output for the process to
        # actually terminate (stop being a zombie) if it crashes
        proc = self.master_proc
        out = proc.stdout.read()
        code = proc.poll()
        if code is not None:
            self.master_proc = None
            raise RuntimeError(f"SSH ControlMaster on {self.tmpdir} exited with {code}:\n{out}")

    def disconnect(self):
        proc = self.master_proc
        if not proc:
            return
        proc.terminate()
        # don't zombie forever, return EPIPE on any attempts to write to us
        proc.stdout.close()
        proc.wait()
        self.master_proc = None

    def connect(self):
        if self.proc_master:
            raise FileExistsError(f"SSH ControlMaster process already running on {self.tmpdir}")

        if not self.tmpdir:
            self.tmpdir_handle = tempfile.TemporaryDirectory(prefix='atex-ssh-')
            self.tmpdir = Path(self.tmpdir_handle.name)

        options = self.options.copy()
        options['SessionType'] = 'none'
        options['ControlMaster'] = 'yes'
        sock = self.tmpdir / 'control.sock'
        options['ControlPath'] = sock

        # TODO: shouldn't password be handled here and passed to _options_to_ssh
        #       rather than for member .ssh() ?

        proc = util.subprocess_Popen(
            _options_to_ssh(options),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.tmpdir),
        )
        os.set_blocking(proc.stdout.fileno(), False)

        # wait for the master to either create the socket (indicating valid
        # connection) or give up and exit
        while proc.poll() is None:
            if sock.exists():
                break
            time.sleep(0.1)
        else:
            code = proc.poll()
            out = proc.stdout.read()
            raise FileNotFoundError(
                f"SSH ControlMaster failed to start on {self.tmpdir} with {code}:\n{out}",
            )

        self.master_proc = proc

    def add_local_forward(self, *spec):
        """
        Add (one or more) ssh forwarding specifications as 'spec' to an
        already-connected instance. Each specification has to follow the
        format of ssh client's LocalForward option (see ssh_config(5)).
        """
        self._assert_master()
        options = self.options.copy()
        options['LocalForward'] = spec
        options['ControlPath'] = self.tmpdir / 'control.sock'
        util.subprocess_run(
            _options_to_ssh(options, extra_cli_flags=('-O', 'forward')),
            skip_frames=1,
            check=True,
        )

    def add_remote_forward(self, *spec):
        """
        Add (one or more) ssh forwarding specifications as 'spec' to an
        already-connected instance. Each specification has to follow the
        format of ssh client's RemoteForward option (see ssh_config(5)).
        """
        self._assert_master()
        options = self.options.copy()
        options['RemoteForward'] = spec
        options['ControlPath'] = self.tmpdir / 'control.sock'
        util.subprocess_run(
            _options_to_ssh(options, extra_cli_flags=('-O', 'forward')),
            skip_frames=1,
            check=True,
        )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()

    def ssh(
        self, cmd, *args, options=None, sudo=None, text=True,
        func=util.subprocess_run, **run_kwargs,
    ):
        self._assert_master()
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        unified_options['RemoteCommand'] = _shell_cmd((cmd, *args), sudo=sudo)
        unified_options['ControlPath'] = self.tmpdir / 'control.sock'
        return func(
            _options_to_ssh(unified_options, password=self.password),
            skip_frames=1,
            text=text,
            **run_kwargs,
        )

    def rsync(
        self, *args, options=None, sudo=None,
        func=util.subprocess_run, **run_kwargs,
    ):
        self._assert_master()
        unified_options = self.options.copy()
        if options:
            unified_options.update(options)
        unified_options['ControlPath'] = self.tmpdir / 'control.sock'
        return func(
            _rsync_host_cmd(*args, options=unified_options, password=self.password, sudo=sudo),
            skip_frames=1,
            text=True,
            stdin=subprocess.DEVNULL,
            **run_kwargs,
        )


# have options as kwarg to be compatible with other functions here
def ssh(
    cmd, *args, options, password=None, sudo=None, text=True,
    func=util.subprocess_run, **run_kwargs,
):
    """
	Execute ssh(1) with the given options.

    On the remote system, run 'cmd' in a shell.

    If 'password' is given, spawn the ssh(1) command via 'sshpass' and
    pass the password to it.

    If 'sudo' specifies a username, call sudo(8) on the remote shell
    to run under a different user on the remote host.
    """
    unified_options = DEFAULT_OPTIONS.copy()
    unified_options['RemoteCommand'] = _shell_cmd((cmd, *args), sudo=sudo)
    unified_options.update(options)
    return func(
        _options_to_ssh(unified_options, password=password),
        skip_frames=1,
        text=text,
        **run_kwargs,
    )


def rsync(
    *args, options, password=None, sudo=None,
    func=util.subprocess_run, **run_kwargs,
):
    return func(
        _rsync_host_cmd(*args, options=options, password=password, sudo=sudo),
        skip_frames=1,
        text=True,
        stdin=subprocess.DEVNULL,
        **run_kwargs,
    )
