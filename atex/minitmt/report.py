import os
import csv
import gzip
import ctypes
import ctypes.util
import contextlib
from pathlib import Path

from .. import util


libc = ctypes.CDLL(ctypes.util.find_library('c'))

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


class CSVReporter(util.LockableClass):
    """
    Stores reported results as a GZIP-ed CSV and files (logs) under a related
    directory.

        with CSVReporter('file/storage/dir', 'results.csv.gz') as reporter:
            sub = reporter.make_subreporter('rhel-9', 'x86_64')
            sub({'name': '/some/test', 'status': 'pass'})
            sub({'name': '/another/test', 'status': 'pass'})
            ...
            sub = reporter.make_subreporter('rhel-9', 'ppc64le')
            ...
            sock = accept_unix_connection()
            reporter.store_file('/some/test', 'debug.log', sock, 1234)
    """
    class _ExcelWithUnixNewline(csv.excel):
        lineterminator = '\n'

    def __init__(self, storage_dir, results_file):
        super().__init__()
        self.storage_dir = Path(storage_dir)
        if self.storage_dir.exists():
            raise FileExistsError(f"{storage_dir} already exists")
        self.results_file = Path(results_file)
        if self.results_file.exists():
            raise FileExistsError(f"{self.results_file} already exists")
        self.storage_dir.mkdir()
        self.csv_writer = None
        self.results_gzip_handle = None

    def __enter__(self):
        f = gzip.open(self.results_file, 'wt', newline='')
        try:
            self.csv_writer = csv.writer(f, dialect=self._ExcelWithUnixNewline)
        except:
            f.close()
            raise
        self.results_gzip_handle = f
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.results_gzip_handle.close()
        self.results_gzip_handle = None
        self.csv_writer = None

    def report(self, distro, arch, status, name, note, *files):
        """
        Persistently write out details of a test result.
        """
        with self.lock:
            self.csv_writer.writerow((distro, arch, status, name, note, *files))

    @staticmethod
    def _normalize_path(path):
        # the magic here is to treat any dangerous path as starting at /
        # and resolve any weird constructs relative to /, and then simply
        # strip off the leading / and use it as a relative path
        path = path.lstrip('/')
        path = os.path.normpath(f'/{path}')
        return path[1:]

    def make_subreporter(self, distro, arch):
        """
        Return a preconfigured reporter instance, suitable for use
        by an Executor.
        """
        def reporter(result_line):
            if 'files' in result_line:
                files = (self._normalize_path(x['name']) for x in result_line['files'])
            else:
                files = ()
            self.report(
                distro, arch, result_line['status'], result_line['name'],
                result_line.get('note', ''), *files,
            )
        return reporter

    def _files_dir(self, result_name):
        dir_path = self.storage_dir / result_name.lstrip('/')
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _files_file(self, result_name, file_name):
        file_name = self._normalize_path(file_name)
        return self._files_dir(result_name) / file_name

    @contextlib.contextmanager
    def open_tmpfile(self, open_mode=os.O_WRONLY):
        flags = open_mode | os.O_TMPFILE
        fd = os.open(self.storage_dir, flags, 0o644)
        try:
            yield fd
        finally:
            os.close(fd)
#    def open_tmpfile(self, result_name, open_mode=os.O_WRONLY):
#        """
#        Open an anonymous (name-less) file for writing, in a directory relevant
#        to 'result_name' and yield its file descriptor (int) as context, closing
#        it when the context is exited.
#        """
#        flags = open_mode | os.O_TMPFILE
#        fd = os.open(self._files_dir(result_name), flags, 0o644)
#        try:
#            yield fd
#        finally:
#            os.close(fd)

    def link_tmpfile_to(self, result_name, file_name, fd):
        """
        Store a file named 'file_name' in a directory relevant to 'result_name'
        whose 'fd' (a file descriptor) was created by open_tmpfile().

        This function can be called multiple times with the same 'fd', and
        does not close or otherwise alter the descriptor.
        """
        final_path = self._files_file(result_name, file_name)
        linkat(fd, b'', AT_FDCWD, bytes(final_path), AT_EMPTY_PATH)

    def store_file(self, result_name, file_name, in_fd, count):
        """
        Read 'count' bytes of binary data from an OS file descriptor 'in_fd'
        and store them under 'result_name' as a file (or relative path)
        named 'file_name', creating it.
        """
        final_path = self._files_file(result_name, file_name)
        # be as efficient as possible, let the kernel handle big data
        out_fd = None
        try:
            out_fd = os.open(final_path, os.O_WRONLY | os.O_CREAT)
            while count > 0:
                written = os.sendfile(out_fd, in_fd, None, count)
                if written == 0:
                    raise RuntimeError(f"got unexpected EOF when receiving {final_path}")
                count -= written
        finally:
            if out_fd:
                os.close(out_fd)
