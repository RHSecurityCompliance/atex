import tempfile

from ... import util
from .. import Orchestrator, OrchestratorError

_get_logger = util.get_loggers("atex.orchestrator.adhoc")


class FailedSetupError(OrchestratorError):
    pass


class AdHocOrchestrator(Orchestrator):
    """
    - `platform` is an arbitrary name that identifies this Orchestrator
      in the aggregated outputs.

      Ie. `9.6` or `rhel-9.6` or `9@x86_64` or `centos-10 Gitlab`.

    - `tests` may be any `str()`-capable objects, typically strings,
      for the Orchestrator to iterate and pass to an Executor as test
      names.

    - `provisioners` are initialized and started Provisioner instances
      to source Remotes from, for test execution.

    - `executor` is a factory (function or class) that, when given
      a connected Connection, produces an initialized Executor instance,
      to be used for running tests.

      This could be an Executor class itself (as a type) or ie. a wrapper
      for instantiating the class with extra arguments.

    - `aggregator` is an initialized and started Aggregator instance
      for ingesting final test results from test artifacts produced
      by an Executor.

    - `old_aggregator` is a started class Aggregator instance for ingesting
      "old" test results (from tests that were later re-run). If left
      as None, these results are discarded.

      Collecting these may be useful for debugging why tests fail randomly.
      Note that the Aggregator needs to support ingesting duplicated
      test names.

    - `max_spares` is how many set-up Remotes to hold reserved and unused,
      ready to replace a Remote destroyed by test. Values above 0 can
      greatly speed up test reruns for Provisioners that take a long time
      to reserve a Remote.

    - `max_failed_setups` is an integer of how many times a setup (preparing
      a reserved Remote for test execution) may fail before FailedSetupError
      is raised.
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
            # Path of a dir with test artifacts as a TemporaryDirectory instance
            "artifacts",
        ),
    ):
        pass

    class FinishedInfo(
        RunningInfo,
        required=(
            # return value of the .run_test() Executor method
            # (None if exception happened)
            "exit_code",
            # exception class instance if running the test failed
            # (None if no exception happened (return is defined))
            "exception",
        ),
    ):
        pass

    def __init__(
        self, platform, tests, provisioners, executor, aggregator, *,
        old_aggregator=None, max_spares=0, max_failed_setups=10,
    ):
        self.logger = _get_logger()

        self.platform = platform
        # dict() instead of set() to preserve order
        self._to_run = dict.fromkeys(tests)
        self.provisioners = tuple(provisioners)
        self.aggregator = aggregator
        self.executor = executor

        if not self._to_run:
            raise ValueError("no tests were passed to run, 'tests' is empty")

        self.old_aggregator = old_aggregator
        self.max_spares = max_spares
        self._failed_setups_left = max_failed_setups

        # just for str(self)
        self._total_tests = len(self._to_run)
        # True if empty self._to_run was seen at least once;
        # needed because re-runs add the test back to self._to_run
        self._finishing_up = False
        # running tests as a dict, indexed by test name, with RunningInfo values
        self._running_tests = {}
        # thread queue for actively running tests
        self._test_queue = util.ThreadReturnQueue(daemon=False)
        # thread queue for remotes being set up (uploading tests, etc.)
        self._setup_queue = util.ThreadReturnQueue(daemon=True)
        # thread queue for remotes being released
        self._release_queue = util.ThreadReturnQueue(daemon=True)
        # thread queue for results being ingested
        self._ingest_queue = util.ThreadReturnQueue(daemon=False)

    def _run_new_test(self, info):
        """
        `info` can be either

          - SetupInfo instance with Remote/Executor to run the new test.

          - FinishedInfo instance of a previously executed test
            (reusing Remote/Executor for a new test).
        """
        next_test_name = self.next_test(self._to_run.keys(), info)
        assert next_test_name in self._to_run, "next_test() needs to return a valid test name"

        self.logger.info(f"starting '{next_test_name}' on {info.remote}")

        del self._to_run[next_test_name]

        # let __del__ take care of it in case we don't
        artifacts = tempfile.TemporaryDirectory(
            prefix="atex-" + str(util.normalize_path(next_test_name)).replace("/","-") + "-",
        )

        rinfo = self.RunningInfo._from(
            info,
            test_name=next_test_name,
            artifacts=artifacts,
        )

        self._test_queue.start_thread(
            target=info.executor.run_test,
            target_args=(
                next_test_name,
                artifacts.name,
            ),
            rinfo=rinfo,
        )

        self._running_tests[next_test_name] = rinfo

    @staticmethod
    def _ingest_and_cleanup(ingest, args, cleanup):
        try:
            ingest(*args)
        finally:
            cleanup()

    def _process_finished_test(self, finfo):
        """
        `finfo` is a FinishedInfo instance.
        """
        if finfo.exception:
            exc_str = f"{type(finfo.exception).__name__}({finfo.exception})"
            self.logger.warning(f"'{finfo.test_name}' threw {exc_str} during test runtime")
            remote_destroyed = True
        else:
            self.logger.debug(f"'{finfo.test_name}' exited with: {finfo.exit_code}")
            remote_destroyed = self.destructive(finfo)

        if (finfo.exception or finfo.exit_code != 0) and self.should_be_rerun(finfo):
            self.logger.info(f"'{finfo.test_name}' failed, re-running")
            self._to_run[finfo.test_name] = None  # add it

            # provision a replacement for a destroyed Remote
            if remote_destroyed:
                self.logger.debug(f"{finfo.remote} was destroyed, getting a new one")
                finfo.provisioner.provision(1)

            if self.old_aggregator:
                # ingest the test artifacts into old_aggregator (will be rerun)
                self._ingest_queue.start_thread(
                    self._ingest_and_cleanup,
                    target_args=(
                        # ingest func itself
                        self.old_aggregator.ingest,
                        # args for ingest
                        (self.platform, finfo.test_name, finfo.artifacts.name),
                        # cleanup func itself
                        finfo.artifacts.cleanup,
                    ),
                    test_name=finfo.test_name,
                )
            else:
                # discard the test artifacts
                finfo.artifacts.cleanup()

        else:
            self.logger.info(f"'{finfo.test_name}' completed, ingesting result")

            # ingest the artifacts into the main aggregator
            self._ingest_queue.start_thread(
                self._ingest_and_cleanup,
                target_args=(
                    # ingest func itself
                    self.aggregator.ingest,
                    # args for ingest
                    (self.platform, finfo.test_name, finfo.artifacts.name),
                    # cleanup func itself
                    finfo.artifacts.cleanup,
                ),
                test_name=finfo.test_name,
            )

        # ingested (destroyed) or removed, artifacts are invalid either way
        finfo = self.FinishedInfo._from(finfo, artifacts=None)

        # if there are still tests to run and the Remote is still valid,
        # run the next test on it (possibly a rerun)
        if self._to_run and not remote_destroyed:
            self.logger.debug(f"'{finfo.test_name}' was non-destructive, running next test")
            self._run_new_test(finfo)
        else:
            self.logger.debug(f"{finfo.remote} no longer useful, releasing it")
            self._release_queue.start_thread(
                finfo.remote.release,
                remote=finfo.remote,
            )

    def serve_once(self):
        # all done
        if not self._to_run and not self._running_tests:
            return False

        # process all finished tests, potentially reusing remotes for executing
        # further tests
        while True:
            try:
                treturn = self._test_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break

            rinfo = treturn.rinfo
            del self._running_tests[rinfo.test_name]

            finfo = self.FinishedInfo(
                **rinfo,
                exit_code=treturn.returned,
                exception=treturn.exception,
            )
            self._process_finished_test(finfo)

        # process any remotes with finished setup, start executing tests on them
        while self._to_run:
            try:
                treturn = self._setup_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break

            sinfo = treturn.sinfo

            if treturn.exception:
                exc_str = f"{type(treturn.exception).__name__}({treturn.exception})"
                msg = f"{sinfo.remote}: setup failed with {exc_str}"
                self._release_queue.start_thread(
                    sinfo.remote.release,
                    remote=sinfo.remote,
                )
                if self._failed_setups_left > 0:
                    self._failed_setups_left -= 1
                    self.logger.warning(
                        f"{msg}, re-trying ({self._failed_setups_left} setup retries left)",
                    )
                    sinfo.provisioner.provision(1)
                else:
                    self.logger.error(f"{msg}, setup retries exceeded, giving up")
                    raise FailedSetupError("setup retries limit exceeded, broken infra?")
            else:
                self._run_new_test(sinfo)

        # everything is either finished, running, or about to be re-run,
        # and we have a healthy buffer of spare Remotes,
        #
        # so exit the "get as many Remotes as possible" mode, and enter
        # the "provision only replacements for destroyed Remotes" mode
        if (
            not self._to_run and
            not self._finishing_up and
            self._setup_queue.qsize() >= self.max_spares
        ):
            self._finishing_up = True
            self.logger.info("switching to finishing-up mode, sending .clear() to provisioners")
            for prov in self.provisioners:
                prov.clear()

        # release any extra Remotes being held as set-up beyond what we need
        # for re-runs + self.max_spares
        # (may happen due to reservation batching in a Provisioner)
        while self._setup_queue.qsize() > len(self._to_run) + self.max_spares:
            try:
                treturn = self._setup_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break
            self.logger.info(f"releasing extraneous set-up {treturn.sinfo.remote}")
            self._release_queue.start_thread(
                treturn.sinfo.remote.release,
                remote=treturn.sinfo.remote,
            )

        # try to get new Remotes from Provisioners - if we get some, start
        # running setup on them
        for provisioner in self.provisioners:
            while (remote := provisioner.get_remote(block=False)) is not None:
                ex = self.executor(remote)
                sinfo = self.SetupInfo(
                    provisioner=provisioner,
                    remote=remote,
                    executor=ex,
                )
                self._setup_queue.start_thread(
                    target=self.run_setup,
                    target_args=(sinfo,),
                    sinfo=sinfo,
                )
                self.logger.info(f"running setup on new {remote}")

        # gather returns from Remote.release() functions - check for exceptions
        # thrown, re-report them as warnings as they are not typically critical
        # for operation
        while True:
            try:
                treturn = self._release_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break
            else:
                if treturn.exception:
                    exc_str = f"{type(treturn.exception).__name__}({treturn.exception})"
                    self.logger.warning(f"{treturn.remote} release failed: {exc_str}")
                else:
                    self.logger.debug(f"{treturn.remote} release completed")

        # gather returns from Aggregator.ingest() calls - check for exceptions
        while True:
            try:
                treturn = self._ingest_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break
            else:
                if treturn.exception:
                    exc_str = f"{type(treturn.exception).__name__}({treturn.exception})"
                    self.logger.error(f"'{treturn.test_name}' ingesting failed: {exc_str}")
                else:
                    self.logger.debug(f"'{treturn.test_name}' ingesting completed")

        return True

    def start(self):
        self.logger.debug(f"starting: {self}")

        # start up initial reservations - the idea is to request as much remotes
        # as there are tests (worst possible case where Remotes are not reused)
        # from EACH provisioner, allowing any one of them to supply the Remotes
        # - any destructive tests do .provision(1) anyway
        #
        # after self._to_run is exhausted, we do .clear() on all of these
        # and let just the destructive .provision(1) logic get new Remotes
        remotes = len(self._to_run)
        for prov in self.provisioners:
            prov.provision(remotes)

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        # cancel all running tests and wait for them to clean up
        for rinfo in self._running_tests.values():
            rinfo.executor.cancel()
        self._test_queue.join()    # also ignore any exceptions raised

        # wait for all running ingestions to finish, print exceptions
        self._ingest_queue.join()
        while True:
            try:
                treturn = self._ingest_queue.get_raw(block=False)
            except util.ThreadReturnQueue.Empty:
                break
            else:
                if treturn.exception:
                    exc_str = f"{type(treturn.exception).__name__}({treturn.exception})"
                    self.logger.error(f"'{treturn.test_name}' ingesting failed: {exc_str}")
                else:
                    self.logger.debug(f"'{treturn.test_name}' ingesting completed")

    def __str__(self):
        class_name = self.__class__.__name__
        running = len(self._running_tests)
        queued = len(self._to_run)
        total = self._total_tests
        set_up = self._setup_queue.qsize()
        return (
            f"{class_name}({self.platform}, {queued}/{total} queued, {running} running, "
            f"{set_up} set up)"
        )

    def run_setup(self, info, /):  # noqa: PLR6301
        """
        Set up a newly acquired class Remote instance for test execution.

        - `info` is a SetupInfo instance with the (fully connected) remote.
        """
        info.executor.start()
        # NOTE: we never run executor.stop() because we assume the remote
        #       (and its connection) was invalidated by the testing, so we just
        #       rely on remote.release() destroying the system

    def next_test(self, to_run, previous, /):  # noqa: ARG002, PLR6301
        """
        Return a test name (string) to be executed next.

        - `to_run` is a sequence of test names to pick from. The returned
          test name must be chosen from these names.

        - `previous` can be either

          - AdHocOrchestrator.SetupInfo instance (first test to be run)

          - AdHocOrchestrator.FinishedInfo instance (previous executed test)

        This method must not modify any of its arguments, it must treat them
        as read-only, eg. don't remove the returned test name from `to_run`.
        """
        # default to simply picking any available test
        return next(iter(to_run))

    def destructive(self, info, /):  # noqa: PLR6301
        """
        Return a boolean result whether a finished test was destructive
        to a class Remote instance, indicating that the Remote instance
        should not be used for further test execution.

        - `info` is AdHocOrchestrator.FinishedInfo of the test.
        """
        # if the test returned non-0 exit code, it could have thrown
        # a python exception of its own, or (if bash) aborted abruptly
        # due to 'set -e', don't trust the remote, consider it destroyed
        if info.exit_code != 0:
            return True
        # otherwise we good
        return False

    def should_be_rerun(self, info, /):  # noqa: ARG002, PLR6301
        """
        Return a boolean result whether a finished test failed in a way
        that another execution attempt might succeed, due to race conditions
        in the test or other non-deterministic factors.

        - `info` is AdHocOrchestrator.FinishedInfo of the test.
        """
        # never rerun by default
        return False
