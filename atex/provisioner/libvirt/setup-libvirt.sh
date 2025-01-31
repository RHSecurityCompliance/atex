#!/bin/bash

set -xe

# install RPM dependencies
dnf --setopt=install_weak_deps=False -y install \
    libvirt-daemon-driver-qemu \
    libvirt-daemon-driver-storage-disk \
    libvirt-daemon-config-network \
    libvirt-client \
    qemu-kvm \
    swtpm-tools

# start all sockets that were enabled by libvirt-daemon RPM scripts
# (simulating a reboot)
if systemctl --quiet is-enabled libvirtd.service; then
    systemctl start libvirtd.service
else
    sockets=$(
        systemctl list-unit-files --full \
        --type=socket --state=enabled 'virt*' \
        | grep '^virt' | sed 's/ .*//'
    )
    for socket in $sockets; do
        systemctl start "$socket"
    done
fi

tmpfile=$(mktemp)
trap "rm -f \"$tmpfile\"" EXIT

# set up a default network
if virsh -q net-list --name | grep -q '^default *$'; then
    virsh net-destroy default
    virsh net-undefine default
elif virsh -q net-list --name --inactive | grep -q '^default *$'; then
    virsh net-undefine default
fi
cat > "$tmpfile" <<EOF
<network>
    <name>default</name>
    <forward mode='nat'/>
    <bridge name='virbr0' stp='off' delay='0'/>
    <ip address='100.80.60.1' netmask='255.255.255.0'>
        <dhcp>
            <range start='100.80.60.2' end='100.80.60.250'/>
        </dhcp>
    </ip>
</network>
EOF
virsh net-define "$tmpfile"
virsh net-autostart default
virsh net-start default

# set up a default storage pool
if virsh -q pool-list --name | grep -q '^default *$'; then
    virsh pool-destroy default
    virsh pool-undefine default
elif virsh -q pool-list --name --inactive | grep -q '^default *$'; then
    virsh pool-undefine default
fi
cat > "$tmpfile" <<EOF
<pool type='dir'>
    <name>default</name>
    <target>
        <path>/var/lib/libvirt/images</path>
    </target>
</pool>
EOF
virsh pool-define "$tmpfile"
virsh pool-autostart default
virsh pool-start default

# create another storage pool for nvram .vars files,
# so they can be easily removed using just a libvirt connection
if virsh -q pool-list --name | grep -q '^nvram *$'; then
    virsh pool-destroy nvram
    virsh pool-undefine nvram
elif virsh -q pool-list --name --inactive | grep -q '^nvram *$'; then
    virsh pool-undefine nvram
fi
cat > "$tmpfile" <<EOF
<pool type='dir'>
    <name>nvram</name>
    <target>
        <path>/var/lib/libvirt/qemu/nvram</path>
    </target>
</pool>
EOF
virsh pool-define "$tmpfile"
virsh pool-autostart nvram
virsh pool-start nvram
