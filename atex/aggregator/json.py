import gzip
import json
import shutil
import threading
from pathlib import Path

from . import Aggregator


class JSONAggregator(Aggregator):
    """
    Collects reported results in a line-JSON output file and uploaded files
    (logs) from multiple test runs under a shared directory.

    Note that the aggregated JSON file *does not* use the test-based JSON format
    described by executor/RESULTS.md - both use JSON, but are very different.

    This aggergated format uses a top-level array (on each line) with a fixed
    field order:

        platform, status, test name, subtest name, files, note

    All these are strings except 'files', which is another (nested) array
    of strings.

    If 'testout' is present in an input test result, it is prepended to
    the list of 'files'.
    If a field is missing in the source result, it is translated to a null
    value.
    """

    def __init__(self, target, files):
        """
        'target' is a string/Path to a .json file for all ingested
        results to be aggregated (written) to.

        'files' is a string/Path of the top-level parent for all
        per-platform / per-test files uploaded by tests.
        """
        self.lock = threading.RLock()
        self.target = Path(target)
        self.files = Path(files)
        self.target_fobj = None

    def start(self):
        if self.target.exists():
            raise FileExistsError(f"{self.target} already exists")
        self.target_fobj = open(self.target, "w")

        if self.files.exists():
            raise FileExistsError(f"{self.files} already exists")
        self.files.mkdir()

    def stop(self):
        if self.target_fobj:
            self.target_fobj.close()
            self.target_fobj = None

    def _get_test_files_path(self, platform, test_name):
        """
        Return a directory path to where uploaded files should be stored
        for a particular 'platform' and 'test_name'.
        """
        platform_files = self.files / platform
        platform_files.mkdir(exist_ok=True)
        test_files = platform_files / test_name.lstrip("/")
        return test_files

    @staticmethod
    def _modify_file_list(test_files):
        return test_files

    @staticmethod
    def _move_test_files(test_files, target_dir):
        """
        Move (or otherwise process) 'test_files' as directory of files uploaded
        by the test, into the pre-computed 'target_dir' location (inside
        a hierarchy of all files from all tests).
        """
        shutil.move(test_files, target_dir)

    @classmethod
    def _gen_test_results(cls, input_fobj, platform, test_name):
        """
        Yield complete output JSON objects, one for each input result.
        """
        # 'testout' , 'files' and others are standard fields in the
        # test control interface, see RESULTS.md for the Executor
        for raw_line in input_fobj:
            result_line = json.loads(raw_line)

            file_names = []
            # process the file specified by the 'testout' key
            if "testout" in result_line:
                file_names.append(result_line["testout"])
            # process any additional files in the 'files' key
            if "files" in result_line:
                file_names += (f["name"] for f in result_line["files"])

            file_names = cls._modify_file_list(file_names)

            output_line = (
                platform,
                result_line["status"],
                test_name,
                result_line.get("name"),  # subtest
                file_names,
                result_line.get("note"),
            )
            yield json.dumps(output_line, indent=None)

    def ingest(self, platform, test_name, test_results, test_files):
        target_test_files = self._get_test_files_path(platform, test_name)
        if target_test_files.exists():
            raise FileExistsError(f"{target_test_files} already exists for {test_name}")

        # parse the results separately, before writing any aggregated output,
        # to ensure that either ALL results from the test are ingested, or none
        # at all (ie. if one of the result lines contains JSON errors)
        with open(test_results) as test_results_fobj:
            output_results = self._gen_test_results(test_results_fobj, platform, test_name)
            output_json = "\n".join(output_results) + "\n"

        with self.lock:
            self.target_fobj.write(output_json)
            self.target_fobj.flush()

        # clean up the source test_results (Aggregator should 'mv', not 'cp')
        Path(test_results).unlink()

        # if the test_files dir is not empty
        if any(test_files.iterdir()):
            self._move_test_files(test_files, target_test_files)


