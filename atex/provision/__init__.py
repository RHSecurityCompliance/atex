import importlib as _importlib
import pkgutil as _pkgutil

from .. import connection as _connection


class Provisioner:
    """
    A remote resource (machine/system) provider.

    The main interface is .get_remote() that returns a connected class Remote
    instance for use by the user, to be .release()d when not needed anymore,
    with Provisioner automatically getting a replacement for it, to be returned
    via .get_remote() later.

        p = Provisioner()
        p.start()
        remote = p.get_remote()
        remote.cmd(["ls", "/"])
        remote.release()
        p.stop()

        with Provisioner() as p:
            remote = p.get_remote()
            ...
            remote.release()

    TODO: mention how a Provisioner always needs to take care of release all Remotes
          when .stop()ped or when context terminates; even the ones handed over to
          the user

    Note that .stop() or .defer_stop() may be called from a different
    thread, asynchronously to any other functions.
    """

    def get_remote(self, block=True):
        """
        Get a connected class Remote instance.

        If 'block' is True, wait for the remote to be available and connected,
        otherwise return None if there is no Remote available yet.
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

    def stop_defer(self):
        """
        Enable an external caller to stop the Provisioner instance,
        deferring resource deallocation to the caller.

        Return an iterable of argument-free thread-safe callables that can be
        called, possibly in parallel, to free up resources.
        Ie. a list of 200 .release() functions, to be called in a thread pool
        by the user, speeding up cleanup.
        """
        return (self.stop,)

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()


class Remote(_connection.Connection):
    """
    Representation of a provisioned (reserved) remote system, providing
    a Connection-like API in addition to system management helpers.

    An instance of Remote is typically prepared by a Provisioner and lent out
    for further use, to be .release()d by the user (if destroyed).
    It is not meant for repeated reserve/release cycles, hence the lack
    of .reserve().

    Also note that Remote can be used via Context Manager, but does not
    do automatic .release(), the manager only handles the built-in Connection.
    The intention is for a Provisioner to run via its own Contest Manager and
    release all Remotes upon exit.
    If you need automatic release of one Remote, use a contextlib.ExitStack
    with a callback, or a try/finally block.
    """

    def release(self):
        """
        Release (de-provision) the remote resource.
        """
        raise NotImplementedError(f"'release' not implemented for {self.__class__.__name__}")


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
