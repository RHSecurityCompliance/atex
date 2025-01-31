"""
Functions and utilities for persistently storing test results and files (logs).

There is a global aggregator (ie. CSVAggregator) that handles all the results
from all platforms (arches and distros), and several  per-platform aggregators
that are used by test execution logic.

    with CSVAggregator("results.csv.gz", "file/storage/dir") as global_aggr:
        reporter = global_aggr.for_platform("rhel-9@x86_64")
        reporter.report({"name": "/some/test", "status": "pass"})
        with reporter.open_tmpfile() as fd:
            os.write(fd, "some contents")
            reporter.link_tmpfile_to("/some/test", "test.log", fd)
"""

import os
import csv
import gzip
import ctypes
import ctypes.util
import threading
import contextlib
from pathlib import Path


libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

# int linkat(int olddirfd, const char *oldpath, int newdirfd, const char *newpath, int flags)
libc.linkat.argtypes = (
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
)
libc.linkat.restype = ctypes.c_int

# fcntl.h:#define AT_EMPTY_PATH                0x1000  /* Allow empty relative pathname */
AT_EMPTY_PATH = 0x1000

# fcntl.h:#define AT_FDCWD             -100    /* Special value used to indicate
AT_FDCWD = -100


def linkat(*args):
    if (ret := libc.linkat(*args)) == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return ret


def _normalize_path(path):
    # the magic here is to treat any dangerous path as starting at /
    # and resolve any weird constructs relative to /, and then simply
    # strip off the leading / and use it as a relative path
    path = path.lstrip("/")
    path = os.path.normpath(f"/{path}")
    return path[1:]


class CSVAggregator:
    """
    Collects reported results as a GZIP-ed CSV and files (logs) under a related
    directory.
    """

    class _ExcelWithUnixNewline(csv.excel):
        lineterminator = "\n"

    def __init__(self, results_file, storage_dir):
        self.lock = threading.RLock()
        self.storage_dir = Path(storage_dir)
        self.results_file = Path(results_file)
        self.csv_writer = None
        self.results_gzip_handle = None

    def __enter__(self):
        if self.results_file.exists():
            raise FileExistsError(f"{self.results_file} already exists")
        f = gzip.open(self.results_file, "wt", newline="")
        try:
            self.csv_writer = csv.writer(f, dialect=self._ExcelWithUnixNewline)
        except:
            f.close()
            raise
        self.results_gzip_handle = f

        if self.storage_dir.exists():
            raise FileExistsError(f"{self.storage_dir} already exists")
        self.storage_dir.mkdir()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.results_gzip_handle.close()
        self.results_gzip_handle = None
        self.csv_writer = None

    def report(self, platform, status, name, note, *files):
        with self.lock:
            self.csv_writer.writerow((platform, status, name, note, *files))

    def for_platform(self, platform_string):
        """
        Return a ResultAggregator instance that writes results into this
        CSVAgreggator instance.
        """
        def report(result_line):
            file_names = []
            if "testout" in result_line:
                file_names.append(result_line["testout"])
            if "files" in result_line:
                file_names += (f["name"] for f in result_line["files"])
            self.report(
                platform_string, result_line["status"], result_line["name"],
                result_line.get("note", ""), *file_names,
            )
        platform_dir = self.storage_dir / platform_string
        platform_dir.mkdir(exist_ok=True)
        return ResultAggregator(report, platform_dir)


class ResultAggregator:
    """
    Collects reported results (in a format specified by RESULTS.md) for
    a specific platform, storing them persistently.
    """

    def __init__(self, callback, storage_dir):
        """
        'callback' is a function to call to record a result, with the
        result dict passed as an argument.

        'storage_dir' is a directory for storing uploaded files.
        """
        self.report = callback
        self.storage_dir = storage_dir

    @contextlib.contextmanager
    def open_tmpfile(self, open_mode=os.O_WRONLY):
        """
        Open an anonymous (name-less) file for writing and yield its file
        descriptor (int) as context, closing it when the context is exited.
        """
        flags = open_mode | os.O_TMPFILE
        fd = os.open(self.storage_dir, flags, 0o644)
        try:
            yield fd
        finally:
            os.close(fd)

    def link_tmpfile_to(self, result_name, file_name, fd):
        """
        Store a file named 'file_name' in a directory relevant to 'result_name'
        whose 'fd' (a file descriptor) was created by .open_tmpfile().

        This function can be called multiple times with the same 'fd', and
        does not close or otherwise alter the descriptor.
        """
        # /path/to/all/logs / some/test/name / path/to/file.log
        file_path = self.storage_dir / result_name.lstrip("/") / _normalize_path(file_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        linkat(fd, b"", AT_FDCWD, bytes(file_path), AT_EMPTY_PATH)
