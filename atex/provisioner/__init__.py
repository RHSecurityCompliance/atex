import importlib as _importlib
import pkgutil as _pkgutil

from .. import connection as _connection


class Remote(_connection.Connection):
    """
    Representation of a provisioned (reserved) remote system, providing
    a Connection-like API in addition to system management helpers.

    An instance of Remote is typically prepared by a Provisioner and returned
    to the caller for use and an eventual .release().

    Also note that Remote can be used via Context Manager, but does not
    do automatic .release(), the manager only handles the built-in Connection.
    The intention is for a Provisioner to run via its own Contest Manager and
    release all Remotes upon exit.
    If you need automatic release of one Remote, use a try/finally block.
    """

    def release(self):
        """
        Release (de-provision) the remote resource.
        """
        raise NotImplementedError(f"'release' not implemented for {self.__class__.__name__}")


class Provisioner:
    """
    A remote resource (machine/system) provider.

    The idea is to request machines (a.k.a. Remotes, or class Remote instances)
    to be reserved via a non-blocking .provision() and for them to be retrieved
    through blocking / non-blocking .get_remote() when they become available.

    Each Remote has its own .release() for freeing (de-provisioning) it once
    the user doesn't need it anymore. The Provisioner does this automatically
    to all Remotes during .stop() or context manager exit.

        p = Provisioner()
        p.start()
        p.provision(count=1)
        remote = p.get_remote()
        remote.cmd(["ls", "/"])
        remote.release()
        p.stop()

        with Provisioner() as p:
            p.provision(count=2)
            remote1 = p.get_remote()
            remote2 = p.get_remote()
            ...

    Note that .provision() is a hint expressed by the caller, not a guarantee
    that .get_remote() will ever return a Remote. Ie. the caller can call
    .provision(count=math.inf) to receive as many remotes as the Provisioner
    can possibly supply.
    """

    def provision(self, count=1):
        """
        Request that 'count' machines be provisioned (reserved) for use,
        to be returned at a later point by .get_remote().
        """
        raise NotImplementedError(f"'provision' not implemented for {self.__class__.__name__}")

    def get_remote(self, block=True):
        """
        Return a connected class Remote instance of a previously .provision()ed
        remote system.

        If 'block' is True, wait for the Remote to be available and connected,
        otherwise return None if there is none available yet.
        """
        raise NotImplementedError(f"'get_remote' not implemented for {self.__class__.__name__}")

    def start(self):
        """
        Start the Provisioner instance, start any provisioning-related
        processes that lead to systems being reserved.
        """
        raise NotImplementedError(f"'start' not implemented for {self.__class__.__name__}")

    def stop(self):
        """
        Stop the Provisioner instance, freeing all reserved resources,
        calling .release() on all Remote instances that were created.
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

__all__ = [*_submodules, Provisioner.__name__, Remote.__name__]  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
