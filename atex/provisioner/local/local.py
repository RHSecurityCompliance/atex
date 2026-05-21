import threading

from ... import connection, util
from .. import Provisioner, Remote

get_logger = util.get_loggers("atex.provisioner.local")


class LocalRemote(Remote, connection.local.LocalConnection):
    """
    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.
    """

    def __init__(self, *, release_hook):
        self.lock = threading.RLock()
        self.release_called = False
        self.release_hook = release_hook

    def release(self):
        with self.lock:
            if self.release_called:
                return
            else:
                self.release_called = True
        self.disconnect()
        self.release_hook(self)

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}()"


class LocalProvisioner(Provisioner):
    def __init__(self):
        self.lock = threading.RLock()
        self.logger = get_logger()
        self.remotes = []
        self._requested = 0
        self._cond = threading.Condition()
        self.started = False

    def start(self):
        self.logger.debug(f"starting: {self}")
        self.started = True

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._cond:
            self.started = False
            self._cond.notify_all()
        with self.lock:
            while self.remotes:
                self.remotes.pop().release()

    def provision(self, count=1):
        assert count >= 0
        self.logger.debug(f"provisioning {count}")
        with self._cond:
            self._requested += count
            self._cond.notify(count)

    def get_remote(self, block=True):
        with self._cond:
            if block:
                self._cond.wait_for(lambda: self._requested > 0 or not self.started)
                if not self.started:
                    return None
            elif self._requested <= 0:
                return None
            self._requested -= 1

        def release_hook(remote):
            self.logger.debug(f"releasing {remote}")
            with self.lock:
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass

        remote = LocalRemote(release_hook=release_hook)
        self.remotes.append(remote)
        return remote

    def clear(self):
        with self._cond:
            self._requested = 0

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({len(self.remotes)} remotes)"
