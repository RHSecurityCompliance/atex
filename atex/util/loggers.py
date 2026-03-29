#!/usr/bin/python3

import logging
import threading

_instances = {}
_lock = threading.RLock()


def get_loggers(name):
    """
    Generate a unique logger instance number for each invocation of the returned
    logger factory. Useful for differentiating class instances.

    The number is appended after the logger `name`, separated by `.`, to still
    allow `getLogger(name)` customization (ie. `.setLevel()`) by the user.

    Ie.
        logging.basicConfig(format="%(name)s: %(message)s")

        factory = get_loggers("foo.bar")

        first = factory()
        second = factory()

        logging.getLogger("foo.bar").setLevel(logging.INFO)

        first.info("abc")   # foo.bar.0: abc
        second.info("abc")  # foo.bar.1: abc
    """
    def get_logger():
        with _lock:
            nr = _instances.get(name, 0)
            _instances[name] = nr + 1
        return logging.getLogger(f"{name}.{nr}")

    return get_logger
