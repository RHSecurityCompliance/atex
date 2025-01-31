import time
import tempfile
import threading

from ... import connection, util
from .. import Provisioner, Remote

from . import api


class TestingFarmRemote(Remote, connection.ssh.ManagedSSHConn):
    """
    Built on the official Remote API, pulling in the Connection API
    as implemented by ManagedSSHConn.
    """

    def __init__(self, request_id, ssh_options, *, release_hook):
        """
        'request_id' is a string with Testing Farm request UUID (for printouts).

        'ssh_options' are a dict, passed to ManagedSSHConn __init__().

        'release_hook' is a callable called on .release() in addition
        to disconnecting the connection.
        """
        # NOTE: self.lock inherited from ManagedSSHConn
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
        self.release_hook(self)
        self.disconnect()

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        ssh_user = self.options.get("User", "unknown")
        ssh_host = self.options.get("Hostname", "unknown")
        ssh_port = self.options.get("Port", "unknown")
        ssh_key = self.options.get("IdentityFile", "unknown")
        return f"{class_name}({ssh_user}@{ssh_host}:{ssh_port}@{ssh_key}, {self.request_id})"


class TestingFarmProvisioner(Provisioner):
    # TODO: have max_systems as (min,default,max) tuple; have an algorithm that
    #       starts at default and scales up/down as needed

    def __init__(self, compose, arch="x86_64", *, max_systems=1, max_retries=10, **reserve_kwargs):
        """
        'compose' is a Testing Farm compose to prepare.

        'arch' is an architecture associated with the compose.

        'max_systems' is an int of how many systems to reserve (and keep
        reserved) in an internal pool.

        'max_retries' is a maximum number of provisioning (Testing Farm) errors
        that will be reprovisioned before giving up.
        """
        self.lock = threading.RLock()
        self.compose = compose
        self.arch = arch
        self.max_systems = max_systems
        self.reserve_kwargs = reserve_kwargs
        self.retries = max_retries

        self._tmpdir = None
        self.ssh_key = self.ssh_pubkey = None
        self.queue = util.ThreadQueue(daemon=True)
        self.tf_api = api.TestingFarmAPI()

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
            util.debug(f"delaying for {initial_delay}s to distribute load")
            time.sleep(initial_delay)

        # 'machine' is api.Reserve.ReservedMachine namedtuple
        machine = tf_reserve.reserve()

        # connect our Remote to the machine via its class Connection API
        ssh_options = {
            "Hostname": machine.host,
            "User": machine.user,
            "Port": machine.port,
            "IdentityFile": machine.ssh_key,
            "ConnectionAttempts": "1000",
            "Compression": "yes",
        }

        def release_hook(remote):
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

    def _schedule_one_reservation(self, initial_delay=None):
        # instantiate a class Reserve from the Testing Farm api module
        # (which typically provides context manager, but we use its .reserve()
        #  and .release() functions directly)
        tf_reserve = api.Reserve(
            compose=self.compose,
            arch=self.arch,
            ssh_key=self.ssh_key,
            api=self.tf_api,
            **self.reserve_kwargs,
        )

        # add it to self.reserving even before we schedule a provision,
        # to avoid races on suddent abort
        with self.lock:
            self.reserving.append(tf_reserve)

        # start a background wait
        self.queue.start_thread(
            target=self._wait_for_reservation,
            target_args=(tf_reserve, initial_delay),
        )

    def start(self):
        with self.lock:
            self._tmpdir = tempfile.TemporaryDirectory()
            self.ssh_key, self.ssh_pubkey = util.ssh_keygen(self._tmpdir.name)
            # start up all initial reservations
            for i in range(self.max_systems):
                delay = (api.API_QUERY_DELAY / self.max_systems) * i
                #self.queue.start_thread(target=self._schedule_one_reservation, args=(delay,))
                self._schedule_one_reservation(delay)

    def stop(self):
        with self.lock:
            # abort reservations in progress
            while self.reserving:
                # testingfarm api.Reserve instances
                self.reserving.pop().release()
            # cancel/release all Remotes ever created by us
            while self.remotes:
                # TestingFarmRemote instances
                self.remotes.pop().release()
            # explicitly remove the tmpdir rather than relying on destructor
            self._tmpdir.cleanup()
            self._tmpdir = None

    def stop_defer(self):
        callables = []
        with self.lock:
            callables += (f.release for f in self.reserving)
            self.reserving = []
            callables += (r.release for r in self.remotes)
            self.remotes = []  # just in case
            callables.append(self._tmpdir.cleanup)
            self._tmpdir = None
        return callables

    def get_remote(self, block=True):
        # fill .release()d remotes back up with reservations
        with self.lock:
            deficit = self.max_systems - len(self.remotes) - len(self.reserving)
            for i in range(deficit):
                delay = (api.API_QUERY_DELAY / deficit) * i
                self._schedule_one_reservation(delay)

        while True:
            # otherwise wait on a queue of Remotes being provisioned
            try:
                return self.queue.get(block=block)  # thread-safe
            except util.ThreadQueue.Empty:
                # always non-blocking
                return None
            except (api.TestingFarmError, connection.ssh.SSHError) as e:
                with self.lock:
                    if self.retries > 0:
                        util.warning(
                            f"caught while reserving a TF system: {repr(e)}, "
                            f"retrying ({self.retries} left)",
                        )
                        self.retries -= 1
                        self._schedule_one_reservation()
                        if block:
                            continue
                        else:
                            return None
                    else:
                        util.warning(
                            f"caught while reserving a TF system: {repr(e)}, "
                            "exhausted all retries, giving up",
                        )
                        raise

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        reserving = len(self.reserving)
        remotes = len(self.remotes)
        return (
            f"{class_name}({self.compose} @ {self.arch}, {reserving} reserving, "
            f"{remotes} remotes, {hex(id(self))})"
        )
