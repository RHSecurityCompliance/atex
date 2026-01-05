import importlib as _importlib
import pkgutil as _pkgutil


class Aggregator:
    """
    TODO: generic description, not JSON-specific
    """

    def ingest(self, platform, test_name, test_results, test_files):
        """
        Process 'test_results' (string/Path) for as results reported by a test
        ran by Executor, along with 'test_files' as files uploaded by that test,
        aggregating them under 'platform' (string) as 'test_name' (string).

        This is DESTRUCTIVE, the input results/files are consumed in the
        process.
        """
        raise NotImplementedError(f"'ingest' not implemented for {self.__class__.__name__}")

    def start(self):
        """
        Start the Aggregator instance, opening any files / allocating resources
        as necessary.
        """
        raise NotImplementedError(f"'start' not implemented for {self.__class__.__name__}")

    def stop(self):
        """
        Stop the Aggregator instance, freeing all allocated resources.
        """
        raise NotImplementedError(f"'stop' not implemented for {self.__class__.__name__}")

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


_submodules = [
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
]

__all__ = [*_submodules, Aggregator.__name__]  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
