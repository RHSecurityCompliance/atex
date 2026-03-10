import abc as _abc
import importlib as _importlib
import pkgutil as _pkgutil
import time as _time


class Orchestrator:
    @_abc.abstractmethod
    def serve_once(self):
        """
        Run the orchestration logic, processing any outstanding requests
        (for provisioning, new test execution, etc.) and returning once these
        are taken care of.

        Returns `True` to indicate that it should be called again by the user
        (more work to be done), `False` once all testing is concluded.
        """

    def serve_forever(self):
        """
        Run the orchestration logic, blocking until all testing is concluded.
        """
        while self.serve_once():
            _time.sleep(1)

    @_abc.abstractmethod
    def start(self):
        """
        Start the Orchestrator instance, opening any files / allocating
        resources as necessary.
        """

    @_abc.abstractmethod
    def stop(self):
        """
        Stop the Orchestrator instance, freeing all allocated resources.
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


class OrchestratorError(Exception):
    pass


_submodules = tuple(
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Orchestrator.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
