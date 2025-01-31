"""
Connection API implementation using the 'podman' CLI client.
"""

import subprocess

from .. import util
from . import Connection


class PodmanConnError(ConnectionError):
    pass


class PodmanConn(Connection):
    """
    Implements the Connection API via 'podman container exec' on an
    already-running container, it does not handle any image pulling,
    container creation, starting or stopping.
    """

#    def __init__(self, container, *, user=None, workdir=None):
#        """
#        'container' is a string with either the full or partial podman
#        container ID, or a container name, as recognized by podman CLI.
#
#        'user' is a string with a username or UID, possibly including a GID,
#        passed to the podman CLI as --user.
#
#        'workdir' is a string specifying the CWD inside the container.
#        """
    def __init__(self, container):
        self.container = container

    def connect(self, block=True):
        pass

    def disconnect(self):
        pass

    # have options as kwarg to be compatible with other functions here
    def cmd(self, command, *, func=util.subprocess_run, **func_args):
        return func(
            ("podman", "container", "exec", "-i", self.container, *command),
            skip_frames=1,
            **func_args,
        )

    def rsync(self, *args, func=util.subprocess_run, **func_args):
        return func(
            (
                "rsync",
                # use shell to strip off the destination argument rsync passes
                #   cmd[0]=/bin/bash cmd[1]=-c cmd[2]=exec podman ... cmd[3]=destination
                #   cmd[4]=rsync cmd[5]=--server cmd[6]=-vve.LsfxCIvu cmd[7]=. cmd[8]=.
                "-e", f"/bin/bash -c 'exec podman container exec -i {self.container} \"$@\"'",
                *args,
            ),
            skip_frames=1,
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )
