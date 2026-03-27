import abc as _abc
import importlib as _importlib
import pkgutil as _pkgutil
from pathlib import PurePath as _PurePath


class Aggregator(_abc.ABC):
    @_abc.abstractmethod
    def ingest(self, platform: str, test_name: str, artifacts: str | _PurePath) -> None:
        """
        Process `artifacts` for results reported and files uploaded by
        a test ran by an Executor, aggregating them under `platform`
        as `test_name`.

        This is **destructive**, the artifacts are consumed in the process.
        """

    @_abc.abstractmethod
    def start(self) -> None:
        """
        Start the Aggregator instance, opening any files / allocating resources
        as necessary.
        """

    @_abc.abstractmethod
    def stop(self) -> None:
        """
        Stop the Aggregator instance, freeing all allocated resources.
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


class AggregatorError(Exception):
    pass


_submodules = tuple(
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Aggregator.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
