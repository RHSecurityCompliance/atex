from pathlib import Path

from .. import util

from . import fmf

SCRIPTS_DEPENDENCIES = ('nmap-ncat',)


def test_wrapper(*, test, tests, tmpdir_template, control, debug=False):
    """
    Generate a bash script that runs a user-specified test, preparing
    an environment for it, and reporting its exit code.
    The script must be as "transparent" as possible, since any output
    is considered as test output and any unintended environment changes
    will impact the test itself.

    'test' is a atex.minitmt.fmf.FMFTest instance.

    'tests' is a directory (repository) of all the tests, FMF metadata root.

    'tmpdir_template' is a placeholder string (template) to be used in place
    of a temporary directory, to be replaced by ie. 'sed'.
    This directory will be removed via 'rm -rf' on script exit.

    'control' is a UNIX domain socket file name inside 'tmpdir_template',
    used for controlling test execution per the CONTROL_FILE.md spec.

    'debug' specifies whether to include wrapper output inside test output.
    """
    control_path = f"{tmpdir_template}/{control}"
    out = "#!/bin/bash\n"

    if debug:
        out += "set -x\n"

    # use a subshell to limit the scope of env variables and the CWD change
    out += "(\n"

    # environment:
    #   - SOME: some_value
    #     ANOTHER: another_value
    #   - SECOND: second_value
    env = {}
    for item in fmf.listlike(test.data, "environment"):
        env.update(item)
    for key, value in env.items():
        out += f"export -- '{key}={value}'\n"

    # export additional TMT-style variables
    out += util.dedent(fr"""
        export -- 'TMT_TEST_NAME={test.name}'
        export -- 'ATEX_CONTROL_FILE={control_path}'
    """) + "\n"

    # TODO: custom PATH with tmt-* style commands?

    # join the directory with all tests and nested path of our test inside it
    test_cwd = Path(tests) / test.dir
    out += f"cd '{test_cwd}' || exit 1\n"

    # wrap the test script in a separate interpreter, don't rely on subshell
    # as bash v4+ interprets some control builtins (ie. set) to have scope
    # beyond the subshell - also, 'kill $$' would refer to this wrapper, etc.
    out += f"exec -a 'bash: atex running {test.name}' bash <<'ATEX_WRAPPER_EOF'\n"
    # this is to mimic what full fat tmt uses
    out += "set -eo pipefail\n"
    out += test.data['test']
    out += "\nATEX_WRAPPER_EOF\n"

    # subshell end
    out += ")\n"

    # write test exitcode to control socket
    out += "rc=$?\n"
    out += f"ncat --send-only -U '{control_path}' <<<\"exitcode $rc\"\n"

    # delete any UNIX sockets and any other wrapper-related metadata
    out += f"rm -rf '{tmpdir_template}'\n"

    # always exit the wrapper with 0 if test execution was normal
    out += "exit 0\n"

    return out


def test_setup(*, test, wrapper, debug=False, **kwargs):
    """
    Generate a bash script that should prepare the remote end for test
    execution. The bash script itself should create another bash script,
    a test wrapper, that would be executed to run the test.

    'test' is a atex.minitmt.fmf.FMFTest instance.

    'wrapper' is a test wrapper file (script) name (not full path) inside
    a (would-be-created) tmpdir.

    'debug' specifies whether to make the setup script extra verbose.

    Any 'kwargs' are passed to test_wrapper().
    """
    out = "#!/bin/bash\n"

    # have deterministic stdin, avoid leaking parent console
    # also avoid any accidental stdout output, we use it for passing tmpdir path
    if debug:
        out += "exec {orig_stdout}>&1 1>&2\n"
        out += "set -xe\n"
    else:
        out += "exec {orig_stdout}>&1 2>/dev/null 1>&2\n"
        out += "set -e\n"

    # install test dependencies
    # - only strings (package names) in require/recommend are supported
    if require := [x for x in fmf.listlike(test.data, "require") if isinstance(x, str)]:
        require += SCRIPTS_DEPENDENCIES
        out += "dnf -y --setopt=install_weak_deps=False install "
        out += " ".join(f"'{pkg}'" for pkg in require) + "\n"
    if recommend := [x for x in fmf.listlike(test.data, "recommend") if isinstance(x, str)]:
        out += "dnf -y --setopt=install_weak_deps=False install --skip-broken "
        out += " ".join(f"'{pkg}'" for pkg in recommend) + "\n"

    # make a unique (race-free) tmpdir for UNIX sockets, etc.
    out += "tmpdir=$(mktemp -d)\n"

    # create a test wrapper inside the tmpdir
    out += f"cat > \"$tmpdir/{wrapper}\" <<'ATEX_SETUP_EOF'\n"
    out += test_wrapper(
        test=test,
        tmpdir_template='%%%TMPDIR%%%',
        debug=debug,
        **kwargs,
    )
    out += "ATEX_SETUP_EOF\n"

    # replace tmpdir_template inside the wrapper script with the mktemp'd one
    out += f'sed -i "s|%%%TMPDIR%%%|$tmpdir|g" "$tmpdir/{wrapper}"\n'
    out += f'chmod 0755 "$tmpdir/{wrapper}"\n'

    # return tmpdir back over ssh to the caller, so it can order ssh to create
    # a UNIX socket in it and run 'wrapper' inside it
    out += 'echo "tmpdir=$tmpdir" >&$orig_stdout\n'

    out += "exit 0\n"

    return out


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
