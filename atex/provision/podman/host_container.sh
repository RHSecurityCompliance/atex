#!/bin/bash

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <podman-image-name>" >&2
    exit 1
fi
image_name="$1"

set -e -x

tmpdir=$(mktemp -d -p /var/tmp)
trap "rm -rf '$tmpdir'" EXIT

installroot="$tmpdir/root"

dnf \
    --installroot="$installroot" \
    --setopt=install_weak_deps=False \
    --setopt=tsflags=nodocs \
    -q -y groupinstall minimal-environment

echo -n > "$installroot/etc/machine-id"
#echo container > "$installroot/etc/hostname"

cp -f /etc/yum.repos.d/* "$installroot/etc/yum.repos.d/."
cp -f /etc/pki/rpm-gpg/* "$installroot/etc/pki/rpm-gpg/."

echo install_weak_deps=False >> "$installroot/etc/dnf/dnf.conf"
echo tsflags=nodocs >> "$installroot/etc/dnf/dnf.conf"

ln -sf \
    /usr/lib/systemd/system/multi-user.target \
    "$installroot/etc/systemd/system/default.target"

systemctl --root="$installroot" disable \
    auditd.service crond.service rhsmcertd.service sshd.service

#encrypted=$(openssl passwd -6 somepass)
#usermod --root="$installroot" --password "$encrypted" root

dnf clean packages --installroot="$installroot"

tar --xattrs -C "$installroot" -cf "$tmpdir/packed.tar" .

rm -rf "$installroot"

podman import \
    --change 'CMD ["/sbin/init"]' \
    "$tmpdir/packed.tar" "$image_name"

# start as
# podmn {run,create} --systemd=always --cgroups=split --device /dev/kvm ...
#
# podman run -t -i \
#   --systemd=always --cgroups=split \
#   --device /dev/kvm \
#   --network=bridge \
#   --cap-add NET_ADMIN --cap-add NET_RAW --cap-add SYS_MODULE \
#   --mount type=bind,src=/lib/modules,dst=/lib/modules,ro \
#   --mount type=bind,src=/proc/sys/net,dst=/proc/sys/net,rw \
#   my_container
#
# as unprivileged user:
# podman run -t -i \
#   --systemd=always --cgroups=split --network=bridge --privileged \
#   my_container
#
# container setup:
# dnf -y install libvirt-daemon qemu-kvm libvirt-client libvirt-daemon-driver-qemu virt-install libvirt-daemon-driver-storage libvirt-daemon-config-network
# echo $'user = "root"\ngroup = "root"\nremember_owner = 0' >> /etc/libvirt/qemu.conf
# systemctl start virtqemud.socket virtstoraged.socket virtnetworkd.socket
# virsh net-start default
# virt-install --install fedora40 --disk /var/lib/libvirt/images/foo.qcow2,size=20 --console pty --check disk_size=off --unattended --graphics none

