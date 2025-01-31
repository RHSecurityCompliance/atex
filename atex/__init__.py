"""
Ad-hoc Test EXecutor

Some documentation here.
"""

import importlib as _importlib
import pkgutil as _pkgutil

__all__ = [
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
]


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    # importing a module known to exist
    if attr in __all__:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
