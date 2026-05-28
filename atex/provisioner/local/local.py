import threading

from ... import connection, util
from .. import Provisioner, ProvisionerError, Remote

_get_logger = util.get_loggers("atex.provisioner.local")


class LocalRemote(Remote, connection.local.LocalConnection):
    """
    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.

    - `kwargs` are passed to the underlying LocalConnection.
    """

    def __init__(self, *, release_hook, **kwargs):
        super().__init__(**kwargs)
        self._lock = threading.RLock()
        self._release_called = False
        self.release_hook = release_hook

    def release(self):
        with self._lock:
            if self._release_called:
                return
            else:
                self._release_called = True
        try:
            self.disconnect()
        finally:
            self.release_hook(self)

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}()"


class LocalProvisioner(Provisioner):
    """
    - `kwargs` are passed to LocalRemote and its underlying
      LocalConnection.
    """

    def __init__(self, **kwargs):
        self._lock = threading.Condition()
        self.logger = _get_logger()
        self._remotes = set()
        self._requested = 0
        self._stopped = True
        self.kwargs = kwargs

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._stopped = False

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._lock:
            self._stopped = True
            self._lock.notify_all()
            while self._remotes:
                self._remotes.pop().release()

    def provision(self, count=1):
        if self._stopped:
            raise ProvisionerError("the provisioner is stopped")

        self.logger.debug(f"provisioning {count}")
        with self._lock:
            self._requested += count
            self._lock.notify(count)

    def get_remote(self, block=True):
        with self._lock:
            if block:
                self._lock.wait_for(lambda: self._requested > 0 or self._stopped)

            if self._stopped:
                raise ProvisionerError("the provisioner is stopped")

            if self._requested <= 0:
                return None

            self._requested -= 1

            def release_hook(remote):
                self.logger.debug(f"releasing {remote}")
                with self._lock:
                    self._remotes.discard(remote)

            remote = LocalRemote(release_hook=release_hook, **self.kwargs)
            self._remotes.add(remote)
            return remote

    def clear(self):
        with self._lock:
            self._requested = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({len(self._remotes)} remotes)"
