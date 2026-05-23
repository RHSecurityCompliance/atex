import re
from pathlib import PurePath


def normalize_path(src):
    """
    Transform a potentially dangerous path (leading slash, relative `../../../`
    leading beyond parent, etc.) to a safe one.

    Always returns a relative path.
    """
    # replace control characters (null, newline, tab, etc.) with underscores
    src = re.sub(r"[\x00-\x1f\x7f-\x9f]", "_", str(src))
    parts = (
        part for part in PurePath(src).parts
        if part not in (".","..") and "/" not in part
    )
    return PurePath(*parts)
