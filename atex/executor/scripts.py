import collections
import yaml
from pathlib import Path

from .. import util, fmf

# name: fmf path to the test as string, ie. /some/test
# data: dict of the parsed fmf metadata (ie. {'tag': ... , 'environment': ...})
# dir:  relative pathlib.Path of the test .fmf to repo root, ie. some/test
#       (may be different from name for "virtual" tests that share the same dir)
Test = collections.namedtuple("Test", ["name", "data", "dir"])


# NOTE that we split test execution into 3 scripts:
#      - "setup script" (package installs, etc.)
#      - "wrapper script" (runs test script)
#      - "test script" (exact contents of the 'test:' FMF metadata key)
#
#      this is to allow interactive test execution - the setup script
#      can run in 'bash' via stdin pipe into 'ssh', creating the wrapper
#      script somewhere on the disk, making it executable,
#
#      then the "wrapper" script can run via a separate 'ssh' execution,
#      passed by an argument to 'ssh', leaving stdin/out/err untouched,
#      allowing the user to interact with it (if run interactively)

def test_wrapper(*, test, tests_dir, test_exec):
    """
    Generate a bash script that runs a user-specified test, preparing
    a test control channel for it, and reporting its exit code.
    The script must be as "transparent" as possible, since any output
    is considered as test output and any unintended environment changes
    will impact the test itself.

    'test' is a class Test instance.

    'test_dir' is a remote directory (repository) of all the tests,
    a.k.a. FMF metadata root.

    'test_exec' is a remote path to the actual test to run.
    """
    out = "#!/bin/bash\n"

    # stdout-over-ssh is used as Test Control (see TEST_CONTROL.md),
    # so duplicate stderr to stdout, and then open a new fd pointing to the
    # original stdout
    out += "exec {orig_stdout}>&1 1>&2\n"

    # TODO: if interactive, keep original stdin, else exec 0</dev/null ,
    #       doing it here avoids unnecessary traffic (reading stdin) via ssh,
    #       even if it is fed from subprocess.DEVNULL on the runner

    if util.in_debug_mode():
        out += "set -x\n"

    # use a subshell to limit the scope of the CWD change
    out += "(\n"

    # if TMT_PLAN_ENVIRONMENT_FILE exists, export everything from it
    # (limited by the subshell, so it doesn't leak)
    out += util.dedent("""
        if [[ -f $TMT_PLAN_ENVIRONMENT_FILE ]]; then
            set -o allexport
            . "$TMT_PLAN_ENVIRONMENT_FILE"
            set +o allexport
        fi
    """) + "\n"

    # TODO: custom PATH with tmt-* style commands?

    # join the directory with all tests and nested path of our test inside it
    test_cwd = Path(tests_dir) / test.dir
    out += f"cd '{test_cwd}' || exit 1\n"

    # run the test script
    # - the '-e -o pipefail' is to mimic what full fat tmt uses
    out += (
        "ATEX_TEST_CONTROL=$orig_stdout"
        f" exec -a 'bash: atex running {test.name}'"
        f" bash -e -o pipefail '{test_exec}'\n"
    )

    # subshell end
    out += ")\n"

    # write test exitcode to test control stream
    out += "echo exitcode $? >&$orig_stdout\n"

    # always exit the wrapper with 0 if test execution was normal
    out += "exit 0\n"

    return out


def _install_packages(pkgs, extra_opts=None):
    pkgs_str = " ".join(pkgs)
    extra_opts = extra_opts or ()
    dnf = ["dnf", "-y", "--setopt=install_weak_deps=False", "install", *extra_opts]
    dnf_str = " ".join(dnf)
    return util.dedent(fr"""
        not_installed=$(rpm -q --qf '' {pkgs_str} | sed -nr 's/^package ([^ ]+) is not installed$/\1/p')
        [[ $not_installed ]] && {dnf_str} $not_installed
    """)  # noqa: E501


def test_setup(*, test, wrapper_exec, test_exec, test_yaml, **kwargs):
    """
    Generate a bash script that should prepare the remote end for test
    execution.

    The bash script itself will (among other things) generate two more bash
    scripts: a test script (contents of 'test' from FMF) and a wrapper script
    to run the test script.

    'test' is a class Test instance.

    'wrapper_exec' is the remote path where the wrapper script should be put.

    'test_exec' is the remote path where the test script should be put.

    Any 'kwargs' are passed to test_wrapper().
    """
    out = "#!/bin/bash\n"

    if util.in_debug_mode():
        out += "set -xe\n"
    else:
        out += "exec 1>/dev/null\n"
        out += "set -e\n"

    # install test dependencies
    # - only strings (package names) in require/recommend are supported
    if require := list(fmf.test_pkg_requires(test.data, "require")):
        out += _install_packages(require) + "\n"
    if recommend := list(fmf.test_pkg_requires(test.data, "recommend")):
        out += _install_packages(recommend, ("--skip-broken",)) + "\n"

    # write out test data
    out += f"cat > '{test_yaml}' <<'ATEX_SETUP_EOF'\n"
    out += yaml.dump(test.data).rstrip("\n")  # don't rely on trailing \n
    out += "\nATEX_SETUP_EOF\n"

    # make the wrapper script
    out += f"cat > '{wrapper_exec}' <<'ATEX_SETUP_EOF'\n"
    out += test_wrapper(
        test=test,
        test_exec=test_exec,
        **kwargs,
    )
    out += "ATEX_SETUP_EOF\n"
    # make the test script
    out += f"cat > '{test_exec}' <<'ATEX_SETUP_EOF'\n"
    out += test.data["test"]
    out += "\n"  # for safety, in case 'test' doesn't have a newline
    out += "ATEX_SETUP_EOF\n"
    # make both executable
    out += f"chmod 0755 '{wrapper_exec}' '{test_exec}'\n"

    out += "exit 0\n"

    return out
