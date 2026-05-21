import subprocess

from .. import Connection


class LocalConnection(Connection):
    """
    - `cwd` changes the working directory for `.cmd()` and `.rsync()`.
    """

    def __init__(self, *, cwd=None):
        self.cwd = cwd

    def connect(self):
        pass

    def disconnect(self):
        pass

    def cmd(self, command, *, func=subprocess.run, **func_args):
        func_args.setdefault("cwd", self.cwd)
        return func(command, **func_args)

    def rsync(self, *args, func=subprocess.run, **func_args):
        return func(
            # rsync passes the literal 'remote' from the 'remote:foo/bar' arg
            # as first arg to -e, so use shell to strip it off and exec rsync
            ("rsync", "-e", "/bin/bash -c 'exec \"$@\"'", *args),
            **{"check": True, "stdin": subprocess.DEVNULL, "cwd": self.cwd} | func_args,
        )
