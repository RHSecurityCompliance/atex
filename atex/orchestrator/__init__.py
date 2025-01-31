import importlib as _importlib
import pkgutil as _pkgutil
#import threading as _threading


class Orchestrator:
    """
    A scheduler for parallel execution on multiple resources (machines/systems).

    Given a list of Provisioner-derived class instances, it attempts to reserve
    resources and uses them on-demand as they become available, calling run()
    on each.

    Note that run() and report() always run in a separate threads (are allowed
    to block), and may access instance attributes, which are transparently
    guarded by a thread-aware mutex.

    """

    def __init__(self):
        pass
        # TODO: configure via args, max workers, etc.

#    def reserve(self, provisioner):
#        # call provisioner.reserve(), return its return
#        ...

    def add_provisioner(self, provisioner):
        # add to a self.* list of provisioners to be used for getting machines
        ...

    def run(self, provisioner):
        # run tests, if destructive, call provisioner.release()
        # returns anything
        ...

    def report(self):
        # gets return from run
        # writes it out to somewhere else
        ...


_submodules = [
    info.name for info in _pkgutil.iter_modules(__spec__.submodule_search_locations)
]

__all__ = [*_submodules, Orchestrator.__name__]  # noqa: PLE0604


def __dir__():
    return __all__


# lazily import submodules
def __getattr__(attr):
    if attr in _submodules:
        return _importlib.import_module(f".{attr}", __name__)
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
