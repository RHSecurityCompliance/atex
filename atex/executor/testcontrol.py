import os
import collections
import json

from .. import util


class BufferFullError(Exception):
    pass


class NonblockLineReader:
    """
    Kind of like io.BufferedReader but capable of reading from non-blocking
    sources (both O_NONBLOCK sockets and os.set_blocking(False) descriptors),
    re-assembling full lines from (potentially) multiple read() calls.

    It also takes a file descriptor (not a file-like object) and takes extra
    care to read one-byte-at-a-time to not read (and buffer) more data from the
    source descriptor, allowing it to be used for in-kernel move, such as via
    os.sendfile() or os.splice().
    """

    def __init__(self, src, maxlen=4096):
        """
        'src' is an opened file descriptor (integer).

        'maxlen' is a maximum potential line length, incl. the newline
        character - if reached, a BufferFullError is raised.
        """
        self.src = src
        self.eof = False
        self.buffer = bytearray(maxlen)
        self.bytes_read = 0

    def readline(self):
        r"""
        Read a line and return it, without the '\n' terminating character,
        clearing the internal buffer upon return.

        Returns None if nothing could be read (BlockingIOError) or if EOF
        was reached.
        """
        while self.bytes_read < len(self.buffer):
            try:
                data = os.read(self.src, 1)
            except BlockingIOError:
                return None

            # stream EOF
            if len(data) == 0:
                self.eof = True
                return None

            char = data[0]

            if char == 0x0a:  # \n
                line = self.buffer[0:self.bytes_read]
                self.bytes_read = 0
                return line
            else:
                self.buffer[self.bytes_read] = char
                self.bytes_read += 1

        raise BufferFullError(f"line buffer reached {len(self.buffer)} bytes")

    def clear(self):
        """
        Clear the internal buffer, clearing any partially-read line data.
        """
        self.bytes_read = 0


class BadControlError(Exception):
    """
    Raised by TestControl when abnormalities are detected in the control stream,
    such as invalid syntax, unknown control word, or bad or unexpected data for
    any given control word.
    """
    pass


class BadReportJSONError(BadControlError):
    """
    Raised on a syntactical or semantical error caused by the test not following
    the TEST_CONROL.md specification when passing JSON data to the 'result'
    control word.
    """
    pass


class TestControl:
    """
    An implementation of the protocol described by TEST_CONTROL.md,
    processing test-issued commands, results and uploaded files.
    """

    def __init__(self, *, reporter, duration, control_fd=None):
        """
        'control_fd' is a non-blocking file descriptor to be read.

        'reporter' is an instance of class Reporter all the results
        and uploaded files will be written to.

        'duration' is a class Duration instance.
        """
        self.reporter = reporter
        self.duration = duration
        if control_fd:
            self.control_fd = control_fd
            self.stream = NonblockLineReader(control_fd)
        else:
            self.control_fd = None
            self.stream = None
        self.eof = False
        self.in_progress = None
        self.partial_results = collections.defaultdict(dict)
        self.exit_code = None
        self.reconnect = None
        self.nameless_result_seen = False

    def reassign(self, new_fd):
        """
        Assign a new control file descriptor to read test control from,
        replacing a previous one. Useful on test reconnect.
        """
        err = "tried to assign new control fd while"
        if self.in_progress:
            raise BadControlError(f"{err} old one is reading non-control binary data")
        elif self.stream and self.stream.bytes_read != 0:
            raise BadControlError(f"{err} old one is in the middle of reading a control line")
        self.eof = False
        self.control_fd = new_fd
        self.stream = NonblockLineReader(new_fd)

    def process(self):
        """
        Read from the control file descriptor and potentially perform any
        appropriate action based on commands read from the test.

        Returns True if there is more data expected, False otherwise
        (when the control file descriptor reached EOF).
        """
        # if a parser operation is in progress, continue calling it,
        # avoid reading a control line
        if self.in_progress:
            try:
                next(self.in_progress)
                return
            except StopIteration:
                # parser is done, continue on to a control line
                self.in_progress = None

        try:
            line = self.stream.readline()
        except BufferFullError as e:
            raise BadControlError(str(e)) from None

        util.debug(f"got control line: {line} // eof: {self.stream.eof}")

        if self.stream.eof:
            self.eof = True
            return
        # partial read or BlockingIOError, try next time
        if line is None:
            return
        elif len(line) == 0:
            raise BadControlError(r"empty control line (just '\n')")

        line = line.decode()
        word, _, arg = line.partition(" ")

        if word == "result":
            parser = self._parser_result(arg)
        elif word == "duration":
            parser = self._parser_duration(arg)
        elif word == "exitcode":
            parser = self._parser_exitcode(arg)
        elif word == "reconnect":
            parser = self._parser_reconnect(arg)
        else:
            raise BadControlError(f"unknown control word: {word}")

        try:
            next(parser)
            # parser not done parsing, run it next time we're called
            self.in_progress = parser
        except StopIteration:
            pass

    @classmethod
    def _merge(cls, dst, src):
        """
        Merge a 'src' dict into 'dst', using the rules described by
        TEST_CONTROL.md for 'Partial results'.
        """
        for key, value in src.items():
            # delete existing if new value is None (JSON null)
            if value is None and key in dst:
                del dst[key]
                continue
            # add new key
            elif key not in dst:
                dst[key] = value
                continue

            orig_value = dst[key]
            # different type - replace
            if type(value) is not type(orig_value):
                dst[key] = value
                continue

            # nested dict, merge it recursively
            if isinstance(value, dict):
                cls._merge(orig_value, value)
            # extensible list-like iterable, extend it
            elif isinstance(value, (tuple, list)):
                orig_value += value
            # overridable types, doesn't make sense to extend them
            elif isinstance(value, (str, int, float, bool, bytes, bytearray)):
                dst[key] = value
            # set-like, needs unioning
            elif isinstance(value, set):
                orig_value.update(value)
            else:
                raise BadReportJSONError(f"cannot merge type {type(value)}")

    def _parser_result(self, arg):
        try:
            json_length = int(arg)
        except ValueError as e:
            raise BadControlError(f"reading json length: {str(e)}") from None

        # read the full JSON
        json_data = bytearray()
        while json_length > 0:
            try:
                chunk = os.read(self.control_fd, json_length)
            except BlockingIOError:
                yield
                continue
            if chunk == b"":
                raise BadControlError("EOF when reading data")
            json_data += chunk
            json_length -= len(chunk)
            yield

        # convert to native python dict
        try:
            result = json.loads(json_data)
        except json.decoder.JSONDecodeError as e:
            raise BadReportJSONError(f"JSON decode: {str(e)} caused by: {json_data}") from None

        # note that this may be None (result for the test itself)
        name = result.get("name")
        if not name:
            self.nameless_result_seen = True

        # upload files
        for entry in result.get("files", ()):
            file_name = entry.get("name")
            file_length = entry.get("length")
            if not file_name or file_length is None:
                raise BadReportJSONError(f"file entry missing 'name' or 'length': {entry}")
            try:
                file_length = int(file_length)
            except ValueError as e:
                raise BadReportJSONError(f"file entry {file_name} length: {str(e)}") from None

            try:
                with self.reporter.open_file(file_name, name) as f:
                    fd = f.fileno()
                    while file_length > 0:
                        try:
                            # try a more universal sendfile first, fall back to splice
                            try:
                                written = os.sendfile(fd, self.control_fd, None, file_length)
                            except OSError as e:
                                if e.errno == 22:  # EINVAL
                                    written = os.splice(self.control_fd, fd, file_length)
                                else:
                                    raise
                        except BlockingIOError:
                            yield
                            continue
                        if written == 0:
                            raise BadControlError("EOF when reading data")
                        file_length -= written
                        yield
            except FileExistsError:
                raise BadReportJSONError(f"file '{file_name}' already exists") from None

        # either store partial result + return,
        # or load previous partial result and merge into it
        partial = result.get("partial", False)
        if partial:
            # do not store the 'partial' key in the result
            del result["partial"]
            # note that nameless result will get None as dict key,
            # which is perfectly fine
            self._merge(self.partial_results[name], result)
            # partial = do nothing
            return

        # if previously-stored partial result exist, merge the current one
        # into it, but then use the merged result
        # - avoid .get() or __getitem__() on defaultdict, it would create
        #   a new key with an empty value if there was no partial result
        if name in self.partial_results:
            partial_result = self.partial_results[name]
            del self.partial_results[name]
            self._merge(partial_result, result)
            result = partial_result

        if "testout" in result:
            testout = result.get("testout")
            if not testout:
                raise BadReportJSONError("'testout' specified, but empty")
            try:
                self.reporter.link_testout(testout, name)
            except FileExistsError:
                raise BadReportJSONError(f"file '{testout}' already exists") from None

        self.reporter.report(result)

    def _parser_duration(self, arg):
        if not arg:
            raise BadControlError("duration argument empty")
        # increment/decrement
        if arg[0] == "+":
            self.duration.increment(arg[1:])
        elif arg[0] == "-":
            self.duration.decrement(arg[1:])
        # save/restore
        elif arg == "save":
            self.duration.save()
        elif arg == "restore":
            self.duration.restore()
        else:
            self.duration.set(arg)
        # pretend to be a generator
        if False:
            yield

    def _parser_exitcode(self, arg):
        if not arg:
            raise BadControlError("exitcode argument empty")
        try:
            code = int(arg)
        except ValueError:
            raise BadControlError(f"'{arg}' is not an integer exit code") from None
        self.exit_code = code
        # pretend to be a generator
        if False:
            yield

    def _parser_reconnect(self, arg):
        if not arg:
            self.reconnect = "once"
        elif arg == "always":
            self.reconnect = "always"
        else:
            raise BadControlError(f"unknown reconnect arg: {arg}")
        # pretend to be a generator
        if False:
            yield
