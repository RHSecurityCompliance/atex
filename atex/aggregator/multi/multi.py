import shutil
import subprocess
import tempfile
from pathlib import Path

from ... import util
from .. import Aggregator

_get_logger = util.get_loggers("atex.aggregator.multi")


class MultiAggregator(Aggregator):
    """
    - `aggregators` is a sequence of initialized (but not yet started)
      Aggregator instances.
    """

    def __init__(self, aggregators):
        self.logger = _get_logger()

        self.aggregators = list(aggregators)
        if not self.aggregators:
            raise ValueError("at least one Aggregator is required")

    def start(self):
        self.logger.debug(f"starting: {self}")

        for aggregator in self.aggregators:
            aggregator.start()

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        for aggregator in self.aggregators:
            try:
                aggregator.stop()
            except BaseException:
                self.logger.exception(f"failed to stop {aggregator}")

    def ingest(self, platform, test_name, artifacts):
        # since .ingest() is destructive, copy test artifacts for all
        # aggregators except the last one, and leave the original location
        # for the last aggregator to consume

        artifacts = Path(artifacts)
        for aggregator in self.aggregators[:-1]:
            tmp_copy = tempfile.mkdtemp(dir=artifacts.parent, prefix="atex-multi-")
            try:
                # use 'cp' to do reflink, python code for this is notoriously
                # buggy and takes forever on large trees
                subprocess.run(
                    ("cp", "--reflink=auto", "-a", f"{artifacts}/.", f"{tmp_copy}/."),
                    check=True,
                )
                aggregator.ingest(platform, test_name, tmp_copy)
            finally:
                shutil.rmtree(tmp_copy, ignore_errors=True)

        self.aggregators[-1].ingest(platform, test_name, artifacts)

    def __str__(self):
        class_name = self.__class__.__name__
        names = ", ".join(str(aggregator) for aggregator in self.aggregators)
        return f"{class_name}([{names}])"
