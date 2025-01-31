import signal
import functools
import contextlib


class TestTimeoutError(Exception):
    pass


def _sigalrm_handler(signum, frame):  # noqa: ARG001
    raise TestTimeoutError("Test timed out")


def timeout(seconds):
    """
    Raise TestTimeoutError after 'seconds' seconds unless the wrapped function
    exits first. Usable as a function decorator:

        @timeout(60)
        def myfunc():
            time.sleep(61)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            old_handler = signal.signal(signal.SIGALRM, _sigalrm_handler)
            signal.alarm(seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        return wrapper
    return decorator


@contextlib.contextmanager
def Timeout(seconds):  # noqa: N802
    """
    Raise TestTimeoutError after 'seconds' seconds unless the context manager
    block ends first.

        with Timeout(60):
            time.sleep(61)
    """
    old_handler = signal.signal(signal.SIGALRM, _sigalrm_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
