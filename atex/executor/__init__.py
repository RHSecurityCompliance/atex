import importlib
import pkgutil
from abc import ABC, abstractmethod


class Executor(ABC):
    @abstractmethod
    def __init__(self, connection):
        """
        Initialize the Executor.

        - `connection` is used for test upload, preparation and execution.
        """

    @abstractmethod
    def run_test(self, test_name, artifacts):
        """
        Run one test on the remote system.

        - `test_name` is a string with test name.

        - `artifacts` is a destination dir (string or Path) for results reported
          and files uploaded by the test.

          Results are always stored in a line-JSON format in a file named
          `results`, files are always uploaded to directory named `files`,
          both inside `artifacts`.

          The path for `artifacts` must already exist and be an empty directory
          (ie. typically a tmpdir).

        Returns an integer exit code of the test script.
        """

    @abstractmethod
    def start(self):
        """
        Start the Executor instance, uploading tests, setting up the system
        for test execution, etc.
        """

    @abstractmethod
    def stop(self):
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
    info.name for info in pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Executor.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
