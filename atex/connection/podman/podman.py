import subprocess

from .. import Connection


class PodmanConnection(Connection):
    def __init__(self, container):
        self.container = container

    def connect(self):
        pass

    def disconnect(self):
        pass

    def cmd(self, command, *, func=subprocess.run, **func_args):
        return func(
            ("podman", "container", "exec", "-i", self.container, *command),
            **func_args,
        )

    def rsync(self, *args, func=subprocess.run, **func_args):
        return func(
            (
                "rsync",
                # use shell to strip off the destination argument rsync passes
                #   cmd[0]=/bin/bash cmd[1]=-c cmd[2]=exec podman ... cmd[3]=destination
                #   cmd[4]=rsync cmd[5]=--server cmd[6]=-vve.LsfxCIvu cmd[7]=. cmd[8]=.
                "-e", f"/bin/bash -c 'exec podman container exec -i {self.container} \"$@\"'",
                *args,
            ),
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )
