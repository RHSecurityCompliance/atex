import errno
import json
import logging
import math
import socket
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from ... import connection
from .. import Provisioner, Remote

logger = logging.getLogger("atex.provisioner.shvirt")


def _wait_for_sshd(host, port, event):
    """
    Wait for real OpenSSH server to start responding on host/port,
    non-blockingly.

    Return True if successful, False if `event` was set and the waiting
    was thus interrupted.
    """
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setblocking(False)

            # try connecting
            try:
                s.connect((host, port))
            except BlockingIOError:
                pass

            connected = False
            while not connected:
                if event.wait(timeout=0.1):
                    return False
                # wait for the connection to either fail (SO_ERROR)
                if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) != 0:
                    break
                # or succeed (getpeername)
                try:
                    s.getpeername()
                except OSError as e:
                    if e.errno == errno.ENOTCONN:
                        continue
                    break
                else:
                    connected = True

            # re-try connecting with a new socket
            if not connected:
                logger.debug("connection attempt to sshd failed, re-trying")
                continue

            # connected, try receiving
            sshd_signature = False
            end = time.monotonic() + 5  # 5sec to reply over connected socket
            while not sshd_signature and time.monotonic() < end:
                if event.wait(timeout=0.1):
                    return False
                try:
                    data = s.recv(4)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                else:
                    if data == b"SSH-":
                        sshd_signature = True
                    break

            if not sshd_signature:
                logger.debug("connected to sshd, but no signature, re-trying")
                continue

            return True


class SharedVirtRemote(Remote, connection.ssh.ManagedSSHConnection):
    def __init__(self, ssh_options, host, domain, source_image, *, release_hook):
        """
        - `ssh_options` are a dict, passed to ManagedSSHConnection `__init__()`.

        - `host` is a str of libvirt host name (used for `repr()`).

        - `domain` is a str of libvirt domain name.

        - `source_image` is a str of libvirt volume name that was cloned
          for the domain to boot from (used for `repr()`).

        - `release_hook` is a callable called on `.release()` in addition
          to disconnecting the connection.
        """
        # NOTE: self.lock inherited from ManagedSSHConnection
        super().__init__(options=ssh_options)
        self.host = host
        self.domain = domain
        self.source_image = source_image
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

    def connect(self, block=True):
        with self.lock:
            if self.release_called:
                raise ConnectionError("remote released, cannot connect")
        super().connect(block=block)

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        port = self.options["Port"]
        return f"{class_name}({self.host}, {self.domain} ({port}), {self.source_image})"


class SharedVirtProvisioner(Provisioner):
    helper_command = ("atex-virt-helper",)

    # DESIGN NOTES:
    #
    # There's one background reserving thread started by .provision() if
    # 'to_reserve' is > 0. The thread exits on its own once it reaches 0.
    # This thread reserves (locks) domains, clones disk images, starts up
    # the domain OS, waits for sshd, connects a new SharedVirtRemote and
    # appends it to self.remotes and self.reserving_remotes.
    # It also increases a Semaphore by 1 to signal that "something happened".
    #
    # If the thread fails with an exception, the Semaphore is also increased,
    # allowing 'get_remote()' to use IPC blocking mechanisms to wait for either
    #   1) new remote that was reserved
    #   2) reserving thread exception
    # as opposed to ie. SimpleQueue which would work only for (1).
    #
    # Using a Semaphore as "something happened" to wake 'get_remote()' up
    # also lets it handle an exception *before* consuming any previously-
    # created Remotes.
    #
    # The reserving thread also runs as daemon=False and waits for an Event
    # (reserving_exit) to be interrupted, which happens during 'stop()'.
    # It uses as few blocking operations as possible to exit quickly.
    #
    # One missing feature (would be hard-ish to implement within the current
    # mess of possible states) is helper process monitoring - there should be
    # an independent thread stuck on 'helper_proc.wait()' so it can disconnect
    # any Remotes if the helper suddenly exits (because that auto-releases
    # any reservations).

    def __init__(
        self, host, image, *, pool="default",
        domain_filter=None, domain_user="root", domain_sshkey, domain_host=None,
        reserve_delay=3, reserve_name=None,
    ):
        """

        - `host` is a Connection class instance, connected to a libvirt host.

        - `image` is a string with a libvirt storage volume name inside the
          given storage `pool` that should be used as the source for cloning.

        - `pool` is a libvirt storage pool used by all relevant domains on the
          libvirt host **as well as** the would-be-cloned images.

        - `domain_filter` is a regex string matching libvirt domain names to
          attempt reservation on. Useful for including only ie. `auto-.*`
          domains while leaving other domains on the same libvirt host
          untouched.

        - `domain_user` and `domain_sshkey` (strings) specify how to connect to
          an OS booted from the pre-instaled `image`, as these credentials are
          known only to the logic that created the `image` in the first place.

          The `domain_sshkey` is a file path to the private key.

        - `domain_host` (string) is a hostname or an IP address through which
          to connect to the domains' ssh ports, as stored in the libvirt domain
          XML (`<backend type='passt'>`, `<portForward ...>`).

          Normally, this is extracted from `host` if it is *SSHConnection
          (the Hostname `options` attribute) and doesn't need to be provided
          here, but is necessary for non-SSH `host`.

          For example, for a LocalConnection, it would be `127.0.0.1`.

        - `reserve_delay` is an int of how many seconds to wait between trying
          to reserve a libvirt domain, reducing reservation bursting.

        - `reserve_name` is a custom user name, to be set for any reservations
          this Provisioner makes, seen in the list of reservations when queried
          by a user. Must be at most 15 characters long (per PR_SET_NAME).
        """
        self.lock = threading.RLock()
        self.host = host
        self.image = image
        self.pool = pool
        self.domain_filter = domain_filter
        self.domain_user = domain_user
        self.domain_sshkey = domain_sshkey
        self.reserve_delay = reserve_delay
        self.reserve_name = reserve_name

        if domain_host is None:
            if isinstance(
                host,
                (connection.ssh.ManagedSSHConnection, connection.ssh.StatelessSSHConnection),
            ):
                self.domain_host = host.options["Hostname"]
            else:
                raise ValueError("'domain_host' not given and 'host' is not SSH")
        else:
            self.domain_host = domain_host

        self.started = False
        self.helper = None
        self.helper_lock = threading.RLock()

        self.reserving_thread = None
        self.reserving_exit = threading.Event()
        self.reserving_remotes = set()
        self.reserving_exc = None
        self.reserving_events = threading.Semaphore(0)

        self.to_reserve = 0
        self.remotes = []  # TODO: set()?

    def _helper_query(self, data):
        with self.helper_lock:
            json.dump(data, self.helper.stdin)
            self.helper.stdin.write("\n")
            self.helper.stdin.flush()
            response = self.helper.stdout.readline()
            if not response:
                raise ConnectionError("empty response from helper")
            return json.loads(response)

    def _reserve_wrapper(self):
        try:
            self._reserve()
        except Exception as e:
            self.reserving_exc = e
            logger.debug(f"reserve thread got {type(e).__name__}({e})")
            self.reserving_remotes.clear()
            self.stop()
            # wake up any waiting .get_remote() calls
            self.reserving_events.release(math.inf)
        else:
            logger.debug("reserve thread exited cleanly")

    def _reserve(self):
        while True:
            if self.to_reserve <= 0:
                return

            if (exit_code := self.helper.poll()) is not None:
                raise RuntimeError(f"helper not running, exited with {exit_code}")

            reserve_cmd = {"cmd": "reserve"}
            if self.domain_filter:
                reserve_cmd["filter"] = self.domain_filter
            # this blocks, but any provisioner .stop() SIGTERMs the helper
            # which breaks this blocking with EPIPE
            response = self._helper_query(reserve_cmd)
            if not response["success"]:
                reply = response["reply"]
                if reply == "no domain could be reserved":
                    # wait reserve_delay before trying again
                    if self.reserving_exit.wait(timeout=self.reserve_delay):
                        return
                    continue
                else:
                    raise RuntimeError(f"failed reserve: {reply}")

            domain = response["domain"]
            logger.debug(f"reserved domain {domain}")

            # we are relying on .stop() terminating the helper connection
            # to release the domain if any of the exceptions below are raised,
            # rather than risking cmd:release over what might be corrupted
            # helper stdio channel

            # destroy and clone the requested image to it
            response = self._helper_query({"cmd": "virsh", "args": ["destroy", domain]})
            if response["success"]:
                logger.debug(f"destroyed domain {domain}")

            response = self._helper_query({
                "cmd": "vol-copy",
                "pool": self.pool,
                "from": self.image,
                "to_domain": domain,
            })
            if not response["success"]:
                reply = response["reply"]
                raise RuntimeError(f"failed vol-copy: {reply}")

            logger.debug(f"vol-copied {self.image} to {domain}")

            # find the forwarded port via virsh over atex-virt-helper
            response = self._helper_query({
                "cmd": "virsh",
                "args": [
                    "dumpxml", domain, "--xpath",
                    "//devices/interface[backend/@type='passt']/portForward/range",
                ],
            })
            output = response["reply"]
            if not response["success"]:
                raise RuntimeError(f"'virsh dumpxml {domain}' failed: {output}")

            first_range, _, _ = output.partition("\n")  # first <range> only
            logger.debug(f"found portForward range {first_range}")
            port_range = ET.fromstring(first_range)
            port = port_range.get("start")  # string!
            assert port

            # start up the domain
            response = self._helper_query({"cmd": "virsh", "args": ["start", domain]})
            output = response["reply"]
            if not response["success"]:
                raise RuntimeError(f"'virsh start {domain}' failed: {output}")
            logger.debug(f"started up {domain}")

            # create a remote and connect it
            ssh_options = {
                "Hostname": self.domain_host,
                "User": self.domain_user,
                "Port": port,
                "IdentityFile": str(Path(self.domain_sshkey).absolute()),
                "ConnectionAttempts": "1000",
                "Compression": "yes",
            }

            def release_hook(remote):
                # remove from the list of remotes inside this Provisioner
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass
                # issue a cmd:release to the remote helper
                response = self._helper_query({"cmd": "release", "domain": remote.domain})
                assert response["success"]

            remote = SharedVirtRemote(
                ssh_options=ssh_options,
                host=self.domain_host,
                domain=domain,
                source_image=self.image,
                release_hook=release_hook,
            )

            logger.debug(f"waiting for sshd on {remote}")
            if not _wait_for_sshd(self.domain_host, int(port), self.reserving_exit):
                return

            logger.debug(f"connecting to {remote}")
            retries = 0
            while True:
                if self.reserving_exit.wait(timeout=0.1):
                    remote.disconnect()
                    return
                try:
                    remote.connect(block=False)
                except BlockingIOError:
                    pass
                except ConnectionError:
                    # using SLIRP or passt, the user networking binary tends to
                    # accept a TCP connection, but then stops handling any data
                    # if the domain-side port (sshd) isn't listening yet
                    # - this confuses the ssh client and causes a kex disconnect
                    #   so retry a few times (wait for domain to start up)
                    retries += 1
                    if retries > 3000:  # ~5 minutes of sleeps + connects
                        remote.disconnect()
                        raise
                except Exception:
                    remote.disconnect()
                    raise
                else:
                    break

            logger.debug(f"appending {remote}")
            self.remotes.append(remote)
            self.reserving_remotes.add(remote)
            self.to_reserve -= 1
            self.reserving_events.release(1)

            # delay for reserve_delay before reserving more
            if self.reserving_exit.wait(timeout=self.reserve_delay):
                return

    def start(self):
        with self.lock:
            # launch the helper on the remote host
            if self.helper:
                raise RuntimeError("helper already launched")
            self.helper = self.host.cmd(
                self.helper_command,
                func=subprocess.Popen,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )

            # ping the helper to make sure we're talking with a compatible one
            response = self._helper_query({"cmd": "ping"})
            if (
                response.get("cmd") != "ping"
                or response.get("reply") != "atex-virt-helper v1 pong"
            ):
                raise RuntimeError(f"bad pong from remote helper (wrong version?): {response}")

            if self.reserve_name:
                response = self._helper_query({"cmd": "setname", "name": self.reserve_name})
                if not response["success"]:
                    raise RuntimeError(f"failed to 'setname': {response}")

            # re-zero the event counter, in case we're re-starting
            # and it was set to math.inf previously
            self.reserving_events = threading.Semaphore(0)
            self.reserving_exc = None

            self.started = True

    def stop(self):
        with self.lock:
            self.started = False

            # stop the reserving thread
            if (
                self.reserving_thread is not None and
                self.reserving_thread.is_alive() and
                self.reserving_exc is None
            ):
                self.to_reserve = -math.inf
                self.reserving_exit.set()
                self.reserving_thread.join()

            self.to_reserve = 0
            self.reserving_exit.clear()
            self.reserving_thread = None

            # disconnect all existing Remotes to prevent our user messing with
            # their port-forwarded connections after we release all by
            # terminating the helper below
            for remote in self.remotes:
                with remote.lock:
                    remote.release_called = True  # we do it below, globally
                    remote.disconnect()
            self.remotes = []

            if self.helper is not None:
                self.helper.terminate()
                self.helper = None

    def _sanity_check(self):
        if exc := self.reserving_exc:
            raise exc from None
        if not self.started:
            raise RuntimeError("the provisioner is stopped")

    def provision(self, count=1):
        self._sanity_check()

        with self.lock:
            self.to_reserve += count
            if self.to_reserve <= 0:
                return
            # if it isn't running, start up a reserving thread
            if self.reserving_thread is None or not self.reserving_thread.is_alive():
                self.reserving_thread = threading.Thread(target=self._reserve_wrapper)
                self.reserving_thread.start()

    def get_remote(self, block=True):
        self._sanity_check()

        if self.reserving_events.acquire(blocking=block):
            try:
                remote = self.reserving_remotes.pop()
            except KeyError:
                # the event was an exception by _reserve_wrapper(), re-raise it
                raise self.reserving_exc from None
            else:
                return remote

        # non-blocking
        return None

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        return (
            f"{class_name}({self.domain_host}, {self.domain_filter}, "
            f"{len(self.remotes)} remotes, {hex(id(self))})"
        )
