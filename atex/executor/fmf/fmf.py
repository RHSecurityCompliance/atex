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
from .duration import Duration
from .metadata import listlike
from .reporter import Reporter
from .scripts import make_pkg_install, make_plan_script, make_test_setup
from .testcontrol import TestControl

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
    """
    - `connection` is a connected class Connection instance.

    - `fmf_tests` is a class FMFTests instance with (discovered) tests.

    - `env` is a dict of extra environment variables to pass to the
      plan prepare/finish scripts and to all tests.
    """

    def __init__(self, connection, fmf_tests, *, env=None):
        self.lock = threading.RLock()
        self.logger = get_logger()

        self.fmf_tests = fmf_tests
        self.conn = connection
        self.env = env or {}
        self.work_dir = None
        self.cancelled = False

    def start(self):
        self.logger.debug(f"starting: {self}")

        proc = self.conn.cmd(
            # /var is not cleaned up by bootc, /var/tmp is
            ("mktemp", "-d", "-p", "/var", "atex-XXXXXXXXXX"),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        self.work_dir = Path(proc.stdout.rstrip("\n"))

        # create / truncate the TMT_PLAN_ENVIRONMENT_FILE
        self.conn.cmd(("truncate", "-s", "0", self.work_dir / "plan_env"), check=True)

        # upload tests to the remote
        self.conn.rsync(
            "-r", "--delete", "--exclude=.git/",
            f"{self.fmf_tests.root}/",
            f"remote:{self.work_dir}/tests",
            func=util.subprocess_log,
            logger=self.logger,
        )
        self.env["TMT_TREE"] = str(self.work_dir / "tests")

        # run 'prepare' scripts from the plan on the remote
        self._run_plan_prepare_finish("prepare")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        self._run_plan_prepare_finish("finish")

        if self.work_dir:
            self.conn.cmd(("rm", "-rf", self.work_dir), check=True)

        self.work_dir = None

    def cancel(self):
        self.cancelled = True

    def _run_plan_prepare_finish(self, plugin_type):
        # make environment for 'prepare' / 'finish' scripts
        env = {
            **self.fmf_tests.plan.get("environment", {}),
            **self.env,
            "TMT_PLAN_ENVIRONMENT_FILE": str(self.work_dir / "plan_env"),
        }
        env_args = tuple(f"{k}={v}" for k, v in env.items())

        for item in listlike(self.fmf_tests.plan, plugin_type):
            how = item.get("how")
            if how == "install":
                if packages := listlike(item, "package"):
                    self.conn.cmd(
                        ("bash",),
                        func=util.subprocess_log,
                        logger=self.logger,
                        input=make_pkg_install(required=packages),
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
            elif how == "shell":
                for script in listlike(item, "script"):
                    full_script = make_plan_script(
                        contents=script,
                        cwd=self.work_dir / "tests",
                    )
                    self.conn.cmd(
                        ("env", *env_args, "bash"),
                        func=util.subprocess_log,
                        logger=self.logger,
                        input=full_script,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )

    def _report_fallback_result(self, reporter, exit_code, exception, test_name):
        """
        Report a fallback result for a test that hasn't reported a full
        name-less result for itself. See RESULTS.md.

        If the test reported a partial:true nameless result, merge some of
        the fallback logic into it, allowing tests to upload logs on-the-fly
        without setting a name/status and thus using this fallback logic.

        Also, this always reports any fallback result as partial:true, letting
        the Reporter's stop() to finish them - this is to simplify our code and
        make it work for both non-partial and partial cases.
        """
        # if the test reported a full (non-partial) result for itself
        if reporter.nameless_result_seen:
            return

        # get a nameless partial:true result if it exists
        partial = reporter.partial.get(None)

        # avoid adding testout to partial results that already use output.txt
        if (
            partial is None or
            ("testout" not in partial and "output.txt" not in partial.get("files", ()))
        ):
            testout_addition = {"testout": "output.txt"}
        else:
            testout_addition = {}

        # if an unexpected infrastructure-related exception happened, override
        # any partial:true status and note since we likely have higher priority
        # - note that TestAbortedError is already raised by run_test(), this is
        #   just a nice-to-have convenience
        if exception:
            self.logger.debug(f"'{test_name}': reporting fallback exception")
            reporter.report({
                "status": "infra",
                "note": f"{type(exception).__name__}({exception})",
                "partial": True,
                **testout_addition,
            })
            return

        # if the partial result has at least status, prefer it
        if partial and "status" in partial:
            status_addition = {"status": partial["status"]}
        else:
            status_addition = {"status": "pass" if exit_code == 0 else "fail"}

        # regular fallback result - use pass/fail based on exitcode
        self.logger.debug(f"'{test_name}': reporting fallback result")
        reporter.report({
            **status_addition,
            "partial": True,
            **testout_addition,
        })

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

        test_data = self.fmf_tests.data[test_name]
        test_fmf_dir = self.work_dir / "tests" / self.fmf_tests.dirs[test_name]

        # start with fmf-plan-defined environment
        env_vars = {
            **self.fmf_tests.plan.get("environment", {}),
            "TMT_PLAN_ENVIRONMENT_FILE": str(self.work_dir / "plan_env"),
            "TMT_TEST_NAME": test_name,
            "TMT_TEST_METADATA": str(self.work_dir / "test" / "metadata.yaml"),
        }
        # append fmf-test-defined environment into it
        for item in listlike(test_data, "environment"):
            env_vars.update(item)
        # append the Executor-wide environment passed to __init__()
        env_vars.update(self.env)
        # append variables given to this function call
        if env:
            env_vars.update(env)

        # passed to test-wrapper as CLI args
        wrapper_args = [
            self.work_dir / "test" / "test.sh",  # test_exec
            test_fmf_dir,  # fmf_dir
        ]
        if test_data.get("tty", False):  # flags
            wrapper_args.append("pty")
        if os.environ.get("ATEX_DEBUG_NO_EXITCODE") == "1":
            wrapper_args.append("noexitcode")

        self.logger.debug(f"'{test_name}': {env_vars=}")

        with contextlib.ExitStack() as stack:
            reporter = stack.enter_context(
                Reporter(artifacts, "results", "files", logger=self.logger),
            )
            duration = Duration(test_data.get("duration", "5m"))
            control = TestControl(reporter=reporter, duration=duration, logger=self.logger)

            setup_script = make_test_setup(
                test_data=test_data,
                test_dir=self.work_dir / "test",
                wrapper_exec="wrapper.py",
                test_exec="test.sh",
                test_yaml="metadata.yaml",
                bin_dir=self.work_dir / "bin",
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
                    if self.cancelled:
                        abort("cancel requested")

                    if state == self.State.STARTING_TEST:
                        # reconnect/reboot count (for compatibility)
                        env_vars["TMT_REBOOT_COUNT"] = str(reconnects)
                        env_vars["TMT_TEST_RESTART_COUNT"] = str(reconnects)
                        env_args = (f"{k}={v}" for k, v in env_vars.items())
                        # open a pipe for test control
                        control_fd, pipe_w = os.pipe()
                        try:
                            os.set_blocking(control_fd, False)
                            control.reassign(control_fd)
                            # run the test in the background, letting it log output directly to
                            # an opened file (we don't handle it, cmd client sends it to kernel)
                            with reporter.open_testout() as testout_fd:
                                test_proc = self.conn.cmd(
                                    (
                                        "env", *env_args,
                                        self.work_dir / "test" / "wrapper.py", *wrapper_args,
                                    ),
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
                            # avoid 100% CPU spinning if the connection is too slow
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
                self._report_fallback_result(reporter, control.exit_code, exception, test_name)

    def __str__(self):
        class_name = self.__class__.__name__
        fmf_root = str(self.fmf_tests.root)
        return f"{class_name}({self.conn}, {fmf_root})"
