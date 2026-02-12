# Libvirt server config

To use this Provisioner, the libvirt server needs to be configured in a slightly
special way. This doc details how.

## OS

Use as recent OS version as you can, ideally the latest released Fedora (or
equivalent) as the virtualization host.

The domains (VMs) can be much older, basically limited only by compatible
OpenSSH algorithms. If you need RHEL-6 or older, you might want to avoid using
virtio for some subsystems - use the oldest `--os-variant rhelX-unknown` you
care to support (when passing the option to `virt-install`).

## User access

There needs to be either a `root` or unprivileged user access to the server,
via OpenSSH, **using ssh keys** to connect. Passwords are not supported.

Note that you can have an unprivileged user connecting to its own unprivileged
`qemu:///session` libvirt, but some features (ie. `swtpm` emulation, or any
USB or other passthrough) won't be available.

An unprivileged user can also have full `qemu:///system` access if it is
in the `libvirt` group.

For finer-grain access to `qemu:///system` (since full libvirt access is still
dangerous), use Polkit, ie. `/etc/polkit-1/rules.d/100-libvirt-acl.rules` and
give the user only the permissions you need, ie.

```javascript
polkit.addRule(function(action, subject) {
    // systemctl edit polkit, remove --no-debug, then journalctl -u polkit -f
    //polkit.log("subject=" + subject + " // action=" + action);
    switch (true) {
        // unable to connect without this
        case action.id == "org.libvirt.unix.manage":
        // simple readonly things for everyone
        case action.id.endsWith(".read"):
        case action.id.endsWith(".getattr"):
        case /^org\.libvirt\.api\.[^\.]+\.search-/.test(action.id):
        // pool refreshes are harmless
        case action.id == "org.libvirt.api.storage-pool.refresh":
            return polkit.Result.YES;
    }
    switch (subject.user) {
        case "root":
            return polkit.Result.YES;
        case "libvirtuser":
            switch (true) {
                case action.id.startsWith("org.libvirt.api.domain."):
                case action.id.startsWith("org.libvirt.api.network-port."):
                case action.id.startsWith("org.libvirt.api.storage-vol."):
                    return polkit.Result.YES;
            }
    }
    return polkit.Result.NO;
});
```

along with

```sh
for drv in qemu network nodedev storage proxy lock log; do
  echo -e '\naccess_drivers = [ "polkit" ]' >> /etc/libvirt/virt${drv}d.conf
done
```

## `atex-virt-helper`

This helper is executed by the Provisioner, so it needs to be installed on the
server and executable by the user in `PATH`.

If the server is accessed via `ssh`, you can use `ForceCommand` for a specific
user in `/etc/ssh/sshd_config` (or `ssh_config.d/123-your-name.conf`), ie.

```
Match User libvirtuser
    DisableForwarding yes
    ForceCommand /opt/atex-virt-helper --log info qemu:///system
```

Also recommended is to set global `ClientAliveInterval` to ie. `5` to quickly
disconnect dead clients and release their reservations.

### Security

The helper **DOES NOT PROVIDE SECURITY**, it allows users to run `virsh` and
`virt-install` with arbitrary args, it doesn't sanitize file paths, etc.

Treat it as giving the user full shell access.

If you need extra security, use an unprivileged user authorized via Polkit,
see above.

## Libvirt itself

Since the domains (VMs) use passt user networking, there's no requirement on
the networking - you might want to remove the `default` network just in case.
Or don't install the `libvirt-daemon-config-network` RPM.

You do need one `<pool type='dir'>` storage pool, autostarted on boot, for
all the domains.

There need to be `virsh` and `virt-install` commands available in `PATH`
for use by the `atex-virt-helper`.

If using `virt-install`, you might want to pre-create the `boot-scratch` pool,
normally auto-created by `virt-install`, so users can use it without needing
more privileged access (for creating storage pools). It also helps avoid
race conditions.

```
<pool type="dir">
  <name>boot-scratch</name>
  <target>
    <path>/var/lib/libvirt/boot</path>
  </target>
</pool>
```

(and make it autostart)

## Domains (VMs)

The domains need to have pre-created (ie. via `qemu-img` or `virsh`) disk
images (volumes), since libvirt fails defining the XML without them.

When calculating the number of domains versus available RAM on the host,
account for extra memory used by QEMU itself. Also note that Fedora/RHEL
installed via Anaconda needs 4+ GB of RAM to install (stage2 downloaded
to RAM), a cut-down running system is just ~1 GB.

### Networking 

The domains also need to use user networking (specifically passt, not SLIRP)
to be reachable by the Provisioner. There needs to be at least one port
forwarded to domain port 22 (ssh) **for each domain** (VM), ie.

- port `5001` for `vmname1`
- port `5002` for `vmname2`
- etc.

Using `<portForward proto='tcp' address='0.0.0.0'>` is necessary for the
domain to be reachable from outside the virtualization host.

You might also want to use an unused private subnet for the domain itself,
to avoid it receiving an invalid hostname from your local DNS server.

Note that libvirt 11.1.0 has a more efficient `<interface type='vhostuser'>`
compared to the older `<interface type='user'>`.

Also note that libvirt 11.8.0 allows you to override the DNS-provided
hostname with `<backend type='passt' hostname='vmname1'/>`.

### Domain XML examples

The UEFI / Secure Boot version (modern VM):

```xml
<domain type='kvm'>
  <name>vmname1</name>
  <memory unit='GiB'>6</memory>
  <vcpu placement='static'>2</vcpu>
  <os firmware='efi'>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader secure='yes'/>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <smm state='on'/>
  </features>
  <cpu mode='host-passthrough'></cpu>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <disk type='volume' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' io='native'/>
      <source pool='default' volume='vmname1.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='user'>
      <backend type='passt'/>
      <model type='virtio'/>
      <ip address='100.80.60.1' family='ipv4' prefix='24'/>
      <portForward proto='tcp' address='0.0.0.0'>
        <range start='5001' to='22'/>
      </portForward>
    </interface>
    <console type='pty'>
      <target type='serial'/>
    </console>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>
  </devices>
</domain>
```

BIOS-using version (older VMs):

```xml
<domain type='kvm'>
  <name>vmname1</name>
  <memory unit='GiB'>6</memory>
  <vcpu placement='static'>2</vcpu>
  <os>
    <type arch='x86_64' machine='pc'>hvm</type>
    <bios useserial='yes'/>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
    <pae/>
  </features>
  <cpu mode='host-passthrough'></cpu>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <disk type='volume' device='disk'>
      <driver name='qemu' type='qcow2' cache='none' io='native'/>
      <source pool='default' volume='vmname1.qcow2'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='user'>
      <backend type='passt'/>
      <model type='virtio'/>
      <ip address='100.80.60.1' family='ipv4' prefix='24'/>
      <portForward proto='tcp' address='0.0.0.0'>
        <range start='5001' to='22'/>
      </portForward>
    </interface>
    <console type='pty'>
      <target type='serial'/>
    </console>
    <rng model='virtio'>
      <backend model='random'>/dev/urandom</backend>
    </rng>
  </devices>
</domain>
```

## Other users

The virtualization host can be used by non-Provisioner users, just make sure
to limit the Provisioner to reserve only domains (VMs) matching a specific
regular expression.

## Firewall

Since the Provisioner needs to access the passt-forwarded ssh ports (`5001`
in the examples above), you need either removed/disabled firewall, or have
allowed those TCP ports in the firewall.
