import tempfile

from ... import util
from .. import Orchestrator

_get_logger = util.get_loggers("atex.orchestrator.simple")


class SimpleOrchestrator(Orchestrator):
    """
    - `platform` is an arbitrary name that identifies this Orchestrator
      in the aggregated outputs.

      Ie. `9.6` or `rhel-9.6` or `9@x86_64` or `centos-10 Gitlab`.

    - `tests` may be any `str()`-capable objects, typically strings,
      for the Orchestrator to iterate and pass to an Executor as test
      names.

    - `provisioner` is an initialized and started Provisioner instance
      to source Remotes from, for test execution.

    - `executor` is a factory (function or class) that, when given
      a connected Connection, produces an initialized Executor instance,
      to be used for running tests.

      This could be an Executor class itself (as a type) or ie. a wrapper
      for instantiating the class with extra arguments.

    - `aggregator` is an initialized and started Aggregator instance
      for ingesting final test results from test artifacts produced
      by an Executor.
    """

    def __init__(self, platform, tests, provisioner, executor, aggregator, *, destructive=False):
        self.logger = _get_logger()

        self.platform = platform
        self._to_run = list(tests)
        self.provisioner = provisioner
        self.executor = executor
        self.aggregator = aggregator
        self.destructive = destructive

        self._previous = None

    def serve_once(self):
        if not self._to_run:
            return False

        test_name = self._to_run.pop(0)

        # reuse previous Remote
        if not self.destructive and self._previous:
            remote, executor = self._previous
        else:
            self.provisioner.provision()
            remote = self.provisioner.get_remote()
            executor = self.executor(remote)
            executor.start()

        try:
            with tempfile.TemporaryDirectory(prefix="atex-simple-") as artifacts:
                exit_code = executor.run_test(test_name, artifacts)
                self.logger.info(f"'{test_name}' exited with: {exit_code}")
                self.aggregator.ingest(self.platform, test_name, artifacts)
        except BaseException:
            remote.release()
            self._previous = None
            raise

        if not self.destructive:
            self._previous = (remote, executor)
        else:
            remote.release()

        return True

    def start(self):
        self.logger.debug(f"starting: {self}")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        if self._previous:
            remote, _ = self._previous
            remote.release()
            self._previous = None

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.platform}, {len(self._to_run)} tests)"
