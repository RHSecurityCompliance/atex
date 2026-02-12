import re

from ... import connection, util
from .. import Provisioner, Remote

class SharedVirtRemote(Remote, connection.ssh.ManagedSSHConnection):
    def __init__(self, ssh_options, host, domain, source_image, *, release_hook):
        """
        - `ssh_options` are a dict, passed to ManagedSSHConnection `__init__()`.

        - `host` is a str of libvirt host name (used for `repr()`).

        - `domain` is a str of libvirt domain name (used for `repr()`).

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
        self.release_hook(self)
        self.disconnect()

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.host}, {self.domain}, {self.source_image})"


class SharedVirtProvisioner(Provisioner):
    def __init__(
        self, host, image, *, pool="default",
        domain_filter=".*", domain_user="root", domain_sshkey, domain_host=None,
        reserve_delay=3, 
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

        - `domain_host` (string) is a hostname or an IP address through which
          to connect to the domains' ssh ports, as stored in the libvirt domain
          XML (`<backend type='passt'>`, `<portForward ...>`).

          Normally, this is extracted from `host` if it is *SSHConnection
          (the Hostname `ssh_options` attribute) and doesn't need to be provided
          here, but is necessary for non-SSH `host`.

          For example, for a LocalConnection, it would be `127.0.0.1`.

        - `reserve_delay` is an int of how many seconds to wait between trying
          to reserve a libvirt domain, reducing reservation bursting.
        """
        self.lock = threading.RLock()
        self.host = host
        self.image = image
        self.pool = pool
        self.domain_filter = domain_filter
        self.domain_user = domain_user
        self.domain_sshkey = domain_sshkey
        self.reserve_delay = reserve_delay

        if domain_host is None:
            if isinstance(
                host,
                (connection.ssh.ManagedSSHConnection, connection.ssh.StandaloneSSHConnection),
            ):
                domain_host = host.ssh_options["Hostname"]
            else:
                raise ValueError("'domain_host' not given and 'host' is not SSH")

        self.queue = util.ThreadQueue(daemon=True)
        self.to_reserve = 0

        # domain names we successfully locked, but which are still in the
        # process of being set up (image cloning, OS booting, waiting for ssh
        # etc.)
        self.reserving = set()

        # all active Remotes we managed to reserve and return to the user
        self.remotes = []

    def _reserve_one(self):
        with self.lock:
            conn = self.reserve_conn

        # find the to-be-cloned image in the specified pool
        pool = conn.storagePoolLookupByName(self.pool)
        source_vol = pool.storageVolLookupByName(self.image)

        # find the to-be-cloned image format
        xml_root = ET.fromstring(source_vol.XMLDesc())
        source_format = xml_root.find("target").find("format").get("type")

        logger.info(
            f"found volume {source_vol.name()} (format:{source_format}) in pool {pool.name()}",
        )

        # translate domain names to virDomain objects
        with self.lock:
            already_reserving = self.reserving
        already_reserving = {conn.lookupByName(name) for name in already_reserving}

        # acquire (lock) a domain on the libvirt host
        logger.info("attempting to acquire a domain")
        acquired = None
        while not acquired:
            domains = []
            for domain in conn.listAllDomains():
                if not re.match(self.domain_filter, domain.name()):
                    continue
                if domain in already_reserving:
                    continue
                domains.append(domain)

            random.shuffle(domains)
            for domain in domains:
                if locking.lock(domain, self.signature, self.reserve_end):
                    acquired = domain
                    logger.info(f"acquired domain {acquired.name()}")
                    break
                time.sleep(self.reserve_delay)

        with self.lock:
            self.reserving.add(acquired.name())

        # shutdown the domain so we can work with its volumes
        try:
            acquired.destroy()
        except libvirt.libvirtError as e:
            if "domain is not running" not in str(e):
                raise

        # parse XML definition of the domain
        xmldesc = acquired.XMLDesc().rstrip("\n")
        logger.debug(f"domain {acquired.name()} XML:\n{textwrap.indent(xmldesc, '    ')}")
        xml_root = ET.fromstring(xmldesc)
        nvram_vol = nvram_path = None

        # if it looks like UEFI/SecureBoot, try to find its nvram image in
        # any one of the storage pools and delete it, freeing any previous
        # OS installation metadata
        if (xml_os := xml_root.find("os")) is not None:
            if (xml_nvram := xml_os.find("nvram")) is not None:
                nvram_path = xml_nvram.text
        if nvram_path:
            # the file might be in any storage pool and is not refreshed
            # by libvirt natively (because treating nvram as a storage pool
            # is a user hack)
            for p in conn.listAllStoragePools():
                # retry a few times to work around a libvirt race condition
                for _ in range(10):
                    try:
                        p.refresh()
                    except libvirt.libvirtError as e:
                        if "domain is not running" in str(e):
                            break
                        elif "has asynchronous jobs running" in str(e):
                            continue
                        else:
                            raise
                    else:
                        break
            try:
                nvram_vol = conn.storageVolLookupByPath(nvram_path)
            except libvirt.libvirtError as e:
                if "Storage volume not found" not in str(e):
                    raise
        if nvram_vol:
            logger.info(f"deleting nvram volume {nvram_vol.name()}")
            nvram_vol.delete()

        # try to find a disk that is a volume in the specified storage pool
        # that we could replace by cloning from the provided image
        xml_devices = xml_root.find("devices")
        if xml_devices is None:
            raise RuntimeError(f"could not find <devices> for domain '{acquired.name()}'")

        disk_vol_name = None
        for xml_disk in xml_devices.findall("disk"):
            if xml_disk.get("type") != "volume":
                continue
            xml_disk_source = xml_disk.find("source")
            if xml_disk_source is None:
                continue
            if xml_disk_source.get("pool") != pool.name():
                continue
            disk_vol_name = xml_disk_source.get("volume")
            logger.info(f"found a domain disk in XML: {disk_vol_name} for pool {pool.name()}")
            break
        else:
            raise RuntimeError("could not find any <disk> in <devices>")

        # clone the to-be-cloned image under the same name as the original
        # domain volume
        new_volume = util.dedent(fr"""
            <volume>
                <name>{disk_vol_name}</name>
                <target>
                    <format type='{source_format}'/>
                </target>
            </volume>
        """)
        try:
            disk_vol = pool.storageVolLookupByName(disk_vol_name)
            disk_vol.delete()
        except libvirt.libvirtError as e:
            if "Storage volume not found" not in str(e):
                raise
        pool.createXMLFrom(new_volume, source_vol)

        # start the domain up
        logger.info(f"starting up {acquired.name()}")
        acquired.create()  # like 'virsh start' NOT 'virsh create'

        # wait for an IP address leased by libvirt host
        addrs = {}
        while not addrs:
            addrs = acquired.interfaceAddresses(
                libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE,
            )
            time.sleep(1)
        logger.info(f"found iface addrs: {addrs}")
        first_iface = next(iter(addrs.values()))
        first_addr = next(iter(first_iface.values()))[0]["addr"]

        # set up ssh LocalForward to it
        port = reliable_ssh_local_fwd(self.host, f"{first_addr}:22")

        # prepare release using variables from this scope
        def release_hook(remote):
            # un-forward the libvirt host ssh-forwarded port
            self.host.forward("LocalForward", f"127.0.0.1:{port} {first_addr}:22", cancel=True)

            # keep this entire block in a lock because the Provisioner can
            # swap out self.manage_conn and close the previous one at any time,
            # ie. between us reading self.manage_conn and using it
            with self.lock:
                # unlock the domain on the libvirt host
                if self.manage_conn:
                    try:
                        domain = self.manage_conn.lookupByName(remote.domain)
                        locking.unlock(domain, self.signature)
                        domain.destroy()
                    except libvirt.libvirtError as e:
                        if "Domain not found" not in str(e):
                            raise
                # remove from the list of remotes inside this Provisioner
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass

        # create a remote and connect it
        ssh_options = {
            "Hostname": "127.0.0.1",
            "User": self.domain_user,
            "Port": str(port),
            "IdentityFile": str(Path(self.domain_sshkey).absolute()),
            "ConnectionAttempts": "1000",
            "Compression": "yes",
        }
        remote = LibvirtCloningRemote(
            ssh_options=ssh_options,
            host=self.host.options["Hostname"],  # TODO: something more reliable?
            domain=acquired.name(),
            source_image=self.image,
            release_hook=release_hook,
        )
        # LocalForward-ed connection is prone to failing with
        # 'read: Connection reset by peer' instead of a timeout,
        # so retry a few times
        for _ in range(100):
            try:
                remote.connect()
                break
            except ConnectionError:
                time.sleep(0.5)

        with self.lock:
            self.remotes.append(remote)
            self.reserving.remove(acquired.name())

        return remote

    def start(self):
        # TODO: connect via ssh to VM host
        if self.start_event_loop:
            setup_event_loop()
        with self.lock:
            self.reserve_conn = self._open_libvirt_conn()
            self.manage_conn = self.reserve_conn  # for now
            self.reserve_end = int(time.time()) + self.reserve_time

    def stop(self):
        with self.lock:
            # TODO: ssh connection to VM host

            # abort reservations in progress
            while self.reserving:
                try:
                    domain = self.manage_conn.lookupByName(self.reserving.pop())
                    locking.unlock(domain, self.signature)
                except libvirt.libvirtError:
                    pass

            # cancel/release all Remotes ever created by us
            while self.remotes:
                self.remotes.pop().release()
            self.manage_conn.close()
            self.manage_conn = None

            # TODO: wait for threadqueue threads to join?

    def provision(self, count=1):
        with self.lock:
            self.to_reserve += count

    def get_remote(self, block=True):
        with self.lock:
            # if the reservation thread is not running, start one
            if not self.queue.threads and self.to_reserve > 0:
                self.queue.start_thread(target=self._reserve_one)
                self.to_reserve -= 1
        try:
            return self.queue.get(block=block)
        except util.ThreadQueue.Empty:
            # always non-blocking
            return None

    # not /technically/ a valid repr(), but meh
    def __repr__(self):
        class_name = self.__class__.__name__
        remotes = len(self.remotes)
        host_name = self.host.options["Hostname"]
        return (
            f"{class_name}({host_name}, {self.domain_filter}, "
            f"{remotes} remotes, {hex(id(self))})"
        )
