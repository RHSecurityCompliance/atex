#!/bin/bash

set -e -x

function efi_boot_into_current {
    if command -v efibootmgr >/dev/null; then
        current=$(efibootmgr | sed -n 's/^BootCurrent: //p')
        efibootmgr -n "$current"
    fi
}

# no-op on second/third/etc. execution
if [[ $TMT_TEST_RESTART_COUNT && $TMT_TEST_RESTART_COUNT -gt 0 ]]; then
    efi_boot_into_current
    exec sleep inf
    exit 1
fi

# do not remove /var/tmp/tmt-test.pid* here
# it typically contains the TF-started reserve test PID, and tmt-* commands
# read the file to (incorrectly) kill the TF test PID, but
#
#   1) non-tmt users don't care, they never upload their own tmt-* commands
#      (and we remove the TF-made ones below)
#   2) tmt 'provision -h connect' users have their own tmt instance override
#      the pidfile anyway, so their tmt-* commands impact their own test,
#      letting systemd kill the TF-started one on reboot
#
# there is a race condition on reboot between TF and user-started tmt,
# each wanting to override the pidfile of the other one, and other measures
# are needed to prevent that, but removing the pidfile would only bring
# extra chaos into it

# always reboot into the same OS entry (unless otherwise overriden)
efi_boot_into_current

# remove tmt-related commands
# (if running tmt via 'provision -h connect', tmt will upload its own)
rm -f /usr/local/bin/tmt-*

# remove useless daemons to free up RAM a bit
dnf remove -y rng-tools irqbalance

# clean up packages from extra repos, restoring original vanilla OS (sorta)
rm -v -f \
    /etc/yum.repos.d/{tag-repository,*beakerlib*,rcmtools}.repo \
    /etc/yum.repos.d/beaker-{client,harness,tasks}.repo
# downgrade any packages installed/upgraded from the extra package repos
function list_foreign_rpms {
    dnf list --installed \
    | grep -e @koji-override -e @testing-farm -e @epel -e @copr: -e @rcmtools \
    | sed 's/ .*//'
}
rpms=$(list_foreign_rpms)
[[ $rpms ]] && dnf downgrade -y --skip-broken $rpms
rpms=$(list_foreign_rpms)
[[ $rpms ]] && dnf remove -y --noautoremove $rpms
dnf clean all

# install SSH key
if [[ $RESERVE_SSH_PUBKEY ]]; then
    mkdir -p ~/.ssh
    chmod 0700 ~/.ssh
    echo "$RESERVE_SSH_PUBKEY" >> ~/.ssh/authorized_keys
    chmod 0600 ~/.ssh/authorized_keys
else
    echo "RESERVE_SSH_PUBKEY env var not defined" >&2
    exit 1
fi

exec sleep inf
exit 1  # fallback
