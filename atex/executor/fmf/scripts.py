import importlib.resources
import uuid

import yaml

from ... import util
from .metadata import test_pkg_requires

test_wrapper = importlib.resources.files(__package__).joinpath("test-wrapper")


def make_test_setup(*, test_data, wrapper_exec, test_exec, test_yaml):
    """
    Generate a bash script that should prepare the remote end for test
    execution.

    The bash script itself will (among other things) generate two more scripts:
    a test script (contents of 'test' from FMF) and a python-based wrapper
    script to run the test script.

    - `test_data` is a dict with the parsed fmf metadata for the test.

    - `wrapper_exec` is the remote path where the wrapper script should be put.

    - `test_exec` is the remote path where the test script should be put.

    - `test_yaml` is the remote path where the test metadata YAML should be
      written.
    """
    out = "#!/bin/bash\n"
    out += "set -xe\n"

    # install test dependencies
    out += util.dedent(r"""
        if command -v dnf >/dev/null; then
            pkg_tool="dnf -y --setopt=install_weak_deps=False"
        else
            pkg_tool="yum -y"
        fi
    """) + "\n"
    # - only strings (package names) in require/recommend are supported
    if require := list(test_pkg_requires(test_data, "require")):
        pkgs_str = " ".join(require)
        out += util.dedent(fr"""
            not_installed=$(rpm -q --qf '' {pkgs_str} | sed -nr 's/^package ([^ ]+) is not installed$/\1/p')
            [[ $not_installed ]] && $pkg_tool install $not_installed
        """) + "\n"  # noqa: E501
    if recommend := list(test_pkg_requires(test_data, "recommend")):
        pkgs_str = " ".join(recommend)
        out += util.dedent(fr"""
            have_dnf5=$(command -v dnf5) || true
            skip_bad="--skip-broken${{have_dnf5:+ --skip-unavailable}}"
            not_installed=$(rpm -q --qf '' {pkgs_str} | sed -nr 's/^package ([^ ]+) is not installed$/\1/p')
            [[ $not_installed ]] && $pkg_tool install $skip_bad $not_installed
        """) + "\n"  # noqa: E501

    eof = f"EOF_{uuid.uuid4()}"

    # write out test data
    out += f"cat > '{test_yaml}' <<'{eof}'\n"
    out += yaml.dump(test_data).rstrip("\n")  # don't rely on trailing \n
    out += f"\n{eof}\n"

    # find a valid python
    out += util.dedent(r"""
        pyexec=$(command -v python3) || \
        pyexec=$(command -v python) || \
        pyexec=/usr/libexec/platform-python
        if [[ ! -x $pyexec ]]; then
            echo no executable python interpreter found >&2
            exit 1
        fi
    """) + "\n"

    # make the wrapper script
    out += f"printf '#!%s\\n' \"$pyexec\" > '{wrapper_exec}'\n"
    out += f"cat >> '{wrapper_exec}' <<'{eof}'\n"
    out += test_wrapper.read_text()
    out += f"\n{eof}\n"

    # make the test script
    out += f"cat > '{test_exec}' <<'{eof}'\n"
    out += "#!/bin/bash\n"
    # - inject TMT_PLAN_ENVIRONMENT_FILE sourcing before 'test:' content
    out += util.dedent(r"""
        if [[ -f $TMT_PLAN_ENVIRONMENT_FILE ]]; then
            set -o allexport
            . "$TMT_PLAN_ENVIRONMENT_FILE"
            set +o allexport
        fi
    """) + "\n"
    # mimic what tmt does
    out += "set -e -o pipefail\n"
    out += test_data["test"]
    out += f"\n{eof}\n"

    # make both executable
    out += f"chmod 0755 '{wrapper_exec}' '{test_exec}'\n"

    out += "exit 0\n"

    return out


def make_plan_script(*, contents, cwd):
    """
    Generate a bash script header to be prefixed to every prepare/finish script
    defined by a tmt-style plan.

    - `contents` is a string with the literal script contents from fmf metadata.

    - `cwd` is a directory path to 'cd' to on the remote system.
    """
    out = "#!/bin/bash\n"
    out += f"cd '{cwd}' || exit 1\n"
    out += util.dedent(r"""
        if [[ -f $TMT_PLAN_ENVIRONMENT_FILE ]]; then
            set -o allexport
            . "$TMT_PLAN_ENVIRONMENT_FILE"
            set +o allexport
        fi
    """) + "\n"
    out += contents
    return out
