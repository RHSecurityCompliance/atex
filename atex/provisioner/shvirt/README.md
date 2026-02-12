# Shared virtual host provisioner

This uses a set of pre-configured domains (VMs) that sit permanently on the
server. Ie. `vmname1` through `vmname20`. These are ideally XML-defined via
`virsh define` to be exactly like you want them (UEFI, serial console, TPM2,
etc.).

They need to have (empty for start) disk images (libvirt volumes) pre-created
in one common `<pool type='dir'>` storage pool, using the `<disk type='volume'>`
syntax, **NOT** pointing to the files directly via `<disk type='file'>`.

In addition, you need pre-made OS images (as volumes, possibly without an
associated domain) in the same storage pool. These can be created using
`virt-install`, built by OSBuild, generated via libguestfs, whatever.

The domains are then "reserved" by the Provisioner and the pre-made OS images
are cloned to be the domain volumes, before being started up - **this is the
core idea of the Provisioner**.

For more details, see

- [SERVER.md](SERVER.md) for how to set up a libvirt server compatible with
  this Provisioner.
- [PROTOCOL.md](PROTOCOL.md) for details how the Provisioner and the
  server-side `atex-virt-helper` talk.

