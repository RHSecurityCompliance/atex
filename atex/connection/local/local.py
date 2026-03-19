import subprocess

from ... import util
from .. import Connection


class LocalConnection(Connection):
    def connect(self, block=True):
        pass

    def disconnect(self):
        pass

    def cmd(self, command, *, func=util.subprocess_run, **func_args):  # noqa: PLR6301
        return func(command, **func_args)

    def rsync(self, *args, func=util.subprocess_run, **func_args):  # noqa: PLR6301
        return func(
            # rsync passes the literal 'remote' from the 'remote:foo/bar' arg
            # as first arg to -e, so use shell to strip it off and exec rsync
            ("rsync", "-e", "/bin/bash -c 'shift; exec \"$@\"'", *args),
            check=True,
            stdin=subprocess.DEVNULL,
            **func_args,
        )
