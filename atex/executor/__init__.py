class ExecutorError(Exception):
    """
    Raised by class Executor.
    """


class TestSetupError(ExecutorError):
    """
    Raised when the preparation for test execution (ie. pkg install) fails.
    """


class TestAbortedError(ExecutorError):
    """
    Raised when an infrastructure-related issue happened while running a test.
    """


from . import testcontrol  # noqa: F401, E402
from .executor import Executor  # noqa: F401, E402
