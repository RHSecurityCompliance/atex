import subprocess

from .log import debug, extradebug


def subprocess_run(cmd, **kwargs):
    """
    A simple wrapper for the real subprocess.run() that logs the command used.
    """
    # when logging, skip current stack frame - report the place we were called
    # from, not util.subprocess_run itself
    debug(f"running: '{cmd}' with {kwargs=}")
    return subprocess.run(cmd, **kwargs)


def subprocess_output(cmd, *, check=True, text=True, **kwargs):
    """
    A wrapper simulating subprocess.check_output() via a modern .run() API.
    """
    debug(f"running: '{cmd}' with {check=}, {text=} and {kwargs=}")
    proc = subprocess.run(cmd, check=check, text=text, stdout=subprocess.PIPE, **kwargs)
    return proc.stdout.rstrip("\n") if text else proc.stdout


def subprocess_Popen(cmd, **kwargs):  # noqa: N802
    """
    A simple wrapper for the real subprocess.Popen() that logs the command used.
    """
    debug(f"running: '{cmd}' with {kwargs=}")
    return subprocess.Popen(cmd, **kwargs)


def subprocess_stream(cmd, *, stream="stdout", check=False, input=None, **kwargs):
    """
    Run 'cmd' via subprocess.Popen() and return an iterator over any lines
    the command outputs on stdout, in text mode.

    The 'stream' is a subprocess.Popen attribute (either 'stdout' or 'stderr')
    to read from.
    To capture both stdout and stderr as yielded lines, use 'stream="stdout"'
    and pass an additional 'stderr=subprocess.STDOUT'.

    With 'check' set to True, raise a CalledProcessError if the 'cmd' failed.

    Similarly, 'input' simulates the 'input' arg of subprocess.run().
    Note that the input is written to stdin of the process *before* any outputs
    are streamed, so it should be sufficiently small and/or not cause a deadlock
    with the process waiting for outputs to be read before consuming more input.
    Use 'stdin=subprocess.PIPE' and write to it manually if you need more.
    """
    all_kwargs = {
        "text": True,
        stream: subprocess.PIPE,
    }
    if input is not None:
        all_kwargs["stdin"] = subprocess.PIPE
    all_kwargs |= kwargs

    debug(f"running: '{cmd}' with {all_kwargs=}")
    proc = subprocess.Popen(cmd, **all_kwargs)

    def generate_lines():
        if input is not None:
            proc.stdin.write(input)
            proc.stdin.close()
        line_stream = getattr(proc, stream)
        for line in line_stream:
            yield line.rstrip("\n")
        code = proc.wait()
        if code > 0 and check:
            raise subprocess.CalledProcessError(cmd=cmd, returncode=code)

    return (proc, generate_lines())


def subprocess_log(cmd, **kwargs):
    """
    A wrapper to stream every (text) line output from the process to the
    logging module.

    Uses subprocess_stream() to gather the lines.
    """
    debug(f"running: '{cmd}' with {kwargs=}")
    _, lines = subprocess_stream(cmd, **kwargs)
    for line in lines:
        extradebug(line)
