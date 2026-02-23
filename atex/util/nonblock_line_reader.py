import os


class BufferFullError(Exception):
    """
    Returned by NonblockLineReader when the line is longer than `max_len`
    (as specified via `__init__` args to NonblockLineReader).
    """


class NonblockLineReader:
    """
    Kind of like io.BufferedReader but capable of reading from non-blocking
    sources (both `O_NONBLOCK` sockets and `os.set_blocking(False)`
    descriptors), re-assembling full lines from (potentially) multiple
    `read()` calls.
    It also takes a file descriptor (not a file-like object).

    It can take extra care to read one-byte-at-a-time (with `read_len=1`)
    to not read (and buffer) more data from the source descriptor, allowing it
    to be used for in-kernel move, such as via `os.sendfile()` or `os.splice()`.
    """

    def __init__(self, src, max_len=4096, read_len=1024):
        """
        - `src` is an opened file descriptor (integer).

        - `max_len` is a maximum potential line length, incl. the newline
          character - if reached, a BufferFullError is raised.
        """
        self.src = src
        self.read_len = read_len
        self.eof = False
        self.buffer = bytearray(max_len)
        self.bytes_read = 0

    def readline(self):
        r"""
        Read a line and return it, without the `\n` terminating character,
        clearing the internal buffer upon return.

        Returns None if nothing could be read (BlockingIOError) or if EOF
        was reached.
        """
        while self.bytes_read < len(self.buffer):
            try:
                data = os.read(self.src, self.read_len)
            except BlockingIOError:
                return None

            # stream EOF
            if len(data) == 0:
                self.eof = True
                return None

            self.buffer[self.bytes_read : self.bytes_read + len(data)] = data
            self.bytes_read += len(data)

            if (idx := self.buffer.find(b"\n", 0, self.bytes_read)) != -1:
                line = bytes(self.buffer[:idx])
                remainder = self.bytes_read - idx - 1  # \n
                self.buffer[:remainder] = memoryview(self.buffer)[idx+1 : self.bytes_read]
                self.bytes_read -= idx+1
                return line

        raise BufferFullError(f"line buffer reached {len(self.buffer)} bytes")
