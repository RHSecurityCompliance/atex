import os
import json
from pathlib import Path

from .. import util


class Reporter:
    """
    Collects reported results (in a format specified by RESULTS.md) for
    a specific test, storing them persistently.
    """

    # internal name, stored inside 'output_dir' and hardlinked to
    # 'testout'-JSON-key-specified result entries; deleted on exit
    TESTOUT = "testout.temp"

    def __init__(self, output_dir, results_file, files_dir):
        """
        'output_dir' is a destination dir (string or Path) for results reported
        and files uploaded.

        'results_file' is a file name inside 'output_dir' the results will be
        reported into.

        'files_dir' is a dir name inside 'output_dir' any files will be
        uploaded to.
        """
        output_dir = Path(output_dir)
        self.testout_file = output_dir / self.TESTOUT
        self.results_file = output_dir / results_file
        self.files_dir = output_dir / files_dir
        self.output_dir = output_dir
        self.results_fobj = None
        self.testout_fobj = None

    def start(self):
        if self.testout_file.exists():
            raise FileExistsError(f"{self.testout_file} already exists")
        self.testout_fobj = open(self.testout_file, "wb")

        if self.results_file.exists():
            raise FileExistsError(f"{self.results_file} already exists")
        self.results_fobj = open(self.results_file, "w", newline="\n")

        if self.files_dir.exists():
            raise FileExistsError(f"{self.files_dir} already exists")
        self.files_dir.mkdir()

    def stop(self):
        if self.results_fobj:
            self.results_fobj.close()
            self.results_fobj = None

        if self.testout_fobj:
            self.testout_fobj.close()
            self.testout_fobj = None
            Path(self.testout_file).unlink()

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def report(self, result_line):
        """
        Persistently record a test result.

        'result_line' is a dict in the format specified by RESULTS.md.
        """
        json.dump(result_line, self.results_fobj, indent=None)
        self.results_fobj.write("\n")
        self.results_fobj.flush()

    def _dest_path(self, file_name, result_name=None):
        result_name = util.normalize_path(result_name) if result_name else "."
        # /path/to/files_dir / path/to/subtest / path/to/file.log
        file_path = self.files_dir / result_name / util.normalize_path(file_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        return file_path

    def open_file(self, file_name, result_name=None, mode="wb"):
        """
        Open a file named 'file_name' in a directory relevant to 'result_name'.
        Returns an opened file-like object that can be used in a context manager
        just like with regular open().

        If 'result_name' (typically a subtest) is not given, open the file
        for the test (name) itself.
        """
        return open(self._dest_path(file_name, result_name), mode)

    def link_testout(self, file_name, result_name=None):
        # TODO: docstring
        os.link(self.testout_file, self._dest_path(file_name, result_name))
