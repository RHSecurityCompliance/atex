import concurrent.futures
import threading
import time

from ... import connection, util
from .. import Provisioner, Remote
from . import api

_get_logger = util.get_loggers("atex.provisioner.testingfarm")


class TestingFarmRemote(Remote, connection.ssh.ManagedSSHConnection):
    """
    - `request_id` is a string with Testing Farm request UUID
      (for printouts).

    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.

    - `kwargs` are passed to the underlying ManagedSSHConnection.
    """

    def __init__(self, request_id, *, release_hook, **kwargs):
        super().__init__(**kwargs)
        self._lock = threading.RLock()
        self.request_id = request_id
        self.release_hook = release_hook
        self._release_called = False

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
        ssh_user = self.options.get("User", "unknown")
        ssh_host = self.options.get("Hostname", "unknown")
        ssh_port = self.options.get("Port", "unknown")
        ssh_key = self.options.get("IdentityFile", "unknown")
        return f"{class_name}({ssh_user}@{ssh_host}:{ssh_port}@{ssh_key}, {self.request_id})"


class TestingFarmProvisioner(Provisioner):
    """
    - `compose` is a Testing Farm compose to prepare.

    - `arch` is an architecture associated with the compose.

    - `max_remotes` is how many Testing Farm Requests to keep running at any
      one time (both queued / pending, and already reserved).

    - `max_retries` is a maximum number of provisioning (Testing Farm) errors
      that will be retried (systems reprovisioned) before giving up.
    """

    # maximum number of TF requests the user can .provision(),
    # as a safety measure against somebody passing huge max_remotes
    absolute_max_remotes = 50
    # number of parallel threads running HTTP DELETE calls to cancel
    # TF requests on .stop() or Context Manager exit
    stop_release_workers = 10

    def __init__(self, compose, arch="x86_64", max_remotes=3, *, max_retries=10, **reserve_kwargs):
        self._lock = threading.RLock()
        self.logger = _get_logger()

        self.compose = compose
        self.arch = arch
        self.max_remotes = min(max_remotes, self.absolute_max_remotes)
        self.reserve_kwargs = reserve_kwargs
        self._retries = max_retries

        self._queue = util.ThreadJoinQueue(daemon=True)
        self._tf_api = api.TestingFarmAPI()
        self._to_reserve = 0

        # TF Reserve instances (not Remotes) actively being provisioned,
        # in case we need to call their .release() on abort
        self._reserving = []

        # active TestingFarmRemote instances, ready to be handed over to the user,
        # or already in use by the user
        self._remotes = []

    def _wait_for_reservation(self, tf_reserve, initial_delay):
        # assuming this function will be called many times, attempt to
        # distribute load on TF servers
        # (we can sleep here as this code is running in a separate thread)
        if initial_delay:
            self.logger.info(f"delaying for {initial_delay}s to distribute load")
            time.sleep(initial_delay)

        try:
            # 'machine' is api.Reserve.Reserved namedtuple
            machine = tf_reserve.reserve()

            # connect our Remote to the machine via its class Connection API
            ssh_options = {
                "Hostname": machine.host,
                "User": machine.user,
                "Port": machine.port,
                "IdentityFile": machine.ssh_key.absolute(),
                "ConnectionAttempts": 1000,
                "Compression": "yes",
            }

            def release_hook(remote):
                self.logger.debug(f"releasing {remote}")

                # remove from the list of remotes inside this Provisioner
                with self._lock:
                    try:
                        self._remotes.remove(remote)
                    except ValueError:
                        pass
                # call TF API, cancel the request, etc.
                tf_reserve.release()

            remote = TestingFarmRemote(
                tf_reserve.request.id,
                release_hook=release_hook,
                options=ssh_options,
            )

            remote.connect()

            # since the system is fully ready, stop tracking its reservation
            # and return the finished Remote instance
            with self._lock:
                self._remotes.append(remote)
                self._reserving.remove(tf_reserve)

        except BaseException:
            with self._lock:
                self._reserving.remove(tf_reserve)
            tf_reserve.release()
            raise

        return remote

    def _schedule_new_reservations(self):
        if self._to_reserve <= 0:
            return

        # calculate how much can we still reserve to fit within
        # self.max_remotes, and clamp will_reserve to it
        with self._lock:
            capacity = self.max_remotes - len(self._remotes) - len(self._reserving)
            will_reserve = min(self._to_reserve, capacity)
            if will_reserve <= 0:
                return
            self._to_reserve -= will_reserve

            self.logger.info(f"reserving {will_reserve} new remotes")
            for i in range(will_reserve):
                tf_reserve = api.Reserve(
                    compose=self.compose,
                    arch=self.arch,
                    api=self._tf_api,
                    logger=self.logger,
                    **self.reserve_kwargs,
                )
                # add it to self._reserving even before we schedule a provision,
                # to avoid races on sudden abort
                self._reserving.append(tf_reserve)
                # start a background wait
                initial_delay = (api.Request.api_query_limit / will_reserve) * i
                self._queue.start_thread(
                    target=self._wait_for_reservation,
                    target_args=(tf_reserve, initial_delay),
                )

    def start(self):
        self.logger.debug(f"starting: {self}")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        release_funcs = []

        with self._lock:
            release_funcs += (f.release for f in self._reserving)
            self._reserving = []
            release_funcs += (r.release for r in self._remotes)
            self._remotes = []  # just in case of a later .start()

        # parallelize at most stop_release_workers TF API release (DELETE) calls
        if release_funcs:
            workers = min(len(release_funcs), self.stop_release_workers)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                for func in release_funcs:
                    ex.submit(func)

    def provision(self, count=1):
        with self._lock:
            self._to_reserve += count
        self._schedule_new_reservations()

    def get_remote(self, block=True):
        while True:
            self._schedule_new_reservations()
            # otherwise wait on a queue of Remotes being provisioned
            try:
                return self._queue.get(block=block)  # thread-safe
            except util.ThreadJoinQueue.Empty:
                # always non-blocking
                return None
            except BaseException as e:
                exc_str = f"{type(e).__name__}({e})"
                with self._lock:
                    if self._retries > 0:
                        self.logger.warning(
                            f"caught while reserving a TF system: {exc_str}, "
                            f"retrying ({self._retries} left)",
                        )
                        self._retries -= 1
                        self._to_reserve += 1
                        if block:
                            continue
                        else:
                            return None
                    else:
                        self.logger.warning(
                            f"caught while reserving a TF system: {exc_str}, "
                            "exhausted all retries, giving up",
                        )
                        raise

    def clear(self):
        with self._lock:
            self._to_reserve = 0
        # keep all self._reserving running
        # - this optimizes further .get_remote() calls as we don't have to
        #   re-enter the queue for systems with new TF Requests
        # - but also, cancelling would produce exceptions in self._queue;
        #   TODO: add some spare=N for how many self._reserving to keep running
        #         and cancel the rest cleanly, once we get rid of daemon=True
        #         and switch TF API to threading.Event waits

    def __str__(self):
        class_name = self.__class__.__name__
        reserving = len(self._reserving)
        remotes = len(self._remotes)
        return (
            f"{class_name}({self.compose} @ {self.arch}, {reserving} reserving, "
            f"{remotes} remotes)"
        )
