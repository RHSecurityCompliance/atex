import subprocess
from collections.abc import Callable, Sequence

from .. import Connection


class PodmanConnection(Connection):
    def __init__(self, container: str):
        self.container = container

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def cmd(self, command: Sequence, func: Callable = subprocess.run, **func_args):
        return func(
            ("podman", "container", "exec", "-i", self.container, *command),
            **func_args,
        )

    def rsync(self, *args: str, func: Callable = subprocess.run, **func_args):
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
