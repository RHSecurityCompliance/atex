import abc as _abc
import importlib as _importlib
import pkgutil as _pkgutil
from pathlib import PurePath as _PurePath

from ..connection import Connection as _Connection


class Executor(_abc.ABC):
    @_abc.abstractmethod
    def __init__(self, connection: _Connection):
        """
        Initialize the Executor.

        - `connection` is used for test upload, preparation and execution.
        """

    @_abc.abstractmethod
    def run_test(self, test_name: str, artifacts: str | _PurePath) -> int:
        """
        Run one test on the remote system.

        - `artifacts` is a destination dir for results reported and files
          uploaded by the test.

          Results are always stored in a line-JSON format in a file named
          `results`, files are always uploaded to directory named `files`,
          both inside `artifacts`.

          The path for `artifacts` must already exist and be an empty directory
          (ie. typically a tmpdir).

        Returns an exit code of the test script.
        """

    @_abc.abstractmethod
    def start(self) -> None:
        """
        Start the Executor instance, uploading tests, setting up the system
        for test execution, etc.
        """

    @_abc.abstractmethod
    def stop(self) -> None:
        """
        Stop the Executor instance, cleaning the system up after test execution.
        """

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


class ExecutorError(Exception):
    pass


_submodules = tuple(
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Executor.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
