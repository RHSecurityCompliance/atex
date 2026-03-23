import contextlib
import enum
import os
import select
import subprocess
import threading
import time
from pathlib import Path

from ... import util
from ...connection.ssh import ManagedSSHConnection
from .. import Executor, ExecutorError
from . import scripts
from .duration import Duration
from .metadata import listlike
from .reporter import Reporter
from .testcontrol import BadReportJSONError, TestControl

get_logger = util.get_loggers("atex.executor.fmf")


class TestSetupError(ExecutorError):
    """
    Raised when the preparation for test execution (ie. pkg install) fails.
    """


class TestAbortedError(ExecutorError):
    """
    Raised when an infrastructure-related issue happened while running a test.
    """


class FMFExecutor(Executor):
    def __init__(self, connection, *, fmf_tests, env=None):
        """
        Positional arguments are the same as class Executor.

        - `fmf_tests` is a class FMFTests instance with (discovered) tests.

        - `env` is a dict of extra environment variables to pass to the
          plan prepare/finish scripts and to all tests.
        """
        self.lock = threading.RLock()
        self.logger = get_logger()

        self.fmf_tests = fmf_tests
        self.conn = connection
        self.env = env or {}
        self.work_dir = None
        self.tests_dir = None
        self.plan_env_file = None
        self.cancelled = False

    def start(self):
        self.logger.debug(f"starting: {self}")

        tmp_dir = self.conn.cmd(
            # /var is not cleaned up by bootc, /var/tmp is
            ("mktemp", "-d", "-p", "/var", "atex-XXXXXXXXXX"),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        tmp_dir = Path(tmp_dir.stdout.rstrip("\n"))
        self.work_dir = tmp_dir
        self.tests_dir = tmp_dir / "tests"
        self.plan_env_file = tmp_dir / "plan_env"

        # create / truncate the TMT_PLAN_ENVIRONMENT_FILE
        self.conn.cmd(("truncate", "-s", "0", self.plan_env_file), check=True)

        # upload tests to the remote
        self.conn.rsync(
            "-r", "--delete", "--exclude=.git/",
            f"{self.fmf_tests.root}/",
            f"remote:{self.tests_dir}",
            func=util.subprocess_log,
            logger=self.logger,
        )

        # install packages from the plan on the remote
        if self.fmf_tests.prepare_pkgs:
            self.conn.cmd(
                (
                    "dnf", "-y", "--setopt=install_weak_deps=False",
                    "install", *self.fmf_tests.prepare_pkgs,
                ),
                func=util.subprocess_log,
                logger=self.logger,
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                check=True,
            )

        # run 'prepare' scripts from the plan on the remote
        if scripts := self.fmf_tests.prepare_scripts:
            self._run_prepare_scripts(scripts)

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        # run 'finish' scripts from the plan on the remote
        if scripts := self.fmf_tests.finish_scripts:
            self._run_prepare_scripts(scripts)

        if self.work_dir:
            self.conn.cmd(("rm", "-rf", self.work_dir), check=True)

        self.work_dir = None
        self.tests_dir = None
        self.plan_env_file = None

    def cancel(self):
        with self.lock:
            self.cancelled = True

    def _run_prepare_scripts(self, scripts):
        # make envionment for 'prepare' scripts
        env = {
            **self.fmf_tests.plan_env,
            **self.env,
            "TMT_PLAN_ENVIRONMENT_FILE": self.plan_env_file,
        }
        env_args = tuple(f"{k}={v}" for k, v in env.items())
        # run the scripts
        for script in scripts:
            self.conn.cmd(
                ("env", "-C", self.tests_dir, *env_args, "bash"),
                func=util.subprocess_log,
                logger=self.logger,
                input=script,
                stderr=subprocess.STDOUT,
                check=True,
            )

    class State(enum.Enum):
        STARTING_TEST = enum.auto()
        READING_CONTROL = enum.auto()
        WAITING_FOR_EXIT = enum.auto()
        RECONNECTING = enum.auto()

    def run_test(self, test_name, artifacts, *, env=None):
        """
        Positional arguments are the same as class Executor.

        - `env` is a dict of extra environment variables to pass to the test.
        """
        self.logger.info(f"'{test_name}': running, {artifacts=}")

        artifacts = Path(artifacts)
        test_data = self.fmf_tests.tests[test_name]

        # start with fmf-plan-defined environment
        env_vars = {
            **self.fmf_tests.plan_env,
            "TMT_PLAN_ENVIRONMENT_FILE": self.plan_env_file,
            "TMT_TEST_NAME": test_name,
            "TMT_TEST_METADATA": f"{self.work_dir}/metadata.yaml",
        }
        # append fmf-test-defined environment into it
        for item in listlike(test_data, "environment"):
            env_vars.update(item)
        # append the Executor-wide environment passed to __init__()
        env_vars.update(self.env)
        # append variables given to this function call
        if env:
            env_vars.update(env)

        self.logger.debug(f"'{test_name}': {env_vars=}")

        with contextlib.ExitStack() as stack:
            reporter = stack.enter_context(Reporter(artifacts, "results", "files"))
            duration = Duration(test_data.get("duration", "5m"))
            control = TestControl(reporter=reporter, duration=duration, logger=self.logger)

            # run a setup script, preparing wrapper + test scripts
            setup_script = scripts.test_setup(
                test=scripts.Test(test_name, test_data, self.fmf_tests.test_dirs[test_name]),
                tests_dir=self.tests_dir,
                wrapper_exec=f"{self.work_dir}/wrapper.sh",
                test_exec=f"{self.work_dir}/test.sh",
                test_yaml=f"{self.work_dir}/metadata.yaml",
            )
            setup_proc = self.conn.cmd(
                ("bash",),
                input=setup_script,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if setup_proc.returncode != 0:
                reporter.report({
                    "status": "infra",
                    "note": f"TestSetupError({setup_proc.stdout})",
                })
                raise TestSetupError(setup_proc.stdout)

            test_proc = None
            control_fd = None
            stack.callback(lambda: os.close(control_fd) if control_fd else None)

            reconnects = 0

            def abort(msg):
                if test_proc:
                    test_proc.kill()
                    test_proc.wait()
                raise TestAbortedError(msg) from None

            exception = None

            try:
                state = self.State.STARTING_TEST
                self.logger.debug(f"'{test_name}': {state.name}")

                while not duration.out_of_time():
                    with self.lock:
                        if self.cancelled:
                            abort("cancel requested")

                    if state == self.State.STARTING_TEST:
                        # reconnect/reboot count (for compatibility)
                        env_vars["TMT_REBOOT_COUNT"] = str(reconnects)
                        env_vars["TMT_TEST_RESTART_COUNT"] = str(reconnects)
                        env_args = (f"{k}={v}" for k, v in env_vars.items())
                        try:
                            # open a pipe for test control
                            control_fd, pipe_w = os.pipe()
                            os.set_blocking(control_fd, False)
                            control.reassign(control_fd)
                            # run the test in the background, letting it log output directly to
                            # an opened file (we don't handle it, cmd client sends it to kernel)
                            with reporter.open_testout() as testout_fd:
                                test_proc = self.conn.cmd(
                                    ("env", *env_args, f"{self.work_dir}/wrapper.sh"),
                                    stdin=subprocess.DEVNULL,
                                    stdout=pipe_w,
                                    stderr=testout_fd,
                                    func=subprocess.Popen,
                                    bufsize=0,  # we handle fds ourselves
                                )
                        finally:
                            os.close(pipe_w)
                        state = self.State.READING_CONTROL
                        self.logger.debug(f"'{test_name}': {state.name}")

                    elif state == self.State.READING_CONTROL:
                        rlist, _, xlist = select.select((control_fd,), (), (control_fd,), 0.1)
                        if xlist:
                            abort(f"got exceptional condition on control_fd {control_fd}")
                        elif rlist:
                            control.process()
                            if control.eof or control.disconnect_received:
                                os.close(control_fd)
                                control_fd = None
                                state = self.State.WAITING_FOR_EXIT
                                self.logger.debug(f"'{test_name}': {state.name}")

                    elif state == self.State.WAITING_FOR_EXIT:
                        # control stream is EOF and it has nothing for us to read,
                        # we're now just waiting for proc to cleanly terminate
                        try:
                            code = test_proc.wait(0.1)
                            if code == 0:
                                # wrapper exited cleanly, testing is done
                                break
                            else:
                                # unexpected error happened (crash, disconnect, etc.)
                                self.conn.disconnect()
                                # if there was a test control parser running
                                if control.in_progress:
                                    abort(
                                        f"{str(control.in_progress)} was running while test "
                                        f"wrapper unexpectedly exited with {code}",
                                    )
                                # if test control disconnect was intentional, try to reconnect
                                if control.disconnect_received:
                                    state = self.State.RECONNECTING
                                    self.logger.debug(f"'{test_name}': {state.name}")
                                    control.disconnect_received = False
                                else:
                                    abort(
                                        f"test wrapper unexpectedly exited with {code} and "
                                        "disconnect was not sent via test control",
                                    )
                            test_proc = None
                        except subprocess.TimeoutExpired:
                            pass

                    elif state == self.State.RECONNECTING:
                        try:
                            if isinstance(self.conn, ManagedSSHConnection):
                                self.conn.connect(block=False)
                            else:
                                self.conn.connect()
                            reconnects += 1
                            state = self.State.STARTING_TEST
                            self.logger.debug(f"'{test_name}': {state.name}")
                        except BlockingIOError:
                            # avoid 100% CPU spinning if the connection it too slow
                            # to come up (ie. ssh ControlMaster socket file not created)
                            time.sleep(0.5)
                        except ConnectionError:
                            # can happen when ie. ssh is connecting over a LocalForward port,
                            # causing 'read: Connection reset by peer' instead of timeout
                            # - just retry again after a short delay
                            time.sleep(0.5)

                    else:
                        raise AssertionError("reached unexpected state")

                else:
                    abort("test duration timeout reached")

                # testing successful

                # test wrapper hasn't provided exitcode
                if control.exit_code is None:
                    abort("exitcode not reported, wrapper bug?")

                return control.exit_code

            except Exception as e:
                exception = e
                raise

            finally:
                # partial results that were never reported
                if control.partial_results:
                    for result in control.partial_results.values():
                        name = result.get("name")
                        if not name:
                            # partial result is also a result
                            control.nameless_result_seen = True
                        if testout := result.get("testout"):
                            try:
                                reporter.link_testout(testout, name)
                            except FileExistsError:
                                raise BadReportJSONError(
                                    f"file '{testout}' already exists",
                                ) from None
                        reporter.report(result)

                # if an unexpected infrastructure-related exception happened
                if exception:
                    try:
                        reporter.link_testout("output.txt")
                    except FileExistsError:
                        pass
                    reporter.report({
                        "status": "infra",
                        "note": f"{type(exception).__name__}({exception})",
                        "testout": "output.txt",
                    })

                # if the test hasn't reported a result for itself
                elif not control.nameless_result_seen:
                    try:
                        reporter.link_testout("output.txt")
                    except FileExistsError:
                        pass
                    self.logger.debug(f"'{test_name}': reporting fallback result")
                    reporter.report({
                        "status": "pass" if control.exit_code == 0 else "fail",
                        "testout": "output.txt",
                    })

    def __str__(self):
        class_name = self.__class__.__name__
        conn_class = type(self.conn)
        fmf_root = str(self.fmf_tests.root)
        return f"{class_name}({conn_class}, {fmf_root})"
