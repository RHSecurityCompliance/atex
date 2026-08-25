import logging

NULL_LOGGER = logging.getLogger("atex._null")

# avoid anything standard reaching the handler (make no-op cheap)
NULL_LOGGER.setLevel(logging.CRITICAL + 1)

# in case anybody specifies above-CRITICAL by hand, swallow it too
NULL_LOGGER.addHandler(logging.NullHandler())

# don't pass the record to parents, handle/discard it in here
NULL_LOGGER.propagate = False

# work around __module__ based detection in __init__.py
__all__ = ("NULL_LOGGER",)
