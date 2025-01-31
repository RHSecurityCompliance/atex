import os
import re
import time
import select
import threading
import contextlib
import subprocess

from .. import util
from . import testcontrol, scripts, fmf


class Duration:
    """
    A helper for parsing, keeping and manipulating test run time based on
    FMF-defined 'duration' attribute.
    """

    def __init__(self, fmf_duration):
        """
        'fmf_duration' is the string specified as 'duration' in FMF metadata.
        """
        duration = self._fmf_to_seconds(fmf_duration)
        self.end = time.monotonic() + duration
        # keep track of only the first 'save' and the last 'restore',
        # ignore any nested ones (as tracked by '_count')
        self.saved = None
        self.saved_count = 0

    @staticmethod
    def _fmf_to_seconds(string):
        match = re.fullmatch(r"([0-9]+)([a-z]*)", string)
        if not match:
            raise RuntimeError(f"'duration' has invalid format: {string}")
        length, unit = match.groups()
        if unit == "m":
            return int(length)*60
        elif unit == "h":
            return int(length)*60*60
        elif unit == "d":
            return int(length)*60*60*24
        else:
            return int(length)

    def set(self, to):
        self.end = time.monotonic() + self._fmf_to_seconds(to)

    def increment(self, by):
        self.end += self._fmf_to_seconds(by)

    def decrement(self, by):
        self.end -= self._fmf_to_seconds(by)

    def save(self):
        if self.saved_count == 0:
            self.saved = self.end - time.monotonic()
        self.saved_count += 1

    def restore(self):
        if self.saved_count > 1:
            self.saved_count -= 1
        elif self.saved_count == 1:
            self.end = time.monotonic() + self.saved
            self.saved_count = 0
            self.saved = None

    def out_of_time(self):
        return time.monotonic() > self.end


# SETUP global:
# - create CSVAggregator instance on some destination dir

# SETUP of new Provisioner instance:
# - with SSHConn
#   - rsync test repo to some tmpdir on the remote
#   - install packages from plan
#   - create TMT_PLAN_ENVIRONMENT_FILE and export it to plan setup scripts
#   - run plan setup scripts

# SETUP + CLEANUP for one test
# - create Executor instance
#   - pass TMT_PLAN_ENVIRONMENT_FILE to it
#     - probably as general "environment variables" input,
#       could be reused in the future for ie. TMT_PLAN_NAME or so
#     - pass env from CLI -e switches
#   - pass disconnected SSHConn to it
#   - pass one FMFTest namedtuple to it (test to run)
#   - pass test repo location on the remote host
#   - pass CSVAggregator instance to it, so it can write results/logs
# - with SSHConn
#   - create wrapper script on the remote
#   - run wrapper script, redirecting stderr to tmpfile via CSVAggregator
#   - poll() / select() over test stdout, parse TEST_CONTROL protocol
#   - on 0.1sec poll timeout
#     - check if SSHConn master is alive, re-connect if not
#     - check test duration against fmf-defined (control-adjusted) duration
#   - ...
# - make Executor return some complex status
#   - whether testing was destructive (just leave SSHConn disconnected?)


class TestAbortedError(Exception):
    """
    Raised when an infrastructure-related issue happened while running a test.
    """
    pass


# TODO: automatic reporting of all partial results that were not finished
class Executor:
    """
    Logic for running tests on a remote system and processing results
    and uploaded files by those tests.
    """

    def __init__(self, remote, aggregator, remote_dir=None, env=None):
        """
        'remote' is a reserved class Remote instance, with an active connection.

        'aggregator' is an instance of a ResultAggregator all the results
        and uploaded files will be written to.

        'remote_dir' is a path on the remote for storing tests and other
        metadata. If unspecified, a tmpdir is created and used instead.

        'env' is a dict of extra environment variables to pass to the
        plan prepare scripts and tests.
        """
        self.lock = threading.RLock()
        self.remote = remote
        self.aggregator = aggregator
        self.cancelled = False
        self.remote_dir = remote_dir
        self.plan_env = env.copy() if env else {}

    def _get_remote_dir(self):
        # TODO: do not mktemp here, do it in the parent, have remote_dir be mandatory,
        #       renamed to 'tests_dir' (just the test repo), cleaned up by external logic
        #       - handle custom metadata remote dir in run_test() and clean it up there
        #         (for TMT_PLAN_ENVIRONMENT_FILE, wrapper, etc.)
        if not self.remote_dir:
            self.remote_dir = self.remote.cmd(
                ("mktemp", "-d", "-p", "/var/tmp"),
                func=util.subprocess_output,
            )
        return self.remote_dir

    # TODO: do not do this in Executor
    def upload_tests(self, tests_dir):
        """
        Upload a directory of all tests from a local 'tests_dir' path to
        a temporary directory on the remote host.
        """
        remote_dir = self._get_remote_dir()
        self.remote.rsync(
            "-rv", "--delete", "--exclude=.git/",
            f"{tests_dir}/",
            f"remote:{remote_dir}/tests",
        )

    def setup_plan(self, fmf_tests):
        """
        Install packages and run scripts, presumably extracted from a TMT plan
        provided as 'fmf_tests', an initialized FMFTests instance.

        Also prepare additional environment for tests, ie. create and export
        a path to TMT_PLAN_ENVIRONMENT_FILE.
        """
        # install packages from the plan
        if fmf_tests.prepare_pkgs:
            self.remote.cmd(
                (
                    "dnf", "-y", "--setopt=install_weak_deps=False",
                    "install", *fmf_tests.prepare_pkgs,
                ),
                check=True,
            )

        # create TMT_PLAN_ENVIRONMENT_FILE
        self.plan_env.update(fmf_tests.plan_env)
        env_file = f"{self._get_remote_dir()}/TMT_PLAN_ENVIRONMENT_FILE"
        self.remote.cmd(("truncate", "-s", "0", env_file), check=True)
        self.plan_env["TMT_PLAN_ENVIRONMENT_FILE"] = env_file

        # run prepare scripts
        env_args = (f"{k}={v}" for k, v in self.plan_env.items())
        for script in fmf_tests.prepare_scripts:
            self.remote.cmd(
                ("env", *env_args, "bash"),
                input=script,
                text=True,
                check=True,
            )

    def run_test(self, fmf_test, env=None):
        """
        Run one test on the remote system.

        'fmf_test' is a FMFTest namedtuple with the test to run.

        'env' is a dict of extra environment variables to pass to the test.
        """
        env_vars = self.plan_env.copy()
        for item in fmf.listlike(fmf_test.data, "environment"):
            env_vars.update(item)
        env_vars["ATEX_TEST_NAME"] = fmf_test.name
        env_vars["TMT_TEST_NAME"] = fmf_test.name
        if env:
            env_vars.update(env)
        env_args = (f"{k}={v}" for k, v in env_vars.items())

        # run a setup script, preparing wrapper + test scripts
        remote_dir = self._get_remote_dir()
        setup_script = scripts.test_setup(
            test=fmf_test,
            tests_dir=f"{remote_dir}/tests",
            wrapper_exec=f"{remote_dir}/wrapper.sh",
            test_exec=f"{remote_dir}/test.sh",
            debug=True,
        )
        self.remote.cmd(("bash",), input=setup_script, text=True, check=True)

        with contextlib.ExitStack() as stack:
            testout_fd = stack.enter_context(self.aggregator.open_tmpfile())

            duration = Duration(fmf_test.data.get("duration", "5m"))

            test_proc = None
            control_fd = None
            stack.callback(lambda: os.close(control_fd) if control_fd else None)

            def abort(msg):
                if test_proc:
                    test_proc.kill()
                    test_proc.wait()
                self.remote.release()
                raise TestAbortedError(msg) from None

            try:
                # TODO: probably enum
                state = "starting_test"
                while not duration.out_of_time():
                    with self.lock:
                        if self.cancelled:
                            abort("cancel requested")
                            return

                    if state == "starting_test":
                        control_fd, pipe_w = os.pipe()
                        os.set_blocking(control_fd, False)
                        control = testcontrol.TestControl(
                            control_fd=control_fd,
                            aggregator=self.aggregator,
                            duration=duration,
                            testout_fd=testout_fd,
                        )
                        # run the test in the background, letting it log output directly to
                        # an opened file (we don't handle it, cmd client sends it to kernel)
                        test_proc = self.remote.cmd(
                            ("env", *env_args, f"{remote_dir}/wrapper.sh"),
                            stdout=pipe_w,
                            stderr=testout_fd,
                            func=util.subprocess_Popen,
                        )
                        os.close(pipe_w)
                        state = "reading_control"

                    elif state == "reading_control":
                        rlist, _, xlist = select.select((control_fd,), (), (control_fd,), 0.1)
                        if xlist:
                            abort(f"got exceptional condition on control_fd {control_fd}")
                        elif rlist:
                            control.process()
                            if control.eof:
                                os.close(control_fd)
                                control_fd = None
                                state = "waiting_for_exit"

                    elif state == "waiting_for_exit":
                        # control stream is EOF and it has nothing for us to read,
                        # we're now just waiting for proc to cleanly terminate
                        try:
                            code = test_proc.wait(0.1)
                            if code == 0:
                                # wrapper exited cleanly, testing is done
                                break
                            else:
                                # unexpected error happened (crash, disconnect, etc.)
                                self.remote.disconnect()
                                # if reconnect was requested, do so, otherwise abort
                                if control.reconnect:
                                    state = "reconnecting"
                                    if control.reconnect != "always":
                                        control.reconnect = None
                                else:
                                    abort(f"test wrapper unexpectedly exited with {code}")
                            test_proc = None
                        except subprocess.TimeoutExpired:
                            pass

                    elif state == "reconnecting":
                        try:
                            self.remote.connect(block=False)
                            state = "reading_control"
                        except BlockingIOError:
                            pass

                    else:
                        raise AssertionError("reached unexpected state")

                else:
                    abort("test duration timeout reached")

                # testing successful, do post-testing tasks

                # test wrapper hasn't provided exitcode
                if control.exit_code is None:
                    abort("exitcode not reported, wrapper bug?")

                # partial results that were never reported
                if control.partial_results:
                    control.result_seen = True  # partial result is also a result
                    for result in control.partial_results.values():
                        self.aggregator.report(result)

                # test hasn't reported a single result, add an automatic one
                # as specified in RESULTS.md
                # {"status": "pass", "name": "/some/test", "testout": "output.txt"}
                if not control.result_seen:
                    self.aggregator.link_tmpfile_to(fmf_test.name, "output.txt", testout_fd)
                    self.aggregator.report({
                        "status": "pass" if control.exit_code == 0 else "fail",
                        "name": fmf_test.name,
                        "testout": "output.txt",
                    })

            except Exception:
                # if the test hasn't reported a single result, but still
                # managed to break something, provide at least the default log
                # for manual investigation - otherwise test output disappears
                if not control.result_seen:
                    self.aggregator.link_tmpfile_to(fmf_test.name, "output.txt", testout_fd)
                raise

    def cancel(self):
        with self.lock:
            self.cancelled = True
