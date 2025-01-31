from . import util


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
