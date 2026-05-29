import collections
import itertools
import subprocess
import threading
import xml.etree.ElementTree as ET


def virsh(*args, connect=None, **kwargs):
    connect_args = ("-c", connect) if connect else ()
    proc_args = {
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "input": "",
    }
    proc_args |= kwargs
    proc = subprocess.run(("virsh", "-q", *connect_args, *args), **proc_args)
    return (proc.returncode, proc.stdout)


def image_from_volume(pool, volume, *, connect=None):
    """
    Extract a disk image path from a storage pool / volume specification.

    - `pool` is a storage pool name.

    - `volume` is a storage volume name (inside the pool).

    - `connect` is an optional libvirt URI to connect to.
    """
    # look up the pool, ensure it is type=dir
    code, output = virsh("pool-dumpxml", pool, connect=connect)
    if code != 0:
        raise ValueError(f"failed getting pool '{pool}': {output}")
    xml_root = ET.fromstring(output)
    if xml_root.get("type") != "dir":
        raise ValueError("only type=dir storage pools are supported")

    # get the actual file path for the volume
    code, output = virsh("vol-dumpxml", volume, pool, connect=connect)
    if code != 0:
        raise RuntimeError(f"failed getting volume '{volume}' in pool '{pool}': {output}")
    xml_root = ET.fromstring(output)

    if (xml_target := xml_root.find("target")) is not None:
        if (xml_path := xml_target.find("path")) is not None:
            if xml_path.text:
                return xml_path.text

    raise RuntimeError(f"volume '{volume}' in pool '{pool}' has no path")


def _find_primary_disk(xml_devices, *, connect=None):
    """
    Return (disk_element, disk_file_path, disk_format) as a tuple,
    or None if no disk was found.
    """
    for xml_disk in xml_devices.findall("disk"):
        # skip non-disk devices (cdroms, floppies, etc.)
        if xml_disk.get("device") != "disk":
            continue
        # find out format
        if (xml_driver := xml_disk.find("driver")) is None:
            continue
        if (disk_format := xml_driver.get("type")) is None:
            continue
        if (xml_source := xml_disk.find("source")) is None:
            continue
        disk_type = xml_disk.get("type")
        # file-based disk, source path available directly
        if disk_type == "file":
            if (path := xml_source.get("file")):
                return (xml_disk, path, disk_format)
        # pool/volume-based disk, resolve via image_from_volume
        elif disk_type == "volume":
            pool = xml_source.get("pool")
            volume = xml_source.get("volume")
            if pool and volume:
                path = image_from_volume(pool, volume, connect=connect)
                return (xml_disk, path, disk_format)
    return None


def transient_domain_xml(from_domain, *, connect=None):
    """
    Build an XML root element of a to-be-created domain using another domain,
    identified by a `from_domain` name, as a template.

    - `connect` is an optional libvirt URI to connect to.
    """
    code, output = virsh("dumpxml", from_domain, "--inactive", connect=connect)
    if code != 0:
        raise ValueError(f"failed getting domain '{from_domain}': {output}")
    xml_root = ET.fromstring(output)

    if (xml_devices := xml_root.find("devices")) is None:
        raise RuntimeError(f"domain '{from_domain}' has no '<devices>'")

    # find the first disk image of the domain
    primary_disk = _find_primary_disk(xml_devices, connect=connect)
    if not primary_disk:
        raise RuntimeError(f"no supported disk found for domain '{from_domain}'")

    # replace the primary disk with a type=file transient one
    xml_disk, image_path, image_format = primary_disk
    xml_devices.remove(xml_disk)
    new_disk = ET.SubElement(xml_devices, "disk", type="file", device="disk")
    ET.SubElement(new_disk, "driver", name="qemu", type=image_format, cache="unsafe")
    ET.SubElement(new_disk, "source", file=image_path)
    ET.SubElement(new_disk, "transient", shareBacking="yes")
    new_disk.append(xml_disk.find("target"))

    # clear the nvram path so each transient domain gets its own
    # auto-generated UEFI variable store, keeping any template reference
    if (xml_os := xml_root.find("os")) is not None:
        if (xml_nvram := xml_os.find("nvram")) is not None:
            xml_nvram.text = None

    # disable SELinux relabeling so multiple transient domains
    # can share the same backing image
    for seclabel in xml_root.findall("seclabel"):
        xml_root.remove(seclabel)
    ET.SubElement(xml_root, "seclabel", type="none")

    # remove TPM emulator (its state is per-domain and not shareable)
    for tpm in xml_devices.findall("tpm"):
        xml_devices.remove(tpm)

    # replace network with passt
    for iface in xml_devices.findall("interface"):
        xml_devices.remove(iface)
    new_iface = ET.SubElement(xml_devices, "interface", type="user")
    ET.SubElement(new_iface, "backend", type="passt")
    ET.SubElement(new_iface, "model", type="virtio")
    ET.SubElement(new_iface, "ip", address="100.80.60.1", family="ipv4", prefix="24")

    return xml_root


class PortAllocator:
    """
    Count up from `start`, allocating ports for listening, trying to avoid
    re-using ports (to not mis-connect to a wrong system) via FIFO reuse
    if the number of allocations grow to/beyond `reuse_after`.
    """
    def __init__(self, start=0, reuse_after=200):
        self._lock = threading.RLock()
        self._counter = itertools.count(start)
        self._reuse_after = start + reuse_after
        self._current = start - 1
        self._released = collections.deque()

    def acquire(self):
        with self._lock:
            if self._released and self._current >= self._reuse_after:
                return self._released.popleft()
            self._current = next(self._counter)
            return self._current

    def release(self, port):
        with self._lock:
            self._released.append(port)
