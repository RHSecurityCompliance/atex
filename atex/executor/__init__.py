import abc as _abc
import importlib as _importlib
import pkgutil as _pkgutil


class Executor:
    @_abc.abstractmethod
    def run_test(self, test_name, artifacts):
        """
        Request that `count` machines be provisioned (reserved) for use,
        to be returned at a later point by `.get_remote()`.
        """

    @_abc.abstractmethod
    def start(self):
        """
        Start the Executor instance, uploading tests, setting up the system
        for test execution, etc.
        """

    @_abc.abstractmethod
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
    """
    Raised by an Executor.
    """


_submodules = tuple(
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Executor.__name__, ExecutorError.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
