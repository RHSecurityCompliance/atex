import collections
import concurrent.futures
import copy
import threading
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from ... import connection, util
from .. import Provisioner, ProvisionerError, Remote
from .utils import PortAllocator, transient_domain_xml, virsh

_get_logger = util.get_loggers("atex.provisioner.tempvirt")


class TempVirtRemote(Remote, connection.ssh.ManagedSSHConnection):
    """
    - `domain` is a str of a transient libvirt domain name
      (used for `str(self)`).

    - `origin_domain` is a str of a libvirt domain name that was used
      as the source/origin for the transient one (used for `str(self)`).

    - `release_hook` is a callable called on `.release()` in addition
      to disconnecting the connection.

    - `kwargs` are passed to the underlying ManagedSSHConnection.
    """

    def __init__(self, domain, origin_domain, *, release_hook, **kwargs):
        super().__init__(**kwargs)
        self._lock = threading.RLock()
        self.domain = domain
        self.origin_domain = origin_domain
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

    def connect(self, **kwargs):
        with self._lock:
            if self._release_called:
                raise ConnectionError("remote released, cannot connect")
        super().connect(**kwargs)

    def __str__(self):
        class_name = self.__class__.__name__
        # these are ManagedSSHConnection public attrs
        host = self.options["Hostname"]
        port = self.options["Port"]
        user = self.options["User"]
        return f"{class_name}({self.domain}, {self.origin_domain}, {user}@{host}:{port})"


class TempVirtProvisioner(Provisioner):
    """
    - `origin_domain` is a string specifying a source domain name to base
      the temporary (transient) domains on.

    - `domain_user` and `domain_sshkey` (strings) specify how to connect to
      an OS of the `origin_domain`, as these credentials are known only to
      the logic that created the domain in the first place.

      The `domain_sshkey` is a file path to the private key.

    - `domain_host` (string) is a hostname or an IP address through which
      to connect to the domains' ssh ports, forwarded using a 'passt' network
      interface added to the transient domains.

      This should be tied to the `uri` argument and may be left as `None`
      for a local libvirt connection. If `uri` specifies a remote system,
      then `domain_host` needs to specify hostname/address of how to reach
      that system via TCP/IP.

      For example, for an `uri` of `qemu+ssh://root@example.com/system`,
      this would be `example.com`.

    - `domain_sshport_from` is a starting TCP port on `domain_host` from which
      (counting upwards) to allocate SSH-forwarded ports for transient domains,
      using the 'passt' `portForward` directive.

      If `domain_host` is specified (non-local), these ports need to be
      reachable from outside that host.

    - `uri` is a libvirt connection URI, see https://libvirt.org/uri.html.

      If not specified, 'virsh' defaults are used.

    - `max_remotes` is how many transient domains to keep running at any
      one time.

      Adjust this according to the available (free) memory on your system,
      to avoid creating too many running domains.
    """

    # number of parallel threads running virsh destroy commands
    # to remove transient domains on .stop() or Context Manager exit
    stop_release_workers = 6

    def __init__(
        self, origin_domain, *,
        domain_user="root", domain_sshkey, domain_host=None, domain_sshport_from=5100,
        uri=None, max_remotes=3,
    ):
        if uri and uri not in ("qemu:///system", "qemu:///session") and not domain_host:
            raise ValueError("'domain_host' must be given for non-local uri")

        self._lock = threading.Condition()
        self.logger = _get_logger()

        self.origin_domain = origin_domain
        self.domain_user = domain_user
        self.domain_sshkey = domain_sshkey
        self.domain_host = domain_host
        self.uri = uri
        self.max_remotes = max_remotes

        self._remotes = set()
        self._to_reserve = 0
        self._reserving = 0
        self._queue = collections.deque()
        self._stopped = threading.Event()
        self._stopped.set()
        self._domain_template = None
        self._domain_portalloc = PortAllocator(start=domain_sshport_from)

    def start(self):
        self.logger.debug(f"starting: {self}")
        self._domain_template = transient_domain_xml(self.origin_domain, connect=self.uri)
        self._stopped.clear()

    def stop(self):
        self.logger.debug(f"stopping: {self}")
        with self._lock:
            self._stopped.set()
            self._to_reserve = 0
            # unblock any get_remote() and let them raise on self._stopped
            self._lock.notify_all()
            # wait for any _create_domain threads to finish and
            # self-release based on self._stopped being set
            self._lock.wait_for(lambda: self._reserving == 0)
            to_release = self._remotes
            self._remotes = set()
            # this also discards any _create_domain() exceptions, that's fine
            self._queue.clear()

        if to_release:
            release_funcs = [remote.release for remote in to_release]
            workers = min(len(release_funcs), self.stop_release_workers)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                for func in release_funcs:
                    ex.submit(func)

    def provision(self, count=1):
        if self._stopped.is_set():
            raise ProvisionerError("the provisioner is stopped")

        self.logger.debug(f"provisioning {count}")
        with self._lock:
            self._to_reserve += count
            self._lock.notify(count)
        self._spin_up_domains()

    def _spin_up_domains(self):
        with self._lock:
            capacity = self.max_remotes - len(self._remotes) - self._reserving
            will_create = min(self._to_reserve, capacity)
            if will_create <= 0:
                return
            self._to_reserve -= will_create
            self._reserving += will_create

        for _ in range(will_create):
            t = threading.Thread(target=self._wrap_create_domain)
            t.start()

    def _wrap_create_domain(self):
        result = util.ThreadResult()
        try:
            result.value = self._create_domain()
        except BaseException as e:
            result.exception = e

        with self._lock:
            self._reserving -= 1
            if not result.exception:
                self._remotes.add(result.value)
            self._queue.append(result)
            self._lock.notify()

    def _create_domain(self):
        if self._stopped.is_set():
            raise RuntimeError

        # if libvirt is remote, allow forwarding remote connections (us),
        # else keep everything local
        ssh_addr = "0.0.0.0" if self.domain_host else "127.0.0.1"
        ssh_port = self._domain_portalloc.acquire()

        ssh_options = {
            "Hostname": self.domain_host or "127.0.0.1",
            "User": self.domain_user,
            "Port": ssh_port,
            "IdentityFile": Path(self.domain_sshkey).absolute(),
            "ConnectionAttempts": 1000,
            "Compression": "yes" if self.domain_host else "no",  # localhost = no compression
        }

        # add <portForward>
        xml_root = copy.deepcopy(self._domain_template)
        xml_iface = xml_root.find("devices/interface")
        xml_pf = ET.SubElement(xml_iface, "portForward", proto="tcp", address=ssh_addr)
        ET.SubElement(xml_pf, "range", start=str(ssh_port), to="22")

        # rename to a random name
        new_uuid = uuid.uuid4()
        xml_root.find("name").text = f"atex-{new_uuid}"
        xml_root.find("uuid").text = str(new_uuid)

        domain_xml_str = ET.tostring(xml_root, encoding="unicode")
        code, output = virsh(
            "create", "/dev/stdin",
            input=domain_xml_str,
            connect=self.uri,
        )
        if code != 0:
            self._domain_portalloc.release(ssh_port)
            raise RuntimeError(f"failed creating transient domain: {output}")

        domain_name = xml_root.find("name").text
        self.logger.debug(f"created transient domain {domain_name}")

        if self._stopped.is_set():
            virsh("destroy", domain_name, connect=self.uri)
            self._domain_portalloc.release(ssh_port)
            raise RuntimeError

        def release_hook(remote):
            self.logger.debug(f"releasing {remote}")

            # destroy (transient domain gets deleted)
            # - ignore any failure, ie. if the domain is already undefined
            virsh("destroy", domain_name, connect=self.uri)

            # free up ssh port allocated for portForward
            self._domain_portalloc.release(ssh_port)

            # remove from the list of remotes inside this Provisioner
            with self._lock:
                self._remotes.discard(remote)

            # potentially create replacement domain(s)
            self._spin_up_domains()

        remote = TempVirtRemote(
            domain=domain_name,
            origin_domain=self.origin_domain,
            release_hook=release_hook,
            options=ssh_options,
        )

        self.logger.debug(f"waiting for sshd on {remote}")
        if not util.wait_for_sshd(
            ssh_options["Hostname"],
            ssh_options["Port"],
            event=self._stopped,
            logger=self.logger,
        ):
            remote.release()
            raise RuntimeError

        self.logger.debug(f"connecting to {remote}")
        retries = 0
        while True:
            if self._stopped.wait(timeout=0.1):
                remote.release()
                raise RuntimeError
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
                    remote.release()
                    raise RuntimeError("maximum .connect() retries reached") from None
            except BaseException:
                remote.release()
                raise
            else:
                break

        # if .stop() was called while the domain was starting up
        if self._stopped.is_set():
            remote.release()
            raise RuntimeError

        return remote

    def get_remote(self, block=True):
        with self._lock:
            if block:
                self._lock.wait_for(lambda: len(self._queue) > 0 or self._stopped.is_set())

            if self._stopped.is_set():
                raise ProvisionerError("the provisioner is stopped")

            try:
                item = self._queue.popleft()
            except IndexError:
                return None  # only non-blocking

        return item.result()

    def clear(self):
        with self._lock:
            self._to_reserve = 0

    def __str__(self):
        class_name = self.__class__.__name__
        uri = f", {self.uri}" if self.uri else ""
        remotes = f"{len(self._remotes)}/{self.max_remotes}"
        return f"{class_name}({self.origin_domain}{uri}, {remotes} remotes)"
