import time

from .metadata import duration_to_seconds


class Duration:
    """
    A helper for parsing, keeping and manipulating test run time based on
    FMF-defined 'duration' attribute.

    - `fmf_duration` is the string specified as 'duration' in FMF metadata.
    """

    def __init__(self, fmf_duration):
        duration = duration_to_seconds(fmf_duration)
        self._end = time.monotonic() + duration
        # keep track of only the first 'save' and the last 'restore',
        # ignore any nested ones (as tracked by 'saved_count')
        self._saved = None
        self._saved_count = 0

    def set(self, to):
        self._end = time.monotonic() + duration_to_seconds(to)

    def increment(self, by):
        self._end += duration_to_seconds(by)

    def decrement(self, by):
        self._end -= duration_to_seconds(by)

    def save(self):
        if self._saved_count == 0:
            self._saved = self._end - time.monotonic()
        self._saved_count += 1

    def restore(self):
        if self._saved_count > 1:
            self._saved_count -= 1
        elif self._saved_count == 1:
            self._end = time.monotonic() + self._saved
            self._saved_count = 0
            self._saved = None

    def out_of_time(self):
        return time.monotonic() > self._end
