#!/usr/bin/python3

import collections
import logging

_instances = collections.Counter()


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
        logger = logging.getLogger(f"{name}.{_instances[name]}")
        _instances[name] += 1
        return logger

    return get_logger
