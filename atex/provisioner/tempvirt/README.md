> [!NOTE]
> This describes a specific implementation of the abstract Provisioner API.
> See also the [documentation of the generic API](..).

# Temporary Virtual machine Provisioner

```python
# pre-existing installed shut-off virtual machine (a.k.a. a "domain")
origin = "my-fedora-123"

with TempVirtProvisioner(origin, domain_sshkey="key_file", max_remotes=5) as p:
    p.provision(3)
    for _ in range(3):
        remote = p.get_remote()
        remote.cmd(["cat", "/etc/passwd"])
        remote.release()
```

This creates temporary (transient) virtual machines, called "domains" in Libvirt
terminology, from one origin source virtual machine.

The provisioner tries to re-use as much as possible from the origin domain XML,
so it can "clone" BIOS, UEFI, or even emulated machines. This also extends to
the amount of RAM the origin domain has, VCPUs, etc.

The transient domains (VMs) are automatically removed on their shutdown, or
libvirt (or your OS) restart, so even in the event of a crash, they don't
exist persistently on your machine. Only your origin domain remains.

The origin domain **remains untouched** by the transient domains, your data
is safe. However it **must be shut off** prior to TempVirtProvisioner using
it, otherwise the transient domains would try to boot up an OS in an unclean
state.

Finally, TempVirtProvisioner only works with origin domains that specify their
primary disk via `type='file'`. Note that `type='volume'` is supported too,
but the underlying storage pool must be of `type='dir'`. IOW the disk image
must be a regular file, not an LVM volume or something nebulous.

## How it works

Simply put, this relies on the `<transient/>` disk XML element tag, which
Libvirt implements by letting QEMU load the original disk image as if it was
starting the origin domain, but - before it gets unpaused - it tells QEMU to
create a qcow2 overlay of that disk, effectively doing CoW to a temporary
file in the same location (filesystem) as the original disk file.

Coupled with `virsh create`, which always creates transient domains (without
on-disk XML definition), this nicely creates very temporary single-use domains
that can be used for testing.

Networking of the origin domain is swapped for `<interface type='user'/>`
(to work with unprivileged `qemu:///session` too) with `<backend type='passt'>`
and its `<portForward ...>` exposing the in-domain sshd via a simple listening
TCP port on the host.

The starting port is `__init__()` configurable and the address is `0.0.0.0`
for remote libvirt hosts, or simply `127.0.0.1` for local ones, for safety.

TempVirtRemote then, backed by ManagedSSHConnection, simply connects to the
libvirt host on this port, providing user with a class Remote API.
