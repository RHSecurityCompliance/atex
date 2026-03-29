import contextlib
import json
import logging
import os
from pathlib import Path

from ... import util
from .testcontrol import BadReportJSONError


class Reporter:
    """
    Collects reported results (in a format specified by RESULTS.md) for
    a specific test, storing them persistently.
    """

    # internal name, stored inside 'output_dir' and hardlinked to
    # 'testout'-JSON-key-specified result entries; deleted on exit
    TESTOUT = "testout.temp"

    def __init__(self, output_dir, results_file, files_dir, *, logger=None):
        """
        - `output_dir` is a destination dir (string or Path) for results
          reported and files uploaded.

        - `results_file` is a file name inside `output_dir` the results
          will be reported into.

        - `files_dir` is a dir name inside `output_dir` any files will be
          uploaded to.

        - `logger` is an logging-API object to log messages to.
        """
        self.logger = logger or logging.getLogger("atex")

        self.output_dir = Path(output_dir)
        self.results_file = self.output_dir / results_file
        self.results_fobj = None
        self.files_dir = self.output_dir / files_dir
        self.testout_file = self.output_dir / self.TESTOUT
        # data of partial results
        self.partial = {}
        # whether any one of the results was without a 'name' key,
        # indicating a result for the test itself was reported
        self.nameless_result_seen = False
        # whether any one of the results ever linked testout to a file
        self.testout_seen = False

    @classmethod
    def _merge_partial(cls, dst, src):
        """
        Merge a `src` dict into `dst`, using the rules described by
        RESULTS.md for "Partial results".
        """
        for key, value in src.items():
            # delete existing if new value is None (JSON null)
            if value is None:
                if key in dst:
                    del dst[key]
                # don't add a new key with None value
                continue
            # add new key
            if key not in dst:
                dst[key] = value
                continue

            orig_value = dst[key]
            # different type - replace
            if type(value) is not type(orig_value):
                dst[key] = value
                continue

            # nested dict, merge it recursively
            if isinstance(value, dict):
                cls._merge_partial(orig_value, value)
            # extensible sequence, extend it
            elif isinstance(value, list):
                orig_value += value
            # immutable sequence, re-created a merged one
            elif isinstance(value, tuple):
                dst[key] = (*orig_value, *value)
            # overridable types, doesn't make sense to extend them
            elif isinstance(value, (str, int, float, bool, bytes, bytearray)):
                dst[key] = value
            # set-like, needs unioning
            elif isinstance(value, set):
                orig_value.update(value)
            else:
                raise BadReportJSONError(f"cannot merge type {type(value)}")

    def _report_to_file(self, result_line):
        # if testout was specified and is valid, link output to it
        if "testout" in result_line:
            testout = result_line["testout"]
            try:
                self.link_testout(testout, result_line.get("name"))
            except FileExistsError:
                raise BadReportJSONError(f"file '{testout}' already exists") from None

        # convert the set() of files into a sorted list
        if "files" in result_line:
            result_line["files"] = sorted(result_line["files"])

        # write persistently to the results file
        json.dump(result_line, self.results_fobj, indent=None)
        self.results_fobj.write("\n")
        self.results_fobj.flush()

    def replay_partial(self):
        """
        Pop all unfinished partial results and finalize them, writing them out
        to the results file.
        """
        values = self.partial.values()
        self.partial = {}
        for final in values:
            try:
                self._report_to_file(final)
            except (BadReportJSONError, TypeError) as e:
                self.logger.error(f"{type(e).__name__}({e}) when replaying {final}")

    def report(self, result_line):
        """
        Persistently record a test result.

        - `result_line` is a dict in the format specified by RESULTS.md.
        """
        self.logger.debug(f"report() received {result_line}")

        # transform files to just a set(), discarding length, to make it follow
        # the Test Artifacts format
        if "files" in result_line:
            result_line["files"] = {f["name"] for f in result_line["files"]}

        if (partial_flag := result_line.get("partial")) is not None:
            # do not store the 'partial' key in the result, even if False
            del result_line["partial"]

        if "name" not in result_line:
            self.nameless_result_seen = True
        if "testout" in result_line:
            if not result_line["testout"]:
                raise BadReportJSONError("'testout' specified, but empty")
            self.testout_seen = True

        # None is valid too
        name = result_line.get("name")

        # if the result is partial:true, just store it temporarily, do not
        # write it persistently yet
        if partial_flag:
            if name in self.partial:
                self._merge_partial(self.partial[name], result_line)
            else:
                self.partial[name] = result_line

        else:
            # if there is a partial result for the result_line, merge it
            try:
                final = self.partial.pop(name)
            except KeyError:
                # no previous partial result - use the current result as final
                final = result_line
            else:
                # merge the current result into the partial one,
                # then use it as final for writing persistently
                self._merge_partial(final, result_line)

            self._report_to_file(final)

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

    def start(self):
        if self.results_file.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.results_file} already exists")
        self.results_fobj = open(self.results_file, "w", newline="\n")

        if self.testout_file.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.testout_file} already exists")
        self.testout_file.touch()

        if self.files_dir.exists(follow_symlinks=False):
            raise FileExistsError(f"{self.files_dir} already exists")
        self.files_dir.mkdir()

    def stop(self):
        self.replay_partial()

        if self.results_fobj:
            self.results_fobj.close()
            self.results_fobj = None

        self.testout_file.unlink(missing_ok=True)

        self.nameless_result_seen = False
        self.testout_seen = False

    def __enter__(self):
        try:
            self.start()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
