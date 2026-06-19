import json
import mimetypes
import shutil
import threading
from pathlib import Path

from ... import util
from .. import Aggregator

_get_logger = util.get_loggers("atex.aggregator.reportportal")


class ReportPortalAggregator(Aggregator):
    """
    - `api` is a configured class ReportPortalAPI instance.

    - `launch_name` and `launch_rerun` are mutually exclusive:

      - `launch_name` specifies that a new launch should be created with
        this name.

      - `launch_rerun` specifies an UUID of an existing launch to rerun.
        If set, `launch_name` must be left unset (existing name is reused).

    - `tests_promise` is an iterable of `(platform, test_name)` tuples,
      specifying all the platforms/tests that are expected to report results
      at some later point.

      If set, all of these are pre-reported as "in progress", helpfully showing
      to users watching the RP UI what is still left to finish.

    - `join_subtest` (string) sets a separator to merge test + subtest names
      with, changing how results are ingested.

      If unset, subtests are reported as child items under tests. This has the
      disadvantage of subtests avoiding RP AI analysis.

      If set (to ie. `/` or `::` or whatever), subtests are reported on the same
      level as tests, with the test name and `join_subtest` separator prefixed,
      which also includes them in RP AI analysis.
    """

    # ATEX/tmt status to ReportPortal status
    status_mapping = {
        "pass": "passed",
        "fail": "failed",
        "error": "failed",
        "warn": "warn",
        "infra": "interrupted",
        "skip": "skipped",
        "info": "info",
    }
    status_mapping_default = "info"

    def __init__(self, api, *, launch_name=None, launch_rerun=None, join_subtest=None):
        self._lock = threading.RLock()
        self.logger = _get_logger()

        if not launch_name and not launch_rerun:
            raise ValueError("'launch_name' or 'launch_rerun' must be given")
        if launch_name and launch_rerun:
            raise ValueError("'launch_name' and 'launch_rerun' are mutually exclusive")

        self._api = api
        self.launch_name = launch_name
        self.launch_rerun = launch_rerun
        self.join_subtest = join_subtest

        self._launch_uuid = None
        self._started_platforms = {}
        self._started_tests = {}
        self._finished = set()
        self._promised_tests = []

        self._ingesting = set()
        self._ingest_gate = threading.Condition()

    def start(self):
        self.logger.debug(f"starting: {self}")

        self._launch_uuid = self._api.launch_start(
            name=self.launch_name,
            rerun_of=self.launch_rerun,
        )

        with self._lock:
            promised = self._promised_tests
            self._promised_tests = []

        for platform, test_name in promised:
            platform_uuid = self._start_platform(platform)
            self._start_test(platform_uuid, test_name)

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        with self._lock:
            launch_uuid = self._launch_uuid
            self._started_platforms = {}
            self._started_tests = {}
            self._finished = set()
            self._launch_uuid = None

        if launch_uuid:
            # this also finishes all unfinished platforms/tests
            self._api.launch_finish(launch_uuid)

    def promise(self, platform, test_names):
        """
        Promise `test_names` to be reported later for `platform`, causing
        them to appear as "in progress" on the aggregator `.start()`.

        If the aggregator has already been started, create new "in progress"
        items right now from the passed arguments.
        """
        with self._lock:
            if not self._launch_uuid:
                self._promised_tests += ((platform, test_name) for test_name in test_names)
                return
        platform_uuid = self._start_platform(platform)
        for test_name in test_names:
            self._start_test(platform_uuid, test_name)

    @classmethod
    def map_status(cls, src):
        return cls.status_mapping.get(src, cls.status_mapping_default)

    @staticmethod
    def decide_subtest(platform, test_name, result):  # noqa: ARG004
        """
        Decides whether to report a result with 'name' (IOW a subtest)
        to the RP instance.

        Useful to ie. skip either all subtests or just the passing ones,
        for test suites with excessive amounts of results that might otherwise
        overload an RP instance.

        - `platform` and `test_name` are the args given to `.ingest()`
          that called this function.

        - `result` is a dict with a (fully parsed) single test result,
          see Test Artifacts for the keys it might have.

        Returns either True (report the result) or False (skip it).
        """
        return True

    @staticmethod
    def decide_file(platform, test_name, result, file):  # noqa: ARG004
        """
        Decides whether and how to upload a test file (log) to the RP instance.

        - `platform` and `test_name` are the args given to `.ingest()`
          that called this function.

        - `result` is a dict with a (fully parsed) single test result,
          see Test Artifacts for the keys it might have.

        - `file` is a Path to the (log) file to be read and uploaded.

        Returns either

        - `None`, indicating the file should not be uploaded at all.

        - `(level, inline)` tuple, where:

          - `level` is a log level string like `ERROR`, `INFO`, etc.
          - `inline` is a boolean, `True` means to show contents on-page,
            `False` means to upload the log as an attachment.
        """

        # by default, skip logs for non-failing statuses
        if result.get("status") not in ("fail", "error", "infra"):
            return None

        # since we're uploading files only for failed tests, set level
        # to ERROR, so it gets indexed by RP AI analyzer
        level = "ERROR"

        # if the file is named 'output.txt', it likely is the primary
        # output of the test executable, so include it on-page
        inline = (file.name == "output.txt")

        # actually, if the file is bigger than 1M, don't inline it
        if inline and file.stat().st_size > 1048576:
            inline = False

        return (level, inline)

    def _upload_files(self, parent_uuid, platform, test_name, artifacts_files, result):
        for file_name in result.get("files", ()):
            path = (
                artifacts_files
                / util.normalize_path(result.get("name", ""))
                / util.normalize_path(file_name)
            )
            if not path.exists():
                raise FileNotFoundError(
                    f"'{file_name}' doesn't exist for '{test_name}': {result}",
                )

            decision = self.decide_file(platform, test_name, result, path)
            if decision is None:
                continue
            level, inline = decision

            if inline:
                entry = {
                    "level": level,
                    "message": path.read_text(errors="replace"),
                }
            else:
                mime = mimetypes.guess_type(path)[0] or "text/plain"
                entry = {
                    "level": level,
                    "message": file_name,
                    "file": {
                        "name": path.name,  # basename only
                        "content": path.read_bytes(),
                        "content_type": mime,
                    },
                }

            # upload only one log at a time, do not batch, it's not worth it for the
            # typical handful of logs tests have, plus it allows each log to use
            # the full ~32M of max API request size
            self._api.log_upload(self._launch_uuid, parent_uuid, (entry,))

    def _start_platform(self, name):
        with self._lock:
            if platform_uuid := self._started_platforms.get(name):
                return platform_uuid
            platform_uuid = self._api.item_start(self._launch_uuid, "test", name)
            self._started_platforms[name] = platform_uuid
            return platform_uuid

    def _start_test(self, platform_uuid, name):
        with self._lock:
            key = (platform_uuid, name)
            if test_uuid := self._started_tests.get(key):
                return test_uuid
            retry = {"retry": True} if key in self._finished else {}
            test_uuid = self._api.item_start(
                self._launch_uuid, "step", name, parent=platform_uuid, **retry,
            )
            self._started_tests[key] = test_uuid
            return test_uuid

    def _finish_test(self, platform_uuid, name, **kwargs):
        key = (platform_uuid, name)
        with self._lock:
            if test_uuid := self._started_tests.get(key):
                self._api.item_finish(self._launch_uuid, test_uuid, **kwargs)
                del self._started_tests[key]
                self._finished.add(key)

    @staticmethod
    def _sane_results_from(results_file_path):
        with open(results_file_path) as f:
            for raw_line in f:
                result = json.loads(raw_line)
                if not result or "status" not in result:
                    continue
                yield result

    def ingest(self, platform, test_name, artifacts):
        # gate at most one concurrent ingest for platform + test_name at once,
        # to avoid item start/finish races
        unique_key = (platform, test_name)
        with self._ingest_gate:
            self._ingest_gate.wait_for(lambda: unique_key not in self._ingesting)
            self._ingesting.add(unique_key)

        try:
            self.logger.info(f"ingesting '{platform}' / '{test_name}' from '{artifacts}'")

            artifacts = Path(artifacts)
            artifacts_results = artifacts / "results"
            artifacts_files = artifacts / "files"

            if not artifacts_results.exists(follow_symlinks=False):
                raise FileNotFoundError(f"{artifacts_results} does not exist")

            platform_uuid = self._start_platform(platform)

            # report subtests as child items
            if self.join_subtest is None:
                test_uuid = self._start_test(platform_uuid, test_name)
                results = self._sane_results_from(artifacts_results)
                try:
                    for result in results:
                        if "name" in result:
                            if not self.decide_subtest(platform, test_name, result):
                                continue
                            # start + upload + finish for a subtest to ingest it
                            subtest_uuid = self._api.item_start(
                                self._launch_uuid,
                                "step",
                                result["name"],
                                parent=test_uuid,
                                hasStats=False,  # nested STEP
                            )
                            self._upload_files(
                                subtest_uuid,
                                platform,
                                test_name,
                                artifacts_files,
                                result,
                            )
                            self._api.item_finish(
                                self._launch_uuid,
                                subtest_uuid,
                                status=self.map_status(result["status"]),
                                description=result.get("note"),
                            )
                        else:
                            # stop on first non-subtest result, use it for test itself
                            self._upload_files(
                                test_uuid,
                                platform,
                                test_name,
                                artifacts_files,
                                result,
                            )
                            self._finish_test(
                                platform_uuid,
                                test_name,
                                status=self.map_status(result["status"]),
                                description=result.get("note"),
                            )
                            break
                finally:
                    results.close()

            # combine test+subtest names into a flat list of tests
            else:
                results = self._sane_results_from(artifacts_results)
                try:
                    for result in results:
                        if "name" in result:
                            if not self.decide_subtest(platform, test_name, result):
                                continue
                            # create a new combined name from test+subtest
                            item_name = f"{test_name}{self.join_subtest}{result['name']}"
                        else:
                            item_name = test_name

                        test_uuid = self._start_test(platform_uuid, item_name)
                        self._upload_files(
                            test_uuid,
                            platform,
                            test_name,
                            artifacts_files,
                            result,
                        )
                        self._finish_test(
                            platform_uuid,
                            item_name,
                            status=self.map_status(result["status"]),
                            description=result.get("note"),
                        )

                        # stop on first non-subtest result, use it for test itself
                        if "name" not in result:
                            break
                finally:
                    results.close()

            # no result for the test itself; no-op if the test was already finished
            self._finish_test(
                platform_uuid,
                test_name,
                status="interrupted",
                description="no name-less result reported for the test itself",
            )

            artifacts_results.unlink()
            if artifacts_files.exists():
                shutil.rmtree(artifacts_files)

        finally:
            with self._ingest_gate:
                self._ingesting.discard(unique_key)
                self._ingest_gate.notify_all()

    def __str__(self):
        launch = f"rerun:{self.launch_rerun}" if self.launch_rerun else self.launch_name
        return f"{self.__class__.__name__}({self._api}, {launch})"


def get_existing_tests(api, launch_uuid, platform, **kwargs):
    """
    Yield test names for tests matching `statuses` under `platform`.

    - `launch_uuid` is the launch UUID to iterate through.

    - `platform` is a platform name the test results would have been aggregated
      under in a previous run.

    - `kwargs` are passed straight to ReportPortalAPI `.item_list()`.
    """
    launch_id = api.launch_get(launch_uuid)["id"]

    platform_data = next(api.item_list(launch_id, item_type="test", name=platform), None)
    if not platform_data:
        return  # no platform with that name reported yet

    tests = api.item_list(
        launch_id,
        platform_data["id"],
        item_type="step",
        **kwargs,
    )
    yield from (t["name"] for t in tests)
