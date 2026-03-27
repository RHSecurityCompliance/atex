import subprocess
from collections.abc import Callable, Sequence

from .. import Connection


class LocalConnection(Connection):
    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def cmd(self, command: Sequence, func: Callable = subprocess.run, **func_args):  # noqa: PLR6301
        return func(command, **func_args)

    def rsync(self, *args: str, func: Callable = subprocess.run, **func_args):  # noqa: PLR6301
        return func(
            # rsync passes the literal 'remote' from the 'remote:foo/bar' arg
            # as first arg to -e, so use shell to strip it off and exec rsync
            ("rsync", "-e", "/bin/bash -c 'shift; exec \"$@\"'", *args),
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )
