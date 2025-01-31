import importlib as _importlib
import pkgutil as _pkgutil
import threading as _threading

from .. import connection as _connection


class Provisioner:
    """
    A resource (machine/system) provider.

    Any class derived from Provisioner serves as a mechanisms for requesting
    a resource (machine/system), waiting for it to be reserved, providing ssh
    details on how to connect to it, and releasing it when no longer useful.

    The 4 main API points for this are reserve(), connection(), release() and
    alive().
    If necessary, these methods can share data via class instance attributes,
    which are transparently guarded by a thread-aware mutex. For any complex
    reads/writes, use 'self.lock' via a context manager.

    Note that reserve() always runs in a separate thread (and thus may block),
    and other functions (incl. release()) may be called at any time from
    a different thread, even while reserve() is still running.
    It is thus recommended for reserve() to store metadata in self.* as soon
    as the metadata becomes available (some job ID, request UUID, Popen proc
    object with PID, etc.) so that release() can free the resource at any time.

    Once release()'d, the instance is never reused for reserve() again.
    However connection(), release() and alive() may be called several times at
    any time and need to handle it safely.
    Ie. once released(), an instance must never return alive() == True.

        # explicit method calls
        res = Provisioner(...)
        res.reserve()
        conn = res.connection()
        conn.connect()
        conn.ssh('ls /')
        conn.disconnect()
        res.release()

        # via a context manager
        with Provisioner(...) as res:
            with res.connection() as conn:
                conn.ssh('ls /')

    If a Provisioner class needs additional configuration, it should do so via
    class (not instance) attributes, allowing it to be instantiated many times.

        class ConfiguredProvisioner(Provisioner):
            resource_hub = 'https://...'
            login = 'joe'

        # or dynamically
        name = 'joe'
        cls = type(
            f'Provisioner_for_{name}',
            (Provisioner,),
            {'resource_hub': 'https://...', 'login': name},
        )

    These attributes can then be accessed from __init__ or any other function.
    """

    def __init__(self):
        """
        Initialize the provisioner instance.
        If extending __init__, always call 'super().__init__()' at the top.
        """
        self.lock = _threading.RLock()

#    def reserve(self):
#        """
#        Send a reservation request for a resource and wait for it to be
#        reserved.
#        """
#        raise NotImplementedError(f"'reserve' not implemented for {self.__class__.__name__}")
#
#    def connection(self):
#        """
#        Return an atex.ssh.SSHConn instance configured for connection to
#        the reserved resource, but not yet connected.
#        """
#        raise NotImplementedError(f"'connection' not implemented for {self.__class__.__name__}")
#
#    def release(self):
#        """
#        Release a reserved resource, or cancel a reservation-in-progress.
#        """
#        raise NotImplementedError(f"'release' not implemented for {self.__class__.__name__}")
#
#    def alive(self):
#        """
#        Return True if the resource is still reserved, False otherwise.
#        """
#        raise NotImplementedError(f"'alive' not implemented for {self.__class__.__name__}")


class Remote(_connection.Connection):
    """
    Representation of a provisioned (reserved) remote system, providing
    a Connection-like API in addition system management helpers.

    An instance of Remote is typically prepared by a Provisioner and given
    away for further use, to be .release()d by the user. It is not meant
    for repeated reserve/release cycles, hence the lack of .reserve().

    Also note that Remote can be used via Context Manager, but does not
    do automatic .release(), the manager only handles the built-in Connection.
    The intention is for a Provisioner to run via its own Contest Manager and
    release all Remotes upon exit.
    If you need automatic release of one Remote, use a contextlib.ExitStack
    with a callback, or a try/finally block.
    """

    # TODO: pass platform as arg ?
    #def __init__(self, platform, *args, **kwargs):
    #    """
    #    Initialize a new Remote instance based on a Connection instance.
    #    If extending __init__, always call 'super().__init__(conn)' at the top.
    #    """
    #    self.lock = _threading.RLock()
    #    self.platform = platform

    def release(self):
        """
        Release (de-provision) the remote resource, freeing resources.
        """
        raise NotImplementedError(f"'release' not implemented for {self.__class__.__name__}")

    def alive(self):
        """
        Return True if the remote resource is still valid and reserved.
        """
        raise NotImplementedError(f"'alive' not implemented for {self.__class__.__name__}")


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
