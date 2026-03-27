import importlib
import pkgutil
from abc import ABC, abstractmethod

from ..connection import Connection


class Remote(Connection):
    @abstractmethod
    def release(self):
        """
        Release (de-provision) the remote resource.
        """


class Provisioner(ABC):
    @abstractmethod
    def provision(self, count=1):
        """
        Request that `count` machines be provisioned (reserved) for use,
        to be returned at a later point by `.get_remote()`.
        """

    @abstractmethod
    def get_remote(self, block=True):
        """
        Return a connected class Remote instance of a previously
        `.provision()`ed remote system.

        - If `block` is True, wait for the Remote to be available and connected,
          otherwise return None if there is none available yet.
        """

    @abstractmethod
    def clear(self):
        """
        Cancel any previous `.provision()` requests, preventing `.get_remote()`
        (currently running and future) calls from receiving Remotes until
        `.provision()` is called to request more machines.
        This does not release any Remotes already returned via `.get_remote()`.
        """

    @abstractmethod
    def start(self):
        """
        Start the Provisioner instance, start any provisioning-related
        processes that lead to systems being reserved.
        """

    @abstractmethod
    def stop(self):
        """
        Stop the Provisioner instance, freeing all reserved resources,
        calling `.release()` on all Remote instances that were created.
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


class ProvisionerError(Exception):
    pass


_submodules = tuple(
    info.name for info in pkgutil.iter_modules(__spec__.submodule_search_locations)
)

__all__ = (Provisioner.__name__, Remote.__name__, *_submodules)  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
