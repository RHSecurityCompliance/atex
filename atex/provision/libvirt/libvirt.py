import re
import time
import uuid
import shlex
import socket
import random
import tempfile
import threading
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from ... import connection, util
from .. import Provisioner, Remote
from . import locking

libvirt = util.import_libvirt()

# thread-safe bool
libvirt_needs_setup = threading.Semaphore(1)


def setup_event_loop():
    if not libvirt_needs_setup.acquire(blocking=False):
        return

    # register and run default even loop
    libvirt.virEventRegisterDefaultImpl()

    def loop():
        while True:
            time.sleep(0.5)
            libvirt.virEventRunDefaultImpl()

    util.debug("starting libvirt event loop")
    thread = threading.Thread(target=loop, name="libvirt_event_loop", daemon=True)
    thread.start()


class LibvirtCloningRemote(Remote, connection.ssh.ManagedSSHConn):
    """
    TODO
    """

    def __init__(self, ssh_options, host, domain, source_image, *, release_hook):
        """
        'ssh_options' are a dict, passed to ManagedSSHConn __init__().

        'host' is a str of libvirt host name (used for repr()).

        'domain' is a str of libvirt domain name (used for repr()).

        'source_image' is a str of libvirt volume name that was cloned
        for the domain to boot from (used for repr()).

        'release_hook' is a callable called on .release() in addition
        to disconnecting the connection.
        """
        # NOTE: self.lock inherited from ManagedSSHConn
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


# needs ManagedSSHConn due to .forward()
def reliable_ssh_local_fwd(conn, dest, retries=10):
    for _ in range(retries):
        # let the kernel give us a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        # and try to quickly use it for forwarding
        try:
            conn.forward("LocalForward", f"127.0.0.1:{port} {dest}")
            return port
        except subprocess.CalledProcessError:
            pass
    raise ConnectionError("could not add LocalForward / find a free port")


class LibvirtCloningProvisioner(Provisioner):
    """
    Provisioning done via pre-created libvirt domains on the libvirt VM host,
    which are left (largely) untouched, except for their disk images, which are
    swapped in by a fresh clones of a user-specified image name.
    (This image name is presumably a fresh OS install made by 3rd party logic.)

    This allows concurrent access by multiple users (no domains are created
    or removed, just taken/released) and fast provisioning times (volume cloning
    is much faster than Anaconda installs).

    Access to the libvirt host is via ssh, but the remote user does not need to
    have shell access, only TCP forwarding and libvirt socket access, ie.

        Match User libvirtuser
            AllowTcpForwarding yes
            ForceCommand /usr/bin/virt-ssh-helper qemu:///system
            #ForceCommand /usr/bin/nc -U /var/run/libvirt/libvirt-sock  # older

    Note that eligible domains must also have a pre-existing disk image defined
    as a volume (<disk type='volume' ...>) NOT as path (<disk type='path' ...>)
    since only a volume has a pool association that can be matched up with the
    would-be-cloned image name.
    """

    def __init__(
        self, host, image, *, pool="default", domain_filter=".*",
        domain_user="root", domain_sshkey,
        reserve_delay=3, reserve_time=3600, start_event_loop=True,
    ):
        """
        'host' is a ManagedSSHConn class instance, connected to a libvirt host.

        'image' is a string with a libvirt storage volume name inside the
        given storage 'pool' that should be used as the source for cloning.

        'pool' is a libvirt storage pool used by all relevant domains on the
        libvirt host **as well as** the would-be-cloned images.

        'domain_filter' is a regex string matching libvirt domain names to
        attempt reservation on. Useful for including only ie. 'auto-.*' domains
        while leaving other domains on the same libvirt host untouched.

        'domain_user' and 'domain_sshkey' (strings) specify how to connect to
        an OS booted from the pre-instaled 'image', as these credentials are
        known only to the logic that created the 'image' in the first place.

        'reserve_delay' is an int of how many seconds to wait between trying to
        lock libvirt domains, after every unsuccessful locking attempt.
        Ie. with delay=5 and 20 domains, the code will try to lock every domain
        in 5*20=100 seconds before looping back to the first.

        'reserve_time' is an int of maximum seconds to reserve a libvirt domain
        for before other users can steal it for themselves. Note that there is
        no automatic timeout release logic, it's just a hint for others.

        'start_event_loop' set to True starts a global default libvirt event
        loop as part of .start() (or context manager enter) in a background
        daemon thread.
        This is necessary to maintain connection keep-alives, but if you plan
        on managing the loop yourself (have custom uses for the libvirt module),
        setting False here avoids any meddling by this class.
        """
        self.lock = threading.RLock()
        self.host = host
        self.image = image
        self.pool = pool
        self.domain_filter = domain_filter
        self.domain_user = domain_user
        self.domain_sshkey = domain_sshkey
        self.reserve_delay = reserve_delay
        self.reserve_time = reserve_time
        self.start_event_loop = start_event_loop

        self.signature = uuid.uuid4()
        self.reserve_end = None
        self.queue = util.ThreadQueue(daemon=True)

        # use two libvirt connections - one to handle reservations and cloning,
        # and another for management and cleanup;
        # the idea is to neuter the reserving thread on exit simply by closing
        # its connection, so we can run cleanup from the other one
        self.reserve_conn = None
        self.manage_conn = None

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

        util.debug(
            f"found volume {source_vol.name()} (format:{source_format}) in pool {pool.name()}",
        )

        # translate domain names to virDomain objects
        with self.lock:
            already_reserving = self.reserving
        already_reserving = {conn.lookupByName(name) for name in already_reserving}

        # acquire (lock) a domain on the libvirt host
        util.debug("attempting to acquire a domain")
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
                    util.debug(f"acquired domain {acquired.name()}")
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
        xmldesc = acquired.XMLDesc()
        util.debug(f"domain {acquired.name()} XML:\n{xmldesc}")  # TODO: EXTRADEBUG log level
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
                p.refresh()
            try:
                nvram_vol = conn.storageVolLookupByPath(nvram_path)
            except libvirt.libvirtError as e:
                if "Storage volume not found" not in str(e):
                    raise
        if nvram_vol:
            util.debug(f"deleting nvram volume {nvram_vol.name()}")
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
            util.debug(f"found a domain disk in XML: {disk_vol_name} for pool {pool.name()}")
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
        util.debug(f"starting up {acquired.name()}")
        acquired.create()  # like 'virsh start' NOT 'virsh create'

        # wait for an IP address leased by libvirt host
        addrs = {}
        while not addrs:
            addrs = acquired.interfaceAddresses(
                libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE,
            )
            time.sleep(1)
        util.debug(f"found iface addrs: {addrs}")
        first_iface = next(iter(addrs.values()))
        first_addr = next(iter(first_iface.values()))[0]["addr"]

        # set up ssh LocalForward to it
        port = reliable_ssh_local_fwd(self.host, f"{first_addr}:22")

        # create a remote and connect it
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
                    except libvirt.libvirtError as e:
                        if "Domain not found" not in str(e):
                            raise
                # remove from the list of remotes inside this Provisioner
                try:
                    self.remotes.remove(remote)
                except ValueError:
                    pass

        ssh_options = {
            "Hostname": "127.0.0.1",
            "User": self.domain_user,
            "Port": str(port),
            "IdentityFile": self.domain_sshkey,
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

    def _open_libvirt_conn(self):
        # trick .cmd() to not run anything, but just return the ssh CLI
        cli_args = self.host.cmd(
            ("virt-ssh-helper", "qemu:///system"),
            func=lambda *args, **_: args[0],
        )
        # to make libvirt connect via our ManagedSSHConn, we need to give it
        # a specific ssh CLI, but libvirt URI command= takes only one argv[0]
        # and cannot pass arguments - we work around this by creating a temp
        # arg-less executable
        with tempfile.NamedTemporaryFile("w+t", delete_on_close=False) as f:
            f.write("#!/bin/bash\n")
            f.write("exec ")
            f.write(shlex.join(cli_args))
            f.write("\n")
            f.close()
            name = Path(f.name)
            name.chmod(0o0500)  # r-x------
            uri = f"qemu+ext:///system?command={urllib.parse.quote(str(name.absolute()))}"
            util.debug(f"opening libvirt conn to {uri}")
            conn = libvirt.open(uri)
        conn.setKeepAlive(5, 3)
        return conn

    def start(self):
        if self.start_event_loop:
            setup_event_loop()
        with self.lock:
            self.reserve_conn = self._open_libvirt_conn()
            self.manage_conn = self.reserve_conn  # for now
            self.reserve_end = int(time.time()) + self.reserve_time
            # get an initial first remote
            self.queue.start_thread(target=self._reserve_one)

    def stop(self):
        with self.lock:
            #util.debug(f"SELF.RESERVING: {self.reserving} // SELF.REMOTES: {self.remotes}")
            # close reserving libvirt host connection
            # - this stops _reserve_one() from doing anything bad
            if self.reserve_conn:
                self.reserve_conn.close()
                self.reserve_conn = None

            # reopen managing connection here (because we closed reserve_conn)
            # - note that we can't open this in .start() because libvirt conns
            #   can break on signals/interrupts, resulting in "Cannot recv data"
            self.manage_conn = self._open_libvirt_conn()
            # abort reservations in progress
            while self.reserving:
                try:
                    domain = self.manage_conn.lookupByName(self.reserving.pop())
                    locking.unlock(domain, self.signature)
                except libvirt.libvirtError as e:
                    util.debug(f"GOT ERROR: {str(e)}")
                    pass
            # cancel/release all Remotes ever created by us
            while self.remotes:
                self.remotes.pop().release()
            self.manage_conn.close()
            self.manage_conn = None

            self.reserve_end = None
            # TODO: wait for threadqueue threads to join?

    def get_remote(self, block=True):
        # if the reservation thread is not running, start one
        with self.lock:
            if not self.queue.threads:
                self.queue.start_thread(target=self._reserve_one)
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
            f"{class_name}({host_name}, {self.domain_filter}, {self.signature}, "
            f"{remotes} remotes, {hex(id(self))})"
        )
