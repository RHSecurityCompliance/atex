import importlib
import inspect
import pkgutil

__all__ = []


def __dir__():
    return __all__


# this is the equivalent of 'from .submod import *' for all submodules
# (function to avoid polluting global namespace with extra variables)
def _import_submodules():
    def import_obj(key, attr):
        # do not override already processed objects (avoid duplicates)
        assert key not in __all__, f"tried to override already-imported '{key}'"
        globals()[key] = attr
        __all__.append(key)

    for info in pkgutil.iter_modules(__spec__.submodule_search_locations):
        mod = importlib.import_module(f".{info.name}", __name__)

        # if the module defines __all__, just use it
        if hasattr(mod, "__all__"):
            for key in mod.__all__:
                import_obj(key, getattr(mod, key))

        else:
            for key in dir(mod):
                # https://docs.python.org/3/reference/executionmodel.html#binding-of-names
                if key.startswith("_"):
                    continue
                # import any classes or functions which are directly defined
                # by the module, avoiding any foreign imports
                attr = getattr(mod, key)
                if inspect.isroutine(attr) or inspect.isclass(attr):
                    if attr.__module__ == mod.__name__:
                        import_obj(key, attr)
                # anything else is unsafe to import automatically


_import_submodules()
