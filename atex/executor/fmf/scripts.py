import importlib.resources
import shlex
import uuid

import yaml

from ... import util
from .metadata import test_pkg_requires

test_wrapper = importlib.resources.files(__package__).joinpath("test-wrapper")


def make_pkg_install(required=None, recommended=None):
    """
    Generate a bash script for installing RPM packages, avoiding yum/dnf
    overhead if everything is already installed.
    """
    if not required and not recommended:
        return ""
    out = util.dedent(r"""
        if command -v dnf >/dev/null; then
            pkg_tool=(dnf -q -y --setopt=install_weak_deps=False)
        else
            pkg_tool=(yum -q -y)
        fi
    """) + "\n"  # noqa: E501
    if required:
        pkgs_str = " ".join(shlex.quote(p) for p in required)
        out += util.dedent(fr"""
            exprs=$(rpm -q --qf '' --whatprovides {pkgs_str} 2>&1 | \
                sed -nr -e 's/^no package provides (.+)$/\1/p' -e 's/error: file (.+): No such file or directory$/\1/p')
            if [[ $exprs ]]; then (set -f; IFS=$'\n'; "${{pkg_tool[@]}}" install $exprs); fi
        """) + "\n"  # noqa: E501
    if recommended:
        pkgs_str = " ".join(shlex.quote(p) for p in recommended)
        out += util.dedent(fr"""
            skip_bad=(--skip-broken)
            command -v dnf5 >/dev/null && skip_bad+=(--skip-unavailable) || true
            exprs=$(rpm -q --qf '' --whatprovides {pkgs_str} 2>&1 | \
                sed -nr -e 's/^no package provides (.+)$/\1/p' -e 's/error: file (.+): No such file or directory$/\1/p')
            if [[ $exprs ]]; then (set -f; IFS=$'\n'; "${{pkg_tool[@]}}" install "${{skip_bad[@]}}" $exprs); fi
        """) + "\n"  # noqa: E501
    return out


def make_test_setup(*, test_data, test_dir, wrapper_exec, test_exec, test_yaml, bin_dir):
    """
    Generate a bash script that should prepare the remote end for test
    execution.

    The bash script itself will (among other things) generate two more scripts:
    a test script (contents of 'test' from FMF) and a python-based wrapper
    script to run the test script.

    - `test_data` is a dict with the parsed fmf metadata for the test.

    - `test_dir` is a Path of a remote directory for wrapper and test
      executables, and any additional test-related files.

      It is deleted and re-created for each test.

    - `wrapper_exec` is a file, inside `test_dir`, of the test wrapper.

    - `test_exec` is a file, inside `test_dir`, holding the test script
      contents.

    - `test_yaml` is a file, inside `test_dir`, into which the test YAML data
      is to be written.

    - `bin_dir` is a Path of a remote directory to be prepended to PATH.
    """
    test_dir_path = shlex.quote(str(test_dir))
    wrapper_exec_path = shlex.quote(str(test_dir / wrapper_exec))
    test_exec_path = shlex.quote(str(test_dir / test_exec))
    test_yaml_path = shlex.quote(str(test_dir / test_yaml))
    bin_dir_path = shlex.quote(str(bin_dir))

    out = "#!/bin/bash\n"
    # send set -x to stdout (subprocess_log)
    #out += "exec {xtrace_fd}>&1\n"
    #out += "BASH_XTRACEFD=$xtrace_fd\n"
    out += "set -xe\n"

    # re-create test_dir
    out += f"rm -rf {test_dir_path}\n"
    out += f"mkdir {test_dir_path}\n"

    # install test dependencies
    out += make_pkg_install(
        required=tuple(test_pkg_requires(test_data, "require")),
        recommended=tuple(test_pkg_requires(test_data, "recommend")),
    )

    eof = f"EOF_{uuid.uuid4()}"

    # write out test data
    out += f"cat > {test_yaml_path} <<'{eof}'\n"
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
    out += f"printf '#!%s\\n' \"$pyexec\" > {wrapper_exec_path}\n"
    out += f"cat >> {wrapper_exec_path} <<'{eof}'\n"
    out += test_wrapper.read_text()
    out += f"\n{eof}\n"

    # make the test script
    out += f"cat > {test_exec_path} <<'{eof}'\n"
    out += "#!/bin/bash\n"
    # - inject TMT_PLAN_ENVIRONMENT_FILE sourcing before 'test:' content
    out += util.dedent(r"""
        if [[ -f $TMT_PLAN_ENVIRONMENT_FILE ]]; then
            set -o allexport
            . "$TMT_PLAN_ENVIRONMENT_FILE"
            set +o allexport
        fi
    """) + "\n"
    # some users (like BeakerlibExecutor) use additional helpers by creating
    # a bin/ dir in the remote work_dir - if it exists, add it to PATH
    out += util.dedent(fr"""
        if [[ -d {bin_dir_path} ]]; then
            export PATH={bin_dir_path}:"$PATH"
        fi
    """) + "\n"
    # mimic what tmt does
    out += "set -e -o pipefail\n"
    out += test_data["test"]
    out += f"\n{eof}\n"

    # make both executable
    out += f"chmod 0755 {wrapper_exec_path} {test_exec_path}\n"

    out += "exit 0\n"

    return out


def make_plan_script(*, contents, cwd):
    """
    Generate a bash script header to be prefixed to every prepare/finish script
    defined by a tmt-style plan.

    - `contents` is a string with the literal script contents from fmf metadata.

    - `cwd` is a directory path to 'cd' to on the remote system.
    """
    cwd = shlex.quote(str(cwd))
    return "\n".join((
        "#!/bin/bash",
        f"cd {cwd} || exit 1",
        "if [[ -f $TMT_PLAN_ENVIRONMENT_FILE ]]; then",
        "    set -o allexport",
        '    . "$TMT_PLAN_ENVIRONMENT_FILE"',
        "    set +o allexport",
        "fi",
        "set -e -o pipefail",
        contents,
    ))
