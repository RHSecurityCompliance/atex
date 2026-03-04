from pathlib import PurePath


def normalize_path(src):
    """
    Transform a potentially dangerous path (leading slash, relative `../../../`
    leading beyond parent, etc.) to a safe one.

    Always returns a relative path.
    """
    parts = (
        part for part in PurePath(src).parts
        if part not in (".","..") and "/" not in part
    )
    return PurePath(*parts)
