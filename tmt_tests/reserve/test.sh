#!/bin/bash

set -e -x

# remove useless daemons to free up RAM a bit
dnf remove -y rng-tools irqbalance

# clean up packages from extra repos, restoring original vanilla OS (sorta)
rm -v -f \
    /etc/yum.repos.d/{tag-repository,*beakerlib*,rcmtools}.repo \
    /etc/yum.repos.d/beaker-{client,harness,tasks}.repo

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

# wait forever
sleep inf
