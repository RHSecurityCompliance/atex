import importlib as _importlib
import pkgutil as _pkgutil
import inspect as _inspect

__all__ = []


def __dir__():
    return __all__


# this is the equivalent of 'from .submod import *' for all submodules
# (function to avoid polluting global namespace with extra variables)
def _import_submodules():
    for info in _pkgutil.iter_modules(__spec__.submodule_search_locations):
        mod = _importlib.import_module(f".{info.name}", __name__)

        # if the module defines __all__, just use it
        if hasattr(mod, "__all__"):
            keys = mod.__all__
        else:
            # https://docs.python.org/3/reference/executionmodel.html#binding-of-names
            keys = (x for x in dir(mod) if not x.startswith("_"))

        for key in keys:
            attr = getattr(mod, key)

            # avoid objects that belong to other known modules
            # (ie. imported function from another util module)
            if hasattr(attr, "__module__"):
                if attr.__module__ != mod.__name__:
                    continue
            # avoid some common pollution / imports
            # (we don't want subpackages in here anyway)
            if _inspect.ismodule(attr):
                continue
            # do not override already processed objects (avoid duplicates)
            assert key not in __all__, f"tried to override already-imported '{key}'"

            globals()[key] = attr
            __all__.append(key)


_import_submodules()
