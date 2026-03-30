#!/bin/bash

# OS preparation script, run on a Testing Farm reserved machine after SSH
# is up, cleaning up Testing Farm / Beaker leftovers and restoring the OS
# to a vanilla-ish state.

set -e -x

os_id=$(. /etc/os-release; echo "$ID")
os_version=$(. /etc/os-release; echo "$VERSION_ID")

# ------------------------------------------------------------------------------

# remove tmt-related commands
# (if running tmt via 'provision -h connect', tmt will upload its own)
rm -f /usr/local/bin/{tmt,rstrnt,rhts}-*

# ------------------------------------------------------------------------------

# remove testing farm reservation test related files,
# make the reservation last until pipeline timeout (ignoring its timers)
touch /var/tmp/.testing-farm-keep
echo -n > /etc/motd
echo -n > /etc/profile.d/sh.local
rm -rf /root/bin /root/.reserved-until

# ------------------------------------------------------------------------------

if [[ ! -e /run/ostree-booted ]]; then
    # remove useless daemons to free up RAM a bit
    dnf remove -y rng-tools irqbalance

    # clean up packages from extra repos, restoring original vanilla OS (sorta)
    rm -v -f \
        /etc/yum.repos.d/{tag-repository*,*beakerlib*,beaker-harness,rcmtools,rcm-tools,qa-tools}.repo \
        /etc/yum.repos.d/beaker-{client,harness,tasks}.repo
    # downgrade any packages installed/upgraded from the extra package repos
    function list_foreign_rpms {
        dnf list --installed \
        | grep -e @koji-override -e @testing-farm -e @epel -e @beaker-harness \
               -e @copr: -e @rcmtools -e @rcm-tools -e '<unknown>$' \
        | sed 's/ .*//'
    }
    rpms=$(list_foreign_rpms)
    [[ $rpms ]] && dnf downgrade -y --skip-broken $rpms || true
    rpms=$(list_foreign_rpms)
    [[ $rpms ]] && dnf remove -y --noautoremove $rpms
    dnf clean all
fi

# ------------------------------------------------------------------------------

# replace fedora mirrormanager-based repositories with primary/master ones,
# which tend to be a lot more reliable
# - this is to avoid checksum errors that very commonly pop up on mirrormanager
#   on all mirrors (so trying different mirrors doesn't help and dnf eventually
#   fails):
#     Downloading successful, but checksum doesn't match. Calculated: 1abb62...
#     Expected: a91641...
function mkrepo {
    echo "[$1]"
    echo "name=$1"
    echo "baseurl=$2"
    [[ $GPGKEY ]] && echo "gpgkey=$GPGKEY"
    echo "gpgcheck=1"
    local additional
    for additional in "${@:3}"; do
        echo "$additional"
    done
}
# 8 is on vault/archive, 10 is currently broken
if [[ $os_id == centos && ( $os_version == 9 || $os_version == 10 ) ]]; then
    case "$os_version" in
        9)  variants="BaseOS AppStream CRB HighAvailability NFV RT ResilientStorage" ;;
        10) variants="BaseOS AppStream CRB HighAvailability NFV RT" ;;
    esac
    GPGKEY=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial
    rm -f /etc/yum.repos.d/centos{,-addons}.repo
    for variant in $variants; do
        mkrepo "centos-master-$variant" "https://mirror.stream.centos.org/\$stream/$variant/\$basearch/os/" enabled=1
        mkrepo "centos-master-$variant-source" "https://mirror.stream.centos.org/\$stream/$variant/source/tree/" enabled=0
        mkrepo "centos-master-$variant-debuginfo" "https://mirror.stream.centos.org/\$stream/$variant/\$basearch/debug/tree/" enabled=0
        echo
    done > /etc/yum.repos.d/centos-master.repo
fi

# ------------------------------------------------------------------------------

# on RHEL, TF systems have wildly inconsistent repository configurations;
# sometimes duplicating beaker-*.repo inside rhel.repo (causing dnf warnings),
# sometimes with some of the rhel.repo entries disabled, and all with gpgcheck=0
# and without any gpgkey=
# get around all of that by trying to extract known-good data and re-create
# sensible GPG-enabled entries from scratch
if [[ $os_id == rhel ]]; then
    gpgkeys=()
    for key in /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat*; do
        gpgkeys+=("file://$key")
    done

    # if beaker-* repos exist, use them and throw away rhel.repo
    if [[ -f /etc/yum.repos.d/beaker-BaseOS.repo ]]; then
        rm -f /etc/yum.repos.d/rhel.repo

        for repofile in /etc/yum.repos.d/beaker-{AppStream,BaseOS,CRB,HighAvailability,ResilientStorage,SAP}*.repo; do
            sed 's/^gpgcheck=0$/gpgcheck=1/' -i "$repofile"
            if ! grep -q '^gpgkey=' "$repofile"; then
                # after each gpgcheck=1
                sed '/^gpgcheck=1$/a'" gpgkey=${gpgkeys[*]}" -i "$repofile"
            fi
        done

    # only rhel.repo exists, just enable gpgcheck=1 and add gpgkey=
    elif [[ -f /etc/yum.repos.d/rhel.repo ]] && grep -q '^name=rhel-BaseOS$' /etc/yum.repos.d/rhel.repo; then
        sed 's/^gpgcheck=0$/gpgcheck=1/' -i /etc/yum.repos.d/rhel.repo
        if ! grep -q '^gpgkey=' /etc/yum.repos.d/rhel.repo; then
            sed '/^gpgcheck=1$/a'" gpgkey=${gpgkeys[*]}" -i /etc/yum.repos.d/rhel.repo
        fi
    fi
fi

# ------------------------------------------------------------------------------

# remove useless legacy mountpoints (some have sticky bits)
umount -f /mnt/* || true
rmdir /mnt/*/*/* /mnt/*/* /mnt/* || true
sed -rn '/^[^ ]+ \/mnt/!p' -i /etc/fstab
# prevent /mnt/scratch* from being created on reboot
echo -n > /etc/tmpfiles.d/restraint.conf

# ------------------------------------------------------------------------------

# upgrade to latest available packages from each given stream
# - this fixes issues with outdated packages, and overall isn't that big,
#   typically 10-30 packages are upgraded
if [[ $os_id == rhel || $os_id == centos ]]; then
    dnf upgrade -y --skip-broken || true
fi
