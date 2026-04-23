import json
import threading
from pathlib import Path

import yaml

from ... import util
from .. import Aggregator, AggregatorError
from ..jsonl.jsonl import verbatim_move

get_logger = util.get_loggers("atex.aggregator.yamld")


class YAMLDocumentAggregator(Aggregator):
    """
    - `target` is a string/Path to a `.yaml` file for all ingested results
      to be aggregated (written) to.

    - `files` is a string/Path of the top-level parent for all per-platform
      / per-test files uploaded by tests.

    - `allow_duplicate` permits any one test name to be ingested more than
      once, appending ` (1)` to the second test name entry, ` (2)` to the
      third, etc.
    """

    def __init__(self, target, files, *, allow_duplicate=False):
        self.lock = threading.RLock()
        self.logger = get_logger()

        self.target = Path(target)
        self.files = Path(files)
        self.allow_duplicate = allow_duplicate
        self.seen_tests = {}
        self.target_fobj = None

    def start(self):
        self.logger.debug(f"starting: {self}")

        if self.target.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.target} already exists")
        self.target_fobj = open(self.target, "w")

        if self.files.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.files} already exists")
        self.files.mkdir()

    def stop(self):
        self.logger.debug(f"stopping: {self}")

        if self.target_fobj:
            self.target_fobj.close()
            self.target_fobj = None

    def ingest(self, platform, test_name, artifacts):
        unique_id = (platform, test_name)
        with self.lock:
            if unique_id in self.seen_tests:
                if not self.allow_duplicate:
                    raise AggregatorError(
                        f"'{test_name}' was already ingested once for '{platform}'",
                    )
                else:
                    test_name = f"{test_name} ({self.seen_tests[unique_id]})"
                    self.seen_tests[unique_id] += 1
            else:
                self.seen_tests[unique_id] = 1

        self.logger.info(f"ingesting '{platform}' / '{test_name}' from '{artifacts}'")

        artifacts = Path(artifacts)
        artifacts_results = artifacts / "results"
        artifacts_files = artifacts / "files"

        if not artifacts_results.exists(follow_symlinks=False):
            raise FileNotFoundError(f"{artifacts_results} does not exist")

        platform_files = self.files / util.normalize_path(platform)
        target_test_files = platform_files / util.normalize_path(test_name)
        if target_test_files.exists(follow_symlinks=False):
            raise FileExistsError(f"{target_test_files} already exists for {test_name}")

        # any None or empty values are deleted later,
        # to preserve dict insertion order with these on top
        document = {
            "platform": platform,
            "name": test_name,
            "status": None,
            "files": [],
            "note": None,
            "subtests": [],
        }

        with open(artifacts_results) as f:
            for raw_line in f:
                result_line = json.loads(raw_line)

                # these are standard fields defined in the Test Artifacts,
                # see README.md for an Executor

                # if it is a subtest, add it to subtests
                if name := result_line.get("name"):
                    subtest = {"name": name}
                    if status := result_line.get("status"):
                        subtest["status"] = status
                    if files := result_line.get("files"):
                        subtest["files"] = files
                    if note := result_line.get("note"):
                        subtest["note"] = note
                    document["subtests"].append(subtest)

                # update document for the test itself
                else:
                    if status := result_line.get("status"):
                        document["status"] = status
                    if files := result_line.get("files"):
                        document["files"] += files
                    if note := result_line.get("note"):
                        document["note"] = note

        if document["status"] is None:
            del document["status"]
        if not document["files"]:
            del document["files"]
        if document["note"] is None:
            del document["note"]
        if not document["subtests"]:
            del document["subtests"]

        with self.lock:
            yaml.dump(
                document,
                self.target_fobj,
                explicit_start=True,
                default_flow_style=False,
                sort_keys=False,
            )
            self.target_fobj.flush()

        # clean up the source test_results (Aggregator should 'mv', not 'cp')
        Path(artifacts_results).unlink()

        # if the artifacts files directory is not empty
        if any(artifacts_files.iterdir()):
            platform_files.mkdir(exist_ok=True)
            # TODO: why does this work without .mkdir(target_test_files.parent) ?
            verbatim_move(artifacts_files, target_test_files)

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({str(self.target)}, {str(self.files)})"
