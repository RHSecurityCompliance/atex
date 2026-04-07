import json
import logging
import os

from ... import util


class BadControlError(Exception):
    """
    Raised by TestControl when abnormalities are detected in the control stream,
    such as invalid syntax, unknown control word, or bad or unexpected data for
    any given control word.
    """


class BadReportJSONError(BadControlError):
    """
    Raised on a syntactical or semantical error caused by the test not following
    the TEST_CONTROL.md specification when passing JSON data to the 'result'
    control word.
    """


class TestControl:
    """
    An implementation of the protocol described by TEST_CONTROL.md,
    processing test-issued commands, results and uploaded files.

    - `reporter` is an instance of class Reporter all the results
      and uploaded files will be written to.

    - `duration` is a class Duration instance.

    - `control_fd` is a non-blocking file descriptor to be read.

    - `logger` is a logging-API object to log messages to.
    """

    def __init__(self, *, reporter, duration, control_fd=None, logger=None):
        self.logger = logger or logging.getLogger("atex")

        self.reporter = reporter
        self.duration = duration
        if control_fd is not None:
            self.control_fd = control_fd
            self.stream = util.NonblockLineReader(control_fd, read_len=1)
        else:
            self.control_fd = None
            self.stream = None
        self.eof = False
        self.in_progress = None
        self.exit_code = None
        self.disconnect_received = False

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
        self.stream = util.NonblockLineReader(new_fd, read_len=1)

    def process(self):
        """
        Read from the control file descriptor and potentially perform any
        appropriate action based on commands read from the test.
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
        except util.BufferFullError as e:
            raise BadControlError(str(e)) from None

        self.logger.debug(f"control line: {line} // eof: {self.stream.eof}")

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

        self.logger.debug(f"decoded word: {word} / arg: {arg}")

        if word == "result":
            parser = self._parser_result(arg)
        elif word == "duration":
            parser = self._parser_duration(arg)
        elif word == "exitcode":
            parser = self._parser_exitcode(arg)
        elif word == "disconnect":
            parser = self._parser_disconnect(arg)
        elif word == "noop":
            parser = self._parser_noop(arg)
        else:
            raise BadControlError(f"unknown control word: {word}")

        try:
            next(parser)
            # parser not done parsing, run it next time we're called
            self.in_progress = parser
        except StopIteration:
            pass

    def _parser_result(self, arg):
        try:
            json_length = int(arg)
        except ValueError as e:
            raise BadControlError(f"reading json length: {str(e)}") from None

        # read the full JSON
        json_data = bytearray()
        while True:
            try:
                chunk = os.read(self.control_fd, json_length)
            except BlockingIOError:
                yield
                continue
            if chunk == b"":
                raise BadControlError(f"EOF when reading data, got so far: {json_data}")
            json_data += chunk
            json_length -= len(chunk)
            if json_length <= 0:
                break
            yield

        # convert to native python dict
        try:
            result = json.loads(json_data)
        except json.decoder.JSONDecodeError as e:
            raise BadReportJSONError(f"JSON decode: {str(e)} caused by: {json_data}") from None

        self.logger.debug(f"parsed result: {result}")

        name = result.get("name")

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

            with self.reporter.open_file(file_name, os.O_WRONLY | os.O_CREAT, name) as fd:
                # Linux can't do splice(2) on O_APPEND fds, so we open it above
                # as O_WRONLY and just seek to the end, simulating append
                os.lseek(fd, 0, os.SEEK_END)

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

        # let class Reporter handle everything else
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

    def _parser_disconnect(self, _):
        self.disconnect_received = True
        # also reset exitcode, let a reconnected test set it
        self.exit_code = None
        # pretend to be a generator
        if False:
            yield

    @staticmethod
    def _parser_noop(_):
        # pretend to be a generator
        if False:
            yield
