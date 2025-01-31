import time
import tempfile
import traceback
import concurrent
import collections
from pathlib import Path

from .. import util, executor


class OrchestratorError(Exception):
    pass


class FailedSetupError(OrchestratorError):
    pass


class Orchestrator:
    """
    A scheduler for parallel execution on multiple resources (machines/systems).
    """

    class SetupInfo(
        util.NamedMapping,
        required=(
            # class Provisioner instance this machine is provided by
            # (for logging purposes)
            "provisioner",
            # class Remote instance returned by the Provisioner
            "remote",
            # class Executor instance uploading tests / running setup or tests
            "executor",
        ),
    ):
        pass

    class RunningInfo(
        SetupInfo,
        required=(
            # string with /test/name
            "test_name",
            # class tempfile.TemporaryDirectory instance passed to Executor
            "tmp_dir",
        ),
    ):
        pass

    class FinishedInfo(
        RunningInfo,
        required=(
            # integer with exit code of the test
            # (None if exception happened)
            "exit_code",
            # exception class instance if running the test failed
            # (None if no exception happened (exit_code is defined))
            "exception",
        ),
    ):
        pass

    def __init__(
        self, platform, fmf_tests, provisioners, aggregator, tmp_dir, *,
        max_reruns=2, max_failed_setups=10, env=None,
    ):
        """
        'platform' is a string with platform name.

        'fmf_tests' is a class FMFTests instance of the tests to run.

        'provisioners' is an iterable of class Provisioner instances.

        'aggregator' is a class CSVAggregator instance.

        'tmp_dir' is a string/Path to a temporary directory, to be used for
        storing per-test results and uploaded files before being ingested
        by the aggregator. Can be safely shared by Orchestrator instances.

        'max_reruns' is an integer of how many times to re-try running a failed
        test (which exited with non-0 or caused an Executor exception).

        'max_failed_setups' is an integer of how many times an Executor's
        plan setup (uploading tests, running prepare scripts, etc.) may fail
        before FailedSetupError is raised.

        'env' is a dict of extra environment variables to pass to Executor.
        """
        self.platform = platform
        self.fmf_tests = fmf_tests
        self.provisioners = tuple(provisioners)
        self.aggregator = aggregator
        self.tmp_dir = tmp_dir
        self.failed_setups_left = max_failed_setups
        # indexed by test name, value being integer of how many times
        self.reruns = collections.defaultdict(lambda: max_reruns)
        self.env = env
        # tests still waiting to be run
        self.to_run = set(fmf_tests.tests)
        # running setup functions, as a list of SetupInfo items
        self.running_setups = []
        # running tests as a dict, indexed by test name, with RunningInfo values
        self.running_tests = {}
        # thread queue for actively running tests
        self.test_queue = util.ThreadQueue(daemon=False)
        # thread queue for remotes being set up (uploading tests, etc.)
        self.setup_queue = util.ThreadQueue(daemon=True)
        # NOTE: running_setups and test_running are just for debugging and
        #       cancellation, the execution flow itself uses ThreadQueues

    @staticmethod
    def run_setup(sinfo):
        """
        Set up a newly acquired class Remote instance for test execution.

        'sinfo' is a SetupInfo instance with the (fully connected) remote.
        """
        sinfo.executor.setup()
        sinfo.executor.upload_tests()
        sinfo.executor.plan_prepare()
        # NOTE: we never run executor.plan_finish() or even executor.cleanup()
        #       anywhere - instead, we assume the remote (and its connection)
        #       was invalidated by the test, so we just rely on remote.release()
        #       destroying the system

    def _run_new_test(self, info):
        """
        'info' can be either
          - SetupInfo instance with Remote/Executor to run the new test.
          - FinishedInfo instance of a previously executed test
            (reusing Remote/Executor for a new test).
        """
        next_test_name = self.next_test(self.to_run, self.fmf_tests.tests, info)
        assert next_test_name in self.to_run, "next_test() returned valid test name"

        util.info(f"starting '{next_test_name}' on {info.remote}")

        self.to_run.remove(next_test_name)

        rinfo = self.RunningInfo._from(
            info,
            test_name=next_test_name,
            tmp_dir=tempfile.TemporaryDirectory(
                prefix=next_test_name.strip("/").replace("/","-") + "-",
                dir=self.tmp_dir,
                delete=False,
            ),
        )

        tmp_dir_path = Path(rinfo.tmp_dir.name)
        self.test_queue.start_thread(
            target=info.executor.run_test,
            target_args=(
                next_test_name,
                tmp_dir_path,
            ),
            rinfo=rinfo,
        )

        self.running_tests[next_test_name] = rinfo

    def _process_finished_test(self, finfo):
        """
        'finfo' is a FinishedInfo instance.
        """
        remote_with_test = f"{finfo.remote}: '{finfo.test_name}'"

        def ingest_result():
            tmp_dir_path = Path(finfo.tmp_dir.name)
            results_file = tmp_dir_path / "results"
            files_dir = tmp_dir_path / "files"
            # in case Executor code itself threw an unrecoverable exception
            # and didn't even report the fallback 'infra' result
            if results_file.exists() and files_dir.exists():
                self.aggregator.ingest(self.platform, finfo.test_name, results_file, files_dir)
                finfo.tmp_dir.cleanup()

        # if executor (or test) threw exception, schedule a re-run
        if finfo.exception:
            exc_name = type(finfo.exception).__name__
            exc_tb = "".join(traceback.format_exception(finfo.exception)).rstrip("\n")
            msg = f"{remote_with_test} threw {exc_name} during test runtime"
            #finfo.remote.release()
            if (reruns_left := self.reruns[finfo.test_name]) > 0:
                util.info(f"{msg}, re-running ({reruns_left} reruns left):\n{exc_tb}")
                self.reruns[finfo.test_name] -= 1
                self.to_run.add(finfo.test_name)
            else:
                util.info(f"{msg}, reruns exceeded, giving up:\n{exc_tb}")
                # record the final result anyway
                ingest_result()

        # if the test exited as non-0, try a re-run
        elif finfo.exit_code != 0:
            msg = f"{remote_with_test} exited with non-zero: {finfo.exit_code}"
            #finfo.remote.release()
            if (reruns_left := self.reruns[finfo.test_name]) > 0:
                util.info(f"{msg}, re-running ({reruns_left} reruns left)")
                self.reruns[finfo.test_name] -= 1
                self.to_run.add(finfo.test_name)
            else:
                util.info(f"{msg}, reruns exceeded, giving up")
                # record the final result anyway
                ingest_result()

        # test finished successfully - ingest its results
        else:
            util.info(f"{remote_with_test} finished successfully")
            ingest_result()

        # if destroyed, release the remote
        # (Executor exception is always considered destructive)
        test_data = self.fmf_tests.tests[finfo.test_name]
        if finfo.exception or self.destructive(finfo, test_data):
            util.debug(f"{remote_with_test} was destructive, releasing remote")
            finfo.remote.release()

        # if still not destroyed, run another test on it
        # (without running plan setup, re-using already set up remote)
        elif self.to_run:
            util.debug(f"{remote_with_test} was non-destructive, running next test")
            self._run_new_test(finfo)

    def serve_once(self):
        """
        Run the orchestration logic, processing any outstanding requests
        (for provisioning, new test execution, etc.) and returning once these
        are taken care of.

        Returns True to indicate that it should be called again by the user
        (more work to be done), False once all testing is concluded.
        """
        util.debug(
            f"to_run: {len(self.to_run)} tests / "
            f"running: {len(self.running_tests)} tests, {len(self.running_setups)} setups",
        )
        # all done
        if not self.to_run and not self.running_tests:
            return False

        # process all finished tests, potentially reusing remotes for executing
        # further tests
        while True:
            try:
                treturn = self.test_queue.get_raw(block=False)
            except util.ThreadQueue.Empty:
                break

            rinfo = treturn.rinfo
            del self.running_tests[rinfo.test_name]

            finfo = self.FinishedInfo(
                **rinfo,
                exit_code=treturn.returned,
                exception=treturn.exception,
            )
            self._process_finished_test(finfo)

        # process any remotes with finished plan setup (uploaded tests,
        # plan-defined pkgs / prepare scripts), start executing tests on them
        while self.to_run:
            try:
                treturn = self.setup_queue.get_raw(block=False)
            except util.ThreadQueue.Empty:
                break

            sinfo = treturn.sinfo
            self.running_setups.remove(sinfo)

            if treturn.exception:
                exc_name = type(treturn.exception).__name__
                exc_tb = "".join(traceback.format_exception(treturn.exception)).rstrip("\n")
                msg = f"{sinfo.remote}: setup failed with {exc_name}"
                sinfo.remote.release()
                if (reruns_left := self.failed_setups_left) > 0:
                    util.warning(f"{msg}, re-trying ({reruns_left} setup retries left):\n{exc_tb}")
                    self.failed_setups_left -= 1
                else:
                    util.warning(f"{msg}, setup retries exceeded, giving up:\n{exc_tb}")
                    raise FailedSetupError("setup retries limit exceeded, broken infra?")
            else:
                self._run_new_test(sinfo)

        # try to get new remotes from Provisioners - if we get some, start
        # running setup on them
        for provisioner in self.provisioners:
            while (remote := provisioner.get_remote(block=False)) is not None:
                ex = executor.Executor(self.fmf_tests, remote, env=self.env)
                sinfo = self.SetupInfo(
                    provisioner=provisioner,
                    remote=remote,
                    executor=ex,
                )
                self.setup_queue.start_thread(
                    target=self.run_setup,
                    target_args=(sinfo,),
                    sinfo=sinfo,
                )
                self.running_setups.append(sinfo)
                util.info(f"{provisioner}: running setup on new {remote}")

        return True

    def serve_forever(self):
        """
        Run the orchestration logic, blocking until all testing is concluded.
        """
        while self.serve_once():
            time.sleep(1)

    def start(self):
        # start all provisioners
        for prov in self.provisioners:
            prov.start()
        return self

    def stop(self):
        # cancel all running tests and wait for them to clean up (up to 0.1sec)
        for rinfo in self.running_tests.values():
            rinfo.executor.cancel()
        self.test_queue.join()  # also ignore any exceptions raised

        # stop all provisioners, also releasing all remotes
        if self.provisioners:
            workers = min(len(self.provisioners), 20)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                for provisioner in self.provisioners:
                    for func in provisioner.stop_defer():
                        ex.submit(func)

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    @staticmethod
    def next_test(to_run, all_tests, previous):  # noqa: ARG004
        """
        Return a test name (string) to be executed next.

        'to_run' is a set of test names to pick from. The returned test name
        must be chosen from this set.

        'tests' is a dict indexed by test name (string), with values being
        fully resolved fmf test metadata (dicts) of all possible tests.

        'previous' can be either
          - Orchestrator.SetupInfo instance (first test to be run)
          - Orchestrator.FinishedInfo instance (previous executed test)

        This method must not modify any of its arguments, it must treat them
        as read-only, eg. don't remove the returned test name from 'to_run'.
        """
        # default to simply picking any available test
        return next(iter(to_run))

    @staticmethod
    def destructive(info, test_data):  # noqa: ARG004
        """
        Return a boolean result whether a finished test was destructive
        to a class Remote instance, indicating that the Remote instance
        should not be used for further test execution.

        'info' is Orchestrator.FinishedInfo namedtuple of the test.

        'test_data' is a dict of fully resolved fmf test metadata of that test.
        """
        # if Executor ended with an exception (ie. duration exceeded),
        # consider the test destructive
        if info.exception:
            return True
        # if the test returned non-0 exit code, it could have thrown
        # a python exception of its own, or (if bash) aborted abruptly
        # due to 'set -e', don't trust the remote, consider it destroyed
        if info.exit_code != 0:
            return True
        # otherwise we good
        return False
        # TODO: override with additional 'extra-contest: destructive: True' fmf metadata
        # destructive = test_data.get("extra-contest", {}).get("destructive", False)
