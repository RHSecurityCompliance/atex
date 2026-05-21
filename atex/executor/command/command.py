import json
import subprocess
from pathlib import Path

from ... import util
from .. import Executor

get_logger = util.get_loggers("atex.executor.command")


class CommandExecutor(Executor):
    """
    - `connection` is a connected class Connection instance.

    - `tests` is a dict mapping test names (strings) to commands
      (tuple/list), ie. `{"mytest": ("echo", "hello")}`.
    """

    def __init__(self, connection, tests):
        self.logger = get_logger()
        self.conn = connection
        self.tests = tests

    def run_test(self, test_name, artifacts, *, output="output.txt"):
        """
        Positional arguments are the same as class Executor.

        - `output` is a file name inside artifacts for capturing stdout/stderr
          of the executed command.
        """
        if test_name not in self.tests:
            raise ValueError(f"'{test_name}' doesn't exist")

        command = self.tests[test_name]
        self.logger.info(f"'{test_name}': running {command}, {artifacts=}")

        artifacts = Path(artifacts)
        files_dir = artifacts / "files"
        files_dir.mkdir()

        proc = self.conn.cmd(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        output_file = files_dir / util.normalize_path(output)
        output_file.write_bytes(proc.stdout)

        status = self.evaluate(proc.returncode, output_file)

        result = {"status": status, "files": (output,)}
        (artifacts / "results").write_text(
            json.dumps(result, indent=None) + "\n",
        )

        return proc.returncode

    def evaluate(self, exit_code, output):  # noqa: PLR6301, ARG002
        """
        Determine the result status of a finished command.

        - `exit_code` is the integer exit code of the command.

        - `output` is a Path to the file containing the captured
          stdout and stderr of the command.

        Returns a status string for the result, ie. `pass`, `fail`, etc.
        """
        return "pass" if exit_code == 0 else "fail"

    def start(self):
        self.logger.debug(f"starting: {self}")

    def stop(self):
        self.logger.debug(f"stopping: {self}")

    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name}({self.conn}, {len(self.tests)} tests)"

    # TODO: added for AdHocAggregator compatibility, remove it after removing
    #       the non-standard .cancel() from FMFExecutor
    def cancel(self):
        pass
