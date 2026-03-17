import collections

from ...executor.fmf.metadata import duration_to_seconds, listlike


def LimitedRerunsMixin(reruns, cond=lambda code: code != 0):  # noqa: N802
    """
    Return a mixin class that limits test reruns by a counter per test name.

    - `reruns` is the maximum number of reruns for each test.

    - `cond` is a callable with a text exit code passed as argument,
      returning True if the test should be rerun, False if it should not.
    """
    class LimitedRerunsMixin:
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._counter = collections.Counter()

        def should_be_rerun(self, info, /):
            if self._counter[info.test_name] >= reruns:
                return False
            if not cond(info.exit_code):
                return False
            self._counter[info.test_name] += 1
            return True

    return LimitedRerunsMixin


def FMFDurationMixin(fmf_tests):  # noqa: N802
    """
    Return a mixin class that overrides next_test() to prefer longer-running
    tests, based on the 'duration' FMF metadata key.

    Note that this skips over tests with no explicit 'duration', passing them
    to the next mixin (or base class).

    - `fmf_tests` is a class FMFTests instance with all tests.
    """
    class FMFDurationMixin:
        def next_test(self, to_run, previous, /):
            # only pick tests with 'duration' explicitly set
            best = max(
                (name for name in to_run if "duration" in fmf_tests.tests[name]),
                key=lambda name: duration_to_seconds(fmf_tests.tests[name]["duration"]),
                default=None,
            )
            if best is not None:
                return best

            # pass on any duration-unset tests
            return super().next_test(to_run, previous)

    return FMFDurationMixin


def FMFPriorityMixin(fmf_tests):  # noqa: N802
    """
    Return a mixin class that reorders tests based on 'extra-priority'
    FMF metadata key. Positive values run sooner, negative values run later.

    Note that this skips over tests with no explicit 'extra-priority' or with
    it being 0, passing them to the next mixin (or base class).

    - `fmf_tests` is a class FMFTests instance with all tests.
    """
    class FMFPriorityMixin:
        def next_test(self, to_run, previous, /):
            def priority(name):
                return fmf_tests.tests[name].get("extra-priority", 0)

            # this will be >0 if there are higher-than-0 priority tests,
            # and <0 if there are no 0-priority tests left
            # - in either case, we want the highest priority
            best = max(to_run, key=priority)
            if priority(best) != 0:
                return best

            # only tests with 0 priority left (or with it unspecified),
            # pass on the original order
            return super().next_test(to_run, previous)

    return FMFPriorityMixin


def FMFDestructiveMixin(fmf_tests):  # noqa: N802
    """
    Return a mixin class that checks tests for a 'destructive' tag in the test
    metadata, and always destroys the Remote after such tests, even on tests
    that exit with 0 (success).

    - `fmf_tests` is a class FMFTests instance with all tests.
    """
    class FMFDestructiveMixin:
        def destructive(self, info, /):
            tags = listlike(fmf_tests.tests[info.test_name], "tag")
            if "destructive" in tags:
                return True
            return super().destructive(info)

    return FMFDestructiveMixin
