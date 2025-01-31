import os


def normalize_path(path):
    """
    Transform a potentially dangerous path (leading slash, relative ../../../
    leading beyond parent, etc.) to a safe one.

    Always returns a relative path.
    """
    # the magic here is to treat any dangerous path as starting at /
    # and resolve any weird constructs relative to /, and then simply
    # strip off the leading / and use it as a relative path
    path = path.lstrip("/")
    path = os.path.normpath(f"/{path}")
    return path[1:]
