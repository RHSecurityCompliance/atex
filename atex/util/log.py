import os
import logging
import inspect

_logger = logging.getLogger("atex")

# which functions to skip when determining the logger function caller;
# typically, these are wrappers and we want to see their caller in the trace
# instead of them
#
# ( file basename , qualname )
# where qualname is '<module>' or 'funcname' or 'Classname.funcname'
skip_levels = {
    ("subprocess.py", "subprocess_run"),
    ("subprocess.py", "subprocess_output"),
    ("subprocess.py", "subprocess_Popen"),
    ("subprocess.py", "subprocess_stream"),
    ("subprocess.py", "subprocess_log"),

    ("podman.py", "PodmanConnection.cmd"),
    ("podman.py", "PodmanConnection.rsync"),

    ("ssh.py", "StatelessSSHConnection.cmd"),
    ("ssh.py", "StatelessSSHConnection.rsync"),
    ("ssh.py", "ManagedSSHConnection.forward"),
    ("ssh.py", "ManagedSSHConnection.cmd"),
    ("ssh.py", "ManagedSSHConnection.rsync"),
}


def _log_msg(logger_func, *args, stacklevel=1, **kwargs):
    # inspect.stack() is MUCH slower
    caller = inspect.currentframe().f_back.f_back
    extra_levels = 2  # skip this func and the debug/info/warning parent
    while caller.f_back:
        code = caller.f_code
        # pathlib is much slower
        basename = os.path.basename(code.co_filename)  # noqa: PTH119
        qualname = code.co_qualname
        if (basename, qualname) in skip_levels:
            extra_levels += 1
            caller = caller.f_back
        else:
            break
    return logger_func(*args, stacklevel=stacklevel+extra_levels, **kwargs)


def warning(*args, **kwargs):
    return _log_msg(_logger.warning, *args, **kwargs)


def info(*args, **kwargs):
    return _log_msg(_logger.info, *args, **kwargs)


def debug(*args, **kwargs):
    return _log_msg(_logger.debug, *args, **kwargs)


# add a log level more verbose than logging.DEBUG, for verbose command
# outputs, big JSON / XML printouts, and other outputs unsuitable for
# large parallel runs; to be used in targeted debugging
#
# logging.DEBUG is 10, and programs tend to add TRACE as 5, so be somewhere
# in between
EXTRADEBUG = 8
logging.addLevelName(EXTRADEBUG, "EXTRADEBUG")


def extradebug(*args, **kwargs):
    return _log_msg(_logger.log, EXTRADEBUG, *args, **kwargs)
