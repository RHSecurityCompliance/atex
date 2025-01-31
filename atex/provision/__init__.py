import importlib
import pkgutil

from .. import util


class Provisioner(util.LockableClass):
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
        super().__init__()

    def reserve(self):
        """
        Send a reservation request for a resource and wait for it to be
        reserved.
        """
        raise NotImplementedError(f"'reserve' not implemented for {self.__class__.__name__}")

    def connection(self):
        """
        Return an atex.ssh.SSHConn instance configured for connection to
        the reserved resource, but not yet connected.
        """
        raise NotImplementedError(f"'connection' not implemented for {self.__class__.__name__}")

    def release(self):
        """
        Release a reserved resource, or cancel a reservation-in-progress.
        """
        raise NotImplementedError(f"'release' not implemented for {self.__class__.__name__}")

    def alive(self):
        """
        Return True if the resource is still reserved, False otherwise.
        """
        raise NotImplementedError(f"'alive' not implemented for {self.__class__.__name__}")


def find_provisioners():
    provisioners = []
    for info in pkgutil.iter_modules(__spec__.submodule_search_locations):
        mod = importlib.import_module(f'.{info.name}', __name__)
        # look for Provisioner-derived classes in the module
        for attr in dir(mod):
            if attr.startswith('_'):
                continue
            value = getattr(mod, attr)
            try:
                if issubclass(value, Provisioner):
                    provisioners.append(attr)
            except TypeError:
                pass
    return provisioners
