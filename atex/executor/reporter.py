import os
import json
import ctypes
import ctypes.util
import contextlib
from pathlib import Path

from .. import util


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


class Reporter:
    """
    Collects reported results (in a format specified by RESULTS.md) for
    a specific test, storing them persistently.
    """

    def __init__(self, json_file, files_dir):
        """
        'json_file' is a destination file (string or Path) for results.

        'files_dir' is a destination dir (string or Path) for uploaded files.
        """
        self.json_file = Path(json_file)
        self.files_dir = Path(files_dir)
        self.json_fobj = None

    def __enter__(self):
        if self.json_file.exists():
            raise FileExistsError(f"{self.json_file} already exists")
        self.json_fobj = open(self.json_file, "w")

        if self.files_dir.exists():
            raise FileExistsError(f"{self.files_dir} already exists")
        self.files_dir.mkdir()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.json_fobj:
            self.json_fobj.close()
            self.json_fobj = None

    def report(self, result_line):
        """
        Persistently record a test result.

        'result_line' is a dict in the format specified by RESULTS.md.
        """
        json.dump(result_line, self.json_fobj, indent=None)
        self.json_fobj.write("\n")
        self.json_fobj.flush()

    @contextlib.contextmanager
    def open_tmpfile(self, open_mode=os.O_WRONLY):
        """
        Open an anonymous (name-less) file for writing and yield its file
        descriptor (int) as context, closing it when the context is exited.
        """
        flags = open_mode | os.O_TMPFILE
        fd = os.open(self.files_dir, flags, 0o644)
        try:
            yield fd
        finally:
            os.close(fd)

    def link_tmpfile_to(self, fd, file_name, result_name=None):
        """
        Store a file named 'file_name' in a directory relevant to 'result_name'
        whose 'fd' (a file descriptor) was created by .open_tmpfile().

        This function can be called multiple times with the same 'fd', and
        does not close or otherwise alter the descriptor.

        If 'result_name' is not given, link files to the test (name) itself.
        """
        result_name = util.normalize_path(result_name) if result_name else "."
        # /path/to/files_dir / path/to/subresult / path/to/file.log
        file_path = self.files_dir / result_name / util.normalize_path(file_name)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        linkat(fd, b"", AT_FDCWD, bytes(file_path), AT_EMPTY_PATH)
