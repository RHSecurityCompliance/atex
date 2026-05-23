import threading

from ... import connection, util
from .. import Provisioner, Remote

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
        self.disconnect()
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
        self._lock = threading.RLock()
        self.logger = _get_logger()
        self._remotes = []
        self._requested = 0
        self._cond = threading.Condition()
        self._started = False
        self.kwargs = kwargs

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._started = True

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._cond:
            self._started = False
            self._cond.notify_all()
        with self._lock:
            while self._remotes:
                self._remotes.pop().release()

    def provision(self, count=1):
        assert count >= 0
        self.logger.debug(f"provisioning {count}")
        with self._cond:
            self._requested += count
            self._cond.notify(count)

    def get_remote(self, block=True):
        with self._cond:
            if block:
                self._cond.wait_for(lambda: self._requested > 0 or not self._started)
                if not self._started:
                    return None
            elif self._requested <= 0:
                return None
            self._requested -= 1

        def release_hook(remote):
            self.logger.debug(f"releasing {remote}")
            with self._lock:
                try:
                    self._remotes.remove(remote)
                except ValueError:
                    pass

        remote = LocalRemote(release_hook=release_hook, **self.kwargs)
        self._remotes.append(remote)
        return remote

    def clear(self):
        with self._cond:
            self._requested = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({len(self._remotes)} remotes)"
