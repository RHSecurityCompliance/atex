import contextlib
import json
import os
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
        - `output_dir` is a destination dir (string or Path) for results
          reported and files uploaded.

        - `results_file` is a file name inside `output_dir` the results
          will be reported into.

        - `files_dir` is a dir name inside `output_dir` any files will be
          uploaded to.
        """
        self.output_dir = Path(output_dir)
        self.results_file = self.output_dir / results_file
        self.results_fobj = None
        self.files_dir = self.output_dir / files_dir
        self.testout_file = self.output_dir / self.TESTOUT

    def start(self):
        if self.results_file.exists():
            raise FileExistsError(f"{self.results_file} already exists")
        self.results_fobj = open(self.results_file, "w", newline="\n")

        if self.testout_file.exists():
            raise FileExistsError(f"{self.testout_file} already exists")
        self.testout_file.touch()

        if self.files_dir.exists():
            raise FileExistsError(f"{self.files_dir} already exists")
        self.files_dir.mkdir()

    def stop(self):
        if self.results_fobj:
            self.results_fobj.close()
            self.results_fobj = None
        self.testout_file.unlink(missing_ok=True)

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

        - `result_line` is a dict in the format specified by RESULTS.md.
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

    @contextlib.contextmanager
    def open_file(self, file_name, mode, result_name=None):
        """
        Open a file named `file_name` in a directory relevant to `result_name`.
        Yields an opened file descriptor (as integer) as a Context Manager.

        If `result_name` (typically a subtest) is not given, open the file
        for the test (name) itself.
        """
        fd = os.open(self._dest_path(file_name, result_name), mode)
        try:
            yield fd
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def open_testout(self):
        """
        Open a file named after self.TESTOUT inside self.output_dir.
        Yields an opened file descriptor (as integer) as a Context Manager.
        """
        fd = os.open(self.testout_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        try:
            yield fd
        finally:
            os.close(fd)

    def link_testout(self, file_name, result_name=None):
        # TODO: docstring
        os.link(self.testout_file, self._dest_path(file_name, result_name))
