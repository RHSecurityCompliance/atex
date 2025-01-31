import tempfile
import concurrent
import collections
from pathlib import Path

from .. import util, executor
from . import Orchestrator, OrchestratorError


class FailedSetupError(OrchestratorError):
    pass


class AdHocOrchestrator(Orchestrator):
    """
    TODO: document function specific to this reference, ie. run_setup(), etc.
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
            # Path of a 'results' JSON file with test-reported results
            "results",
            # Path of a 'files' directory with test-uploaded files
            "files",
        ),
    ):
        pass

    def __init__(
        self, platform, fmf_tests, provisioners, aggregator, tmp_dir, *,
        max_remotes=1, max_spares=0, max_reruns=2, max_failed_setups=10, env=None,
    ):
        """
        'platform' is a string with platform name.

        'fmf_tests' is a class FMFTests instance of the tests to run.

        'provisioners' is an iterable of class Provisioner instances.

        'aggregator' is a class CSVAggregator instance.

        'tmp_dir' is a string/Path to a temporary directory, to be used for
        storing per-test results and uploaded files before being ingested
        by the aggregator. Can be safely shared by Orchestrator instances.

        'max_remotes' is how many Remotes to hold reserved at any given time,
        eg. how many tests to run in parallel. Clamped to the number of
        to-be-run tests given as 'fmf_tests'.

        'max_spares' is how many set-up Remotes to hold reserved and unused,
        ready to replace a Remote destroyed by test. Values above 0 greatly
        speed up test reruns as Remote reservation happens asynchronously
        to test execution. Spares are reserved on top of 'max_remotes'.

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
        self.max_remotes = max_remotes
        self.max_spares = max_spares
        # indexed by test name, value being integer of how many times
        self.reruns = collections.defaultdict(lambda: max_reruns)
        self.env = env
        # tests still waiting to be run
        self.to_run = set(fmf_tests.tests)
        # running tests as a dict, indexed by test name, with RunningInfo values
        self.running_tests = {}
        # thread queue for actively running tests
        self.test_queue = util.ThreadQueue(daemon=False)
        # thread queue for remotes being set up (uploading tests, etc.)
        self.setup_queue = util.ThreadQueue(daemon=True)
        # thread queue for remotes being released
        self.release_queue = util.ThreadQueue(daemon=True)

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
        test_data = self.fmf_tests.tests[finfo.test_name]

        # TODO: somehow move logging from was_successful and should_be_rerun here,
        #       probably print just some generic info from those functions that doesn't
        #       imply any outcome, ie.
        #           {remote_with_test} threw {exception}
        #           {remote_with_test} exited with {code}
        #           {remote_with_test} has {N} reruns left
        #           {remote_with_test} has 0 reruns left
        #       and then log the decision separately, here below, such as
        #           {remote_with_test} failed, re-running
        #           {remote_with_test} completed, ingesting result
        #           {remote_with_test} was destructive, releasing remote
        #           {remote_with_test} ...., running next test
        #       That allows the user to override the functions, while keeping critical
        #       flow reliably logged here.

        remote_with_test = f"{finfo.remote}: '{finfo.test_name}'"

        if not self.was_successful(finfo, test_data) and self.should_be_rerun(finfo, test_data):
            # re-run the test
            self.to_run.add(finfo.test_name)
        else:
            # ingest the result
            #
            # a condition just in case Executor code itself threw an exception
            # and didn't even report the fallback 'infra' result
            if finfo.results is not None and finfo.files is not None:
                self.aggregator.ingest(
                    self.platform,
                    finfo.test_name,
                    finfo.results,
                    finfo.files,
                )
                # also delete the tmpdir housing these
                finfo.tmp_dir.cleanup()
                # ingesting destroyed these
                finfo = self.FinishedInfo._from(
                    finfo,
                    results=None,
                    files=None,
                    tmp_dir=None,
                )

        # if destroyed, release the remote and request a replacement
        # (Executor exception is always considered destructive)
        if finfo.exception or self.destructive(finfo, test_data):
            util.debug(f"{remote_with_test} was destructive, releasing remote")
            self.release_queue.start_thread(
                finfo.remote.release,
                remote=finfo.remote,
            )
            finfo.provisioner.provision(1)

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
        # all done
        if not self.to_run and not self.running_tests and self.release_queue.qsize() == 0:
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

            tmp_dir_path = Path(rinfo.tmp_dir.name)
            results_path = tmp_dir_path / "results"
            files_path = tmp_dir_path / "files"

            finfo = self.FinishedInfo(
                **rinfo,
                exit_code=treturn.returned,
                exception=treturn.exception,
                results=results_path if results_path.exists() else None,
                files=files_path if files_path.exists() else None,
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

            if treturn.exception:
                msg = f"{sinfo.remote}: setup failed with {repr(treturn.exception)}"
                self.release_queue.start_thread(
                    sinfo.remote.release,
                    remote=sinfo.remote,
                )
                if (reruns_left := self.failed_setups_left) > 0:
                    util.warning(f"{msg}, re-trying ({reruns_left} setup retries left)")
                    self.failed_setups_left -= 1
                    sinfo.provisioner.provision(1)
                else:
                    util.warning(f"{msg}, setup retries exceeded, giving up")
                    raise FailedSetupError("setup retries limit exceeded, broken infra?")
            else:
                self._run_new_test(sinfo)

        # release any extra Remotes being held as set-up when we know we won't
        # use them for any tests (because to_run is empty)
        else:
            while self.setup_queue.qsize() > self.max_spares:
                try:
                    treturn = self.setup_queue.get_raw(block=False)
                except util.ThreadQueue.Empty:
                    break
                self.release_queue.start_thread(
                    treturn.sinfo.remote.release,
                    remote=treturn.sinfo.remote,
                )

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
                util.info(f"{provisioner}: running setup on new {remote}")

        # gather returns from Remote.release() functions - check for exceptions
        # thrown, re-report them as warnings as they are not typically critical
        # for operation
        try:
            treturn = self.release_queue.get_raw(block=False)
        except util.ThreadQueue.Empty:
            pass
        else:
            if treturn.exception:
                util.warning(f"{treturn.remote} release failed: {repr(treturn.exception)}")
            else:
                util.debug(f"{treturn.remote}: completed .release()")

        return True

    def start(self):
        # start all provisioners
        for prov in self.provisioners:
            prov.start()

        # start up initial reservations, balanced evenly across all available
        # provisioner instances
        count = min(self.max_remotes, len(self.fmf_tests.tests)) + self.max_spares
        provisioners = self.provisioners[:count]
        for idx, prov in enumerate(provisioners):
            if count % len(provisioners) > idx:
                prov.provision((count // len(provisioners)) + 1)
            else:
                prov.provision(count // len(provisioners))

    def stop(self):
        # cancel all running tests and wait for them to clean up (up to 0.1sec)
        for rinfo in self.running_tests.values():
            rinfo.executor.cancel()
        self.test_queue.join()  # also ignore any exceptions raised

        # stop all provisioners, also releasing all remotes
        # TODO: don't parallelize here, remove .stop_defer() and parallelize in provisioners
        if self.provisioners:
            workers = min(len(self.provisioners), 20)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                for provisioner in self.provisioners:
                    for func in provisioner.stop_defer():
                        ex.submit(func)

    @staticmethod
    def run_setup(sinfo):
        """
        Set up a newly acquired class Remote instance for test execution.

        'sinfo' is a SetupInfo instance with the (fully connected) remote.
        """
        sinfo.executor.start()
        sinfo.executor.upload_tests()
        sinfo.executor.plan_prepare()
        # NOTE: we never run executor.plan_finish() or even executor.stop()
        #       anywhere - instead, we assume the remote (and its connection)
        #       was invalidated by the test, so we just rely on remote.release()
        #       destroying the system

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

    @staticmethod
    def was_successful(info, test_data):  # noqa: ARG004
        """
        Return a boolean result whether a finished test was successful.
        Returning False might cause it to be re-run (per should_be_rerun()).

        'info' is Orchestrator.FinishedInfo namedtuple of the test.

        'test_data' is a dict of fully resolved fmf test metadata of that test.
        """
        remote_with_test = f"{info.remote}: '{info.test_name}'"

        # executor (or test) threw exception
        if info.exception:
            util.info(f"{remote_with_test} threw {repr(info.exception)} during test runtime")
            return False

        # the test exited as non-0
        if info.exit_code != 0:
            util.info(f"{remote_with_test} exited with non-zero: {info.exit_code}")
            return False

        # otherwise we good
        return True

    # TODO: @staticmethod and remove ARG002
    #@staticmethod
    def should_be_rerun(self, info, test_data):  # noqa: ARG004, ARG002
        """
        Return a boolean result whether a finished test failed in a way
        that another execution attempt might succeed, due to race conditions
        in the test or other non-deterministic factors.

        'info' is Orchestrator.FinishedInfo namedtuple of the test.

        'test_data' is a dict of fully resolved fmf test metadata of that test.
        """
        remote_with_test = f"{info.remote}: '{info.test_name}'"

        # TODO: remove self.reruns and the whole X-reruns logic from AdHocOrchestrator,
        #       leave it up to the user to wrap should_be_rerun() with an external dict
        #       of tests, counting reruns for each
        #        - allows the user to adjust counts per-test (ie. test_data metadata)
        #        - allows this template to be @staticmethod
        if (reruns_left := self.reruns[info.test_name]) > 0:
            util.info(f"{remote_with_test}: re-running ({reruns_left} reruns left)")
            self.reruns[info.test_name] -= 1
            return True
        else:
            util.info(f"{remote_with_test}: reruns exceeded, giving up")
            return False
