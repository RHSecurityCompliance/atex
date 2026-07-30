import functools
import threading

from ... import util
from .. import Provisioner, ProvisionerError, Remote

_get_logger = util.get_loggers("atex.provisioner.anyconn")


class AnyConnectionRemoteBase:
    """
    Mixin providing `.release()` for dynamically-created Remote types.

    The release state is set up via `__init_remote()` after construction,
    keeping `__init__` free for the connection type's own constructor.
    """

    # conn_type may define __eq__, which would make instances unhashable
    __hash__ = object.__hash__

    def __init_remote(self, release_hook):
        self.__lock = threading.RLock()
        self.__release_called = False
        self.__release_hook = release_hook

    def release(self):
        with self.__lock:
            if self.__release_called:
                return
            else:
                self.__release_called = True
        try:
            self.disconnect()
        finally:
            self.__release_hook(self)

    def __str__(self):
        # eg. AnyConnectionRemote[ManagedSSHConnection]()
        return f"{self.__class__.__name__}()"


@functools.cache
def _remote_type(conn_type):
    return type(
        f"AnyConnectionRemote[{conn_type.__name__}]",
        (AnyConnectionRemoteBase, Remote, conn_type),
        {"__module__": __name__},
    )


class AnyConnectionProvisioner(Provisioner):
    """
    - `conn_type` is a Connection class to instantiate for each remote.

    - `conn_args` and `conn_kwargs` are passed to `conn_type.__init__()`.

      The connection must not be connected after construction, the provisioner
      calls `.connect()` itself.

    - `max_remotes` is how many connected Connections can exist at any one time.
    """

    def __init__(self, conn_type, conn_args=None, conn_kwargs=None, *, max_remotes=10):
        self._lock = threading.Condition()
        self.logger = _get_logger()

        self.conn_type = conn_type
        self.conn_args = conn_args or ()
        self.conn_kwargs = conn_kwargs or {}
        self.max_remotes = max_remotes

        self._remotes = set()
        self._to_reserve = 0
        self._reserving = 0
        self._stopped = True

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._stopped = False

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._lock:
            self._stopped = True
            self._to_reserve = 0
            # wait for currently-reserving get_remote() to finish and
            # self-release based on self._stopped == True
            self._lock.notify_all()
            self._lock.wait_for(lambda: self._reserving == 0)
            to_release = self._remotes
            self._remotes = set()
        for remote in to_release:
            try:
                remote.release()
            except Exception:
                self.logger.warning(f"failed to release {remote}", exc_info=True)

    def provision(self, count=1):
        with self._lock:
            if self._stopped:
                raise ProvisionerError("the provisioner is stopped")
            self.logger.debug(f"provisioning {count}")
            self._to_reserve += count
            self._lock.notify(count)

    def _has_capacity(self):
        return len(self._remotes) + self._reserving < self.max_remotes

    def get_remote(self, block=True):
        with self._lock:
            if block:
                self._lock.wait_for(
                    lambda: (self._to_reserve > 0 and self._has_capacity()) or self._stopped,
                )

            if self._stopped:
                raise ProvisionerError("the provisioner is stopped")

            if self._to_reserve <= 0 or not self._has_capacity():
                return None

            self._to_reserve -= 1
            self._reserving += 1

        remote = None
        try:
            def release_hook(remote):
                self.logger.debug(f"releasing {remote}")
                # remove from the list of remotes inside this Provisioner
                with self._lock:
                    self._remotes.discard(remote)
                    self._lock.notify()

            remote_cls = _remote_type(self.conn_type)
            remote = remote_cls(*self.conn_args, **self.conn_kwargs)
            remote._AnyConnectionRemoteBase__init_remote(release_hook)
            remote.connect()
        except BaseException:
            with self._lock:
                self._reserving -= 1
                self._lock.notify()
            if remote is not None:
                try:
                    remote.release()
                except Exception:
                    self.logger.warning(f"failed to release {remote}", exc_info=True)
            raise

        with self._lock:
            self._reserving -= 1
            # if .stop() was called while .get_remote() was running
            if self._stopped:
                remote.release()
                raise ProvisionerError("the provisioner is stopped")
            self._remotes.add(remote)

        return remote

    def clear(self):
        with self._lock:
            self._to_reserve = 0

    def __str__(self):
        class_name = self.__class__.__name__
        remotes = f"{len(self._remotes)}/{self.max_remotes}"
        return f"{class_name}({self.conn_type.__name__}, {remotes} remotes)"
