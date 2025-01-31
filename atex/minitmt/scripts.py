#from .. import util

#run_test = util.dedent(fr'''
#    # create a temp dir for everything, send it to the controller
#    tmpdir=$(mktemp -d /var/tmp/atex-XXXXXXXXX)
#    echo "tmpdir=$tmpdir"
#
#    # remove transient files if interrupted
#    trap "rm -rf \"$tmpdir\"" INT
#
#    # wait for result reporting unix socket to be created by sshd
#    socket=$tmpdir/results.sock
#    while [[ ! -e $socket ]]; do sleep 0.1; done
#    echo "socket=$socket"
#
#    # tell the controller to start logging test output
#    echo ---
#
#    # install test dependencies
#    rpms=( {' '.join(requires)} )
#    to_install=()
#    for rpm in "${{rpms[@]}}"; do
#        rpm -q --quiet "$rpm" || to_install+=("$rpm")
#    done
#    dnf -y --setopt=install_weak_deps=False install "${{to_install[@]}}"
#
#    # run the test
#    ...
#    rc=$?
#
#    # test finished, clean up
#    rm -rf "$tmpdir"
#
#    exit $rc
#''')

# TODO: have another version of ^^^^ for re-execution of test after a reboot
#       or disconnect that sets tmpdir= from us (reusing on-disk test CWD)
#       rather than creating a new one
#         - the second script needs to rm -f the unix socket before echoing
#           something back to let us re-create it via a new ssh channel open
#           because StreamLocalBindUnlink doesn't seem to work


# TODO: call ssh with -oStreamLocalBindUnlink=yes to re-initialize
#       the listening socket after guest reboot
#
#       -R /var/tmp/atex-BlaBla/results.sock:/var/tmp/controller.sock
#
#       (make sure to start listening on /var/tmp/controller.sock before
#        calling ssh to run the test)
