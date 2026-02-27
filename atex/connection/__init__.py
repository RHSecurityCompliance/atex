import abc as _abc
import importlib as _importlib
import pkgutil as _pkgutil

from .. import util as _util


class Connection:
    def __enter__(self):
        try:
            self.connect()
            return self
        except Exception:
            self.disconnect()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()

    @_abc.abstractmethod
    def connect(self, block=True):
        """
        Establish a persistent connection to the remote.

        If `block` is True, wait for the connection to be up,
        otherwise raise BlockingIOError if the connection is still down.
        """

    @_abc.abstractmethod
    def disconnect(self):
        """
        Destroy the persistent connection to the remote.
        """

    @_abc.abstractmethod
    def cmd(self, command, *, func=_util.subprocess_run, **func_args):
        """
        Execute a single command on the remote, using subprocess-like semantics.

        - `command` is the command with arguments, as a tuple/list.

        - `func` is the subprocess function to use (`.run()`, `.Popen()`, etc.).

        - `func_args` are further keyword arguments to pass to `func`.
        """

    @_abc.abstractmethod
    def rsync(self, *args, func=_util.subprocess_run, **func_args):
        """
        Synchronize local/remote files/directories via `rsync`.

        Pass `*args` like `rsync(1)` CLI arguments, incl. option arguments, ie.

            .rsync("-vr", "local_path/", "remote:remote_path")
            .rsync("-z", "remote:remote_file" ".")

        To indicate remote path, use any string followed by a colon, the remote
        name does not matter as an internally-handled `-e` option dictates all
        the connection details.

        - `func` is a subprocess function to use (`.run()`, `.Popen()`, etc.).

        - `func_args` are further keyword arguments to pass to `func`.

        The remote must have the `rsync` command already installed.
        """


_submodules = [
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
]

__all__ = [*_submodules, Connection.__name__]  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
