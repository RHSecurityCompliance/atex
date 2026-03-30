import importlib
import pkgutil
from abc import ABC, abstractmethod


class Aggregator(ABC):
    @abstractmethod
    def ingest(self, platform, test_name, artifacts):
        """
        Process `artifacts` (string/Path) for results reported and files
        uploaded by a test run by an Executor, aggregating them under
        `platform` (string) as `test_name` (string).

        This is **destructive**, the artifacts are consumed in the process.
        """

    @abstractmethod
    def start(self):
        """
        Start the Aggregator instance, opening any files / allocating resources
        as necessary.
        """

    @abstractmethod
    def stop(self):
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
    info.name for info in pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Aggregator.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
