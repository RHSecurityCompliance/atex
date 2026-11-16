from ...executor.fmf.metadata import duration_to_seconds, listlike


def LimitedRerunsMixin(reruns, cond=lambda code: code != 0):  # noqa: N802
    """
    Return a mixin class that limits test reruns by a counter per test name.

    - `reruns` is the maximum number of reruns for each test.

    - `cond` is a callable with a test exit code passed as argument,
      returning True if the test should be rerun, False if it should not.
    """
    class LimitedRerunsMixin:
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._counter = {}

        def should_be_rerun(self, info, /):
            past_reruns = self._counter.get(info.test_name, 0)
            if past_reruns >= reruns:
                return False
            if info.exception or cond(info.exit_code):
                self._counter[info.test_name] = past_reruns + 1
                return True
            return False

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
                (name for name in to_run if "duration" in fmf_tests.data[name]),
                key=lambda name: duration_to_seconds(fmf_tests.data[name]["duration"]),
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
                return fmf_tests.data[name].get("extra-priority", 0)

            best = max(to_run, key=priority)
            highest_prio = priority(best)

            # tests with a positive prio run first; pick highest-prio one
            if highest_prio > 0:
                return best
            # only zero or lower prio left, delegate any zero-prio in orig order
            # - these must not contain non-zero-prio tests, those run after
            elif highest_prio == 0:
                zero_prio = [name for name in to_run if priority(name) == 0]
                return super().next_test(zero_prio, previous)
            # only negative priorities remain; pick highest-prio one
            else:
                return best

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
            tags = listlike(fmf_tests.data[info.test_name], "tag")
            if "destructive" in tags:
                return True
            return super().destructive(info)

    return FMFDestructiveMixin
