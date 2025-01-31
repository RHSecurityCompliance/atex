import re
import time


class Duration:
    """
    A helper for parsing, keeping and manipulating test run time based on
    FMF-defined 'duration' attribute.
    """

    def __init__(self, fmf_duration):
        """
        'fmf_duration' is the string specified as 'duration' in FMF metadata.
        """
        duration = self._fmf_to_seconds(fmf_duration)
        self.end = time.monotonic() + duration
        # keep track of only the first 'save' and the last 'restore',
        # ignore any nested ones (as tracked by '_count')
        self.saved = None
        self.saved_count = 0

    @staticmethod
    def _fmf_to_seconds(string):
        match = re.fullmatch(r"([0-9]+)([a-z]*)", string)
        if not match:
            raise RuntimeError(f"'duration' has invalid format: {string}")
        length, unit = match.groups()
        if unit == "m":
            return int(length)*60
        elif unit == "h":
            return int(length)*60*60
        elif unit == "d":
            return int(length)*60*60*24
        else:
            return int(length)

    def set(self, to):
        self.end = time.monotonic() + self._fmf_to_seconds(to)

    def increment(self, by):
        self.end += self._fmf_to_seconds(by)

    def decrement(self, by):
        self.end -= self._fmf_to_seconds(by)

    def save(self):
        if self.saved_count == 0:
            self.saved = self.end - time.monotonic()
        self.saved_count += 1

    def restore(self):
        if self.saved_count > 1:
            self.saved_count -= 1
        elif self.saved_count == 1:
            self.end = time.monotonic() + self.saved
            self.saved_count = 0
            self.saved = None

    def out_of_time(self):
        return time.monotonic() > self.end
