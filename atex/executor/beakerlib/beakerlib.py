import json
import shlex
import subprocess
import uuid

from ... import util
from ..fmf import FMFExecutor
from ..fmf.scripts import make_pkg_install

get_logger = util.get_loggers("atex.executor.beakerlib")


class BeakerlibExecutor(FMFExecutor):
    """
    - `connection` is a connected class Connection instance.

    - `fmf_tests` is a class FMFTests instance with (discovered) tests.

    - `env` is a dict of extra environment variables to pass to the
      plan prepare/finish scripts and to all tests.
    """

    def __init__(self, connection, fmf_tests, *, env=None):
        super().__init__(connection, fmf_tests, env=env)
        self.logger = get_logger()

    def _make_start_script(self):
        report_result = util.dedent(r"""
        #!/bin/bash
        set -e
        LC_ALL=C  # make ${#foo} count real bytes
        function report {
            local what=$1
            printf 'result %d\n%s' "${#what}" "$what" >&$ATEX_TEST_CONTROL
        }
        test_name=$1 status=$2 log=$3 score=$4
        # atex/tmt use lowercase status/result names
        status=${status,,}  # to lowercase
        # if log file was specified, create a files[] entry for it
        # - Beakerlib uses a random tmp name, and we could hardcode it to
        #   'log.txt', but then multiple rlPhaseStartTest would conflict
        #   on identical subtest name (Test) + file name (log.txt)
        if [[ -f $log ]]; then
            size=$(stat -L -c '%s' "$log")
            log_base=${log##*/}
            fname=${log_base//[^a-zA-Z0-9 _.,:\-+=%@\/]/}  # sanitize
            report "{
                \"status\": \"$status\",
                \"name\": \"$test_name\",
                \"files\": [{\"name\": \"$fname.txt\", \"length\": $size}]
            }"
            # in case something appends to it mid-flight
            head -c "$size" "$log" >&$ATEX_TEST_CONTROL
        else
            report "{
                \"status\": \"$status\",
                \"name\": \"$test_name\"
            }"
        fi
        """)

        file_submit = util.dedent(r"""
        #!/bin/bash
        set -e
        LC_ALL=C  # make ${#foo} count real bytes
        function report {
            local what=$1
            printf 'result %d\n%s' "${#what}" "$what" >&$ATEX_TEST_CONTROL
        }
        ignored_l_arg=$1 log=$2
        if [[ -f $log ]]; then
            size=$(stat -L -c '%s' "$log")
            log_base=${log##*/}
            fname=${log_base//[^a-zA-Z0-9 _.,:\-+=%@\/]/}  # sanitize
            report "{
                \"partial\": true,
                \"files\": [{\"name\": \"$fname\", \"length\": $size}]
            }"
            # in case something appends to it mid-flight
            head -c "$size" "$log" >&$ATEX_TEST_CONTROL
        fi
        """)

        reboot = util.dedent(r"""
        #!/bin/bash
        # if sshd is running, stop it to prevent pre-reboot reconnect
        if systemctl is-active --quiet sshd.service; then
            systemctl stop sshd.service
        fi
        # disconnect the control, send noop while waiting for EPIPE
        echo disconnect >&$ATEX_TEST_CONTROL
        while :; do
            echo noop >&$ATEX_TEST_CONTROL || break
            sleep 0.1
        done
        sync
        reboot
        sleep inf
        """)

        # create helper wrappers in PATH
        # (exported by make_test_setup() if it finds a bin directory)
        quoted_bindir = shlex.quote(str(self.work_dir / "bin"))
        script = (
            "set -xe",
            f"mkdir {quoted_bindir}",
            # for rlReport (also called by rlPhaseEnd)
            f"cat > {quoted_bindir}/atex-report-result <<'EOF'",
            report_result,
            "EOF",
            f"chmod +x {quoted_bindir}/atex-report-result",
            # for rlFileSubmit
            f"cat > {quoted_bindir}/atex-file-submit <<'EOF'",
            file_submit,
            "EOF",
            f"chmod +x {quoted_bindir}/atex-file-submit",
            # manually used by tests, via the extra aliases
            f"cat > {quoted_bindir}/atex-reboot <<'EOF'",
            reboot,
            "EOF",
            f"chmod +x {quoted_bindir}/atex-reboot",
            f"ln -s atex-reboot {quoted_bindir}/tmt-reboot",
            f"ln -s atex-reboot {quoted_bindir}/rhts-reboot",
        )
        return (
            "\n".join(script) +
            "\n" +
            # also make sure beakerlib is installed
            make_pkg_install(
                required=("beakerlib",),
                recommended=("beakerlib-redhat",),
            )
        )

    def start(self):
        super().start()
        self.conn.cmd(
            ("bash",),
            func=util.subprocess_log,
            logger=self.logger,
            input=self._make_start_script(),
            stderr=subprocess.STDOUT,
            check=True,
        )

    def run_test(self, *args, env=None):
        # create BEAKERLIB_DIR, symlink metadata.yaml to it
        quoted_dir = shlex.quote(str(self.work_dir / "beakerlib"))
        # prepare metadata.yaml for rlImport --all
        script = util.dedent(fr"""
            rm -rf {quoted_dir}
            mkdir {quoted_dir}

            ln -s ../test/metadata.yaml {quoted_dir}/metadata.yaml
        """) + "\n"
        self.conn.cmd(
            ("bash",),
            func=util.subprocess_log,
            logger=self.logger,
            input=script,
            stderr=subprocess.STDOUT,
            check=True,
        )

        beakerlib_env = {
            # these are created in _make_start_script() above
            "BEAKERLIB_COMMAND_REPORT_RESULT": "atex-report-result",
            "BEAKERLIB_COMMAND_SUBMIT_LOG": "atex-file-submit",
            "BEAKERLIB_DIR": str(self.work_dir / "beakerlib"),
            "TESTID": str(uuid.uuid4()),
            "BEAKERLIB_JOURNAL": str(0),  # XML journal is useless
        }
        env = beakerlib_env if env is None else env | beakerlib_env

        return super().run_test(*args, env=env)

    def _report_fallback_result(self, reporter, exit_code, exception, test_name):
        if reporter.nameless_result_seen or exception:
            return super()._report_fallback_result(reporter, exit_code, exception, test_name)

        # override exit code based fallback with results-based one,
        # because beakerlib tests always exit with 0 (unless aborted),
        # so we do need to actually parse the results
        #
        # - partial results first
        seen_fail = any(
            # warn also, because Beakerlib reports it on Setup/Cleanup failure
            result.get("status") in ("fail", "warn", "error")
            for result in reporter.partial.values()
        )
        # - on-disk results second
        if not seen_fail:
            with open(reporter.results_file) as f:
                for line in f:
                    result = json.loads(line)
                    if result.get("status") in ("fail", "warn", "error"):
                        seen_fail = True
                        break

        # simulated exit code for the parent _report_fallback_result()
        exit_code = 1 if seen_fail else 0
        return super()._report_fallback_result(reporter, exit_code, exception, test_name)
