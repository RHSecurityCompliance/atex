import subprocess

from .log import debug


def subprocess_run(cmd, *, skip_frames=0, **kwargs):
    """
    A simple wrapper for the real subprocess.run() that logs the command used.
    """
    # when logging, skip current stack frame - report the place we were called
    # from, not util.subprocess_run itself
    debug(f"running: {cmd}", skip_frames=skip_frames+1)
    return subprocess.run(cmd, **kwargs)


def subprocess_output(cmd, *, skip_frames=0, check=True, text=True, **kwargs):
    """
    A wrapper simulating subprocess.check_output() via a modern .run() API.
    """
    debug(f"running: {cmd}", skip_frames=skip_frames+1)
    proc = subprocess.run(cmd, check=check, text=text, stdout=subprocess.PIPE, **kwargs)
    return proc.stdout.rstrip("\n") if text else proc.stdout


def subprocess_Popen(cmd, *, skip_frames=0, **kwargs):  # noqa: N802
    """
    A simple wrapper for the real subprocess.Popen() that logs the command used.
    """
    debug(f"running: {cmd}", skip_frames=skip_frames+1)
    return subprocess.Popen(cmd, **kwargs)


def subprocess_stream(cmd, *, check=False, skip_frames=0, **kwargs):
    """
    Run 'cmd' via subprocess.Popen() and return an iterator over any lines
    the command outputs on stdout, in text mode.

    With 'check' set to True, raise a CalledProcessError if the 'cmd' failed.

    To capture both stdout and stderr as yielded lines, use subprocess.STDOUT.
    """
    debug(f"running: {cmd}", skip_frames=skip_frames+1)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, **kwargs)

    def generate_lines():
        for line in proc.stdout:
            yield line.rstrip("\n")
        code = proc.wait()
        if code > 0 and check:
            raise subprocess.CalledProcessError(cmd=cmd, returncode=code)

    return (proc, generate_lines())
