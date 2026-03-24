import concurrent.futures
import tempfile
import threading
import time

from ... import connection, util
from .. import Provisioner, Remote
from . import api

get_logger = util.get_loggers("atex.provisioner.testingfarm")


class TestingFarmRemote(Remote, connection.ssh.ManagedSSHConnection):
    """
    Built on the official Remote API, pulling in the Connection API
    as implemented by ManagedSSHConnection.
    """

    def __init__(self, request_id, ssh_options, *, release_hook):
        """
        - `request_id` is a string with Testing Farm request UUID
          (for printouts).

        - `ssh_options` are a dict, passed to ManagedSSHConnection `__init__()`.

        - `release_hook` is a callable called on `.release()` in addition
          to disconnecting the connection.
        """
        # NOTE: self.lock inherited from ManagedSSHConnection
        super().__init__(options=ssh_options)
        self.request_id = request_id
        self.release_hook = release_hook
        self.release_called = False

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
        ssh_user = self.options.get("User", "unknown")
        ssh_host = self.options.get("Hostname", "unknown")
        ssh_port = self.options.get("Port", "unknown")
        ssh_key = self.options.get("IdentityFile", "unknown")
        return f"{class_name}({ssh_user}@{ssh_host}:{ssh_port}@{ssh_key}, {self.request_id})"


class TestingFarmProvisioner(Provisioner):
    # maximum number of TF requests the user can .provision(),
    # as a safety measure against somebody passing huge max_remotes
    absolute_max_remotes = 50
    # number of parallel threads running HTTP DELETE calls to cancel
    # TF requests on .stop() or Context Manager exit
    stop_release_workers = 10

    def __init__(self, compose, arch="x86_64", max_remotes=3, *, max_retries=10, **reserve_kwargs):
        """
        - `compose` is a Testing Farm compose to prepare.

        - `arch`' is an architecture associated with the compose.

        - `max_remotes` is how many Testing Farm Requests to keep running at any
          one time (both queued / pending, and already reserved).

        - `max_retries` is a maximum number of provisioning (Testing Farm) errors
          that will be reprovisioned before giving up.
        """
        self.lock = threading.RLock()
        self.logger = get_logger()

        self.compose = compose
        self.arch = arch
        self.max_remotes = min(max_remotes, self.absolute_max_remotes)
        self.reserve_kwargs = reserve_kwargs
        self.retries = max_retries

        self._tmpdir = None
        self.ssh_key = self.ssh_pubkey = None
        self.queue = util.ThreadReturnQueue(daemon=True)
        self.tf_api = api.TestingFarmAPI()
        self.to_reserve = 0

        # TF Reserve instances (not Remotes) actively being provisioned,
        # in case we need to call their .release() on abort
        self.reserving = []

        # active TestingFarmRemote instances, ready to be handed over to the user,
        # or already in use by the user
        self.remotes = []

    def _wait_for_reservation(self, tf_reserve, initial_delay):
        # assuming this function will be called many times, attempt to
        # distribute load on TF servers
        # (we can sleep here as this code is running in a separate thread)
        if initial_delay:
            self.logger.info(f"delaying for {initial_delay}s to distribute load")
            time.sleep(initial_delay)

        try:
            # 'machine' is api.Reserve.ReservedMachine namedtuple
            machine = tf_reserve.reserve()
        except Exception:
            tf_reserve.release()
            raise

        # connect our Remote to the machine via its class Connection API
        ssh_options = {
            "Hostname": machine.host,
            "User": machine.user,
            "Port": machine.port,
            "IdentityFile": machine.ssh_key.absolute(),
            "ConnectionAttempts": "1000",
            "Compression": "yes",
        }

        def release_hook(remote):
            self.logger.debug(f"releasing {remote}")

            # remove from the list of remotes inside this Provisioner
            with self.lock:
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass
            # call TF API, cancel the request, etc.
            tf_reserve.release()

        remote = TestingFarmRemote(
            tf_reserve.request.id,
            ssh_options,
            release_hook=release_hook,
        )
        remote.connect()

        # since the system is fully ready, stop tracking its reservation
        # and return the finished Remote instance
        with self.lock:
            self.remotes.append(remote)
            self.reserving.remove(tf_reserve)

        return remote

    def _schedule_new_reservations(self):
        if self.to_reserve <= 0:
            return

        # calculate how much can we still reserve to fit within
        # self.max_remotes, and clamp will_reserve to it
        with self.lock:
            capacity = self.max_remotes - len(self.remotes) - len(self.reserving)
            will_reserve = min(self.to_reserve, capacity)
            if will_reserve <= 0:
                return
            self.to_reserve -= will_reserve

        self.logger.info(f"reserving {will_reserve} new remotes")
        for i in range(will_reserve):
            tf_reserve = api.Reserve(
                compose=self.compose,
                arch=self.arch,
                ssh_key=self.ssh_key,
                api=self.tf_api,
                **self.reserve_kwargs,
            )
            # add it to self.reserving even before we schedule a provision,
            # to avoid races on suddent abort
            self.reserving.append(tf_reserve)
            # start a background wait
            initial_delay = (api.Request.api_query_limit / will_reserve) * i
            self.queue.start_thread(
                target=self._wait_for_reservation,
                target_args=(tf_reserve, initial_delay),
            )

    def start(self):
        self.logger.debug(f"starting: {self}")

        with self.lock:
            self._tmpdir = tempfile.TemporaryDirectory()
            self.ssh_key, self.ssh_pubkey = util.ssh_keygen(self._tmpdir.name)

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        release_funcs = []

        with self.lock:
            release_funcs += (f.release for f in self.reserving)
            self.reserving = []
            release_funcs += (r.release for r in self.remotes)
            self.remotes = []  # just in case of a later .start()

        # parallelize at most stop_release_workers TF API release (DELETE) calls
        if release_funcs:
            workers = min(len(release_funcs), self.stop_release_workers)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                for func in release_funcs:
                    ex.submit(func)

        with self.lock:
            # explicitly remove the tmpdir rather than relying on destructor
            self._tmpdir.cleanup()
            self._tmpdir = None

    def provision(self, count=1):
        with self.lock:
            self.to_reserve += count
        self._schedule_new_reservations()

    def get_remote(self, block=True):
        while True:
            self._schedule_new_reservations()
            # otherwise wait on a queue of Remotes being provisioned
            try:
                return self.queue.get(block=block)  # thread-safe
            except util.ThreadReturnQueue.Empty:
                # always non-blocking
                return None
            except (api.TestingFarmError, connection.ssh.SSHError) as e:
                exc_str = f"{type(e).__name__}({e})"
                with self.lock:
                    if self.retries > 0:
                        self.logger.warning(
                            f"caught while reserving a TF system: {exc_str}, "
                            f"retrying ({self.retries} left)",
                        )
                        self.retries -= 1
                        self.to_reserve += 1
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
        with self.lock:
            self.to_reserve = 0
        # keep all self.reserving running
        # - this optimizes further .get_remote() calls as we don't have to
        #   re-enter the queue for systems with new TF Requests
        # - but also, cancelling would produce exceptions in self.queue;
        #   TODO: add some spare=N for how many self.reserving to keep running
        #         and cancel the rest cleanly, once we get rid of daemon=True
        #         and switch TF API to threading.Event waits

    def __str__(self):
        class_name = self.__class__.__name__
        reserving = len(self.reserving)
        remotes = len(self.remotes)
        return (
            f"{class_name}({self.compose} @ {self.arch}, {reserving} reserving, "
            f"{remotes} remotes)"
        )
