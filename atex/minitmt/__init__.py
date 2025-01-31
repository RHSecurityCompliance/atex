import os
import random

from pathlib import Path

# TODO: TMT_PLAN_ENVIRONMENT_FILE

# TODO: install rsync on the guest as part of setup

# TODO: in Orchestrator, when a Provisioner becomes free, have it pick a test
#       from the appropriate tests[platform] per the Provisioner's platform


def _random_string(length):
    return ''.join(
        random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=length),
    )


class Preparator:
    """
    Set of utilities for preparing a newly acquired/reserved machine for
    running tests, by installing global package requirements, copying all
    tests over, executing tmt plan 'prepare' step, etc.
    """
    def __init__(self, ssh_conn):
        self.conn = ssh_conn

    def copy_tests(self):
        pass

    def run_prepare_scripts(self):
        pass

    def __enter__(self):
        self.conn.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.disconnect()


# TODO: have Executor take a finished Preparator instance as input?
#        - for extracting copied tests location
#        - for extracting TMT_PLAN_ENVIRONMENT_FILE location
#        - etc.


class Executor:
    """
    Helper for running one test on a remote system and processing results
    and uploaded files by that test.
    """
    def __init__(self, fmf_test, ssh_conn):
        self.fmf_test = fmf_test
        self.conn = ssh_conn
        self.remote_socket = self.local_socket = None

    def __enter__(self):
        # generate a (hopefully) unique test control socket name
        # and modify the SSHConn instance to use it
        rand_name = f'atex-control-{_random_string(50)}.sock'
        self.local_socket = Path(os.environ.get('TMPDIR', '/tmp')) / rand_name
        self.remote_socket = f'/tmp/{rand_name}'
        self.conn.options['RemoteForward'] = f'{self.remote_socket} {self.local_socket}'
        self.conn.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.ssh(f'rm -f {self.remote_socket}')
        self.local_socket.unlink()
        self.remote_socket = self.local_socket = None
        self.conn.disconnect()

    # execute all prepares (how:install and how:shell) via ssh
    def prepare(self):
        # TODO: check via __some_attr (named / prefixed after our class)
        #       whether this reserved system has been prepared already ... ?
        #        ^^^^ in Orchestrator
        #
        # TODO: copy root of fmf metadata to some /var/tmp/somedir to run tests from
        #
        # TODO: move prepare out, possibly to class-less function,
        #       we don't want it running over an SSHConn that would set up socket forwarding
        #       only to tear it back down, when executed from Orchestrator for setup only
        #
        # TODO: install rsync
        pass

    def run_script(self, script, duration=None, shell='/bin/bash', **kwargs):
        self.conn.ssh(shell, input=script.encode())

    # run one test via ssh and parse its results on-the-fly,
    # write out logs
    def run_test(self, fmf_test, reporter):
        # TODO: pass environment from test fmf metadata
        # TODO: watch for test duration, etc. metadata
        # TODO: logging of stdout+stderr to hidden file, doing 'ln' from it to
        #       test-named 'testout' files
        #       - generate hidden name suffix via:
        #         ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=20))
        output_logfile = \
            reporter.files_dir(fmf_test.name) / f'.test_output_{self._random_string(50)}.log'
        output_logfile = os.open(reporter.files_dir(fmf_test.name), os.O_WRONLY | os.O_CREAT)
        try:
            #self.conn.ssh(
            pass
        finally:
            os.close(output_logfile)
        # TODO: create temp dir on remote via 'mktemp -d', then call
        #       self.conn.add_remote_forward(...) with socket path inside that tmpdir

# TODO: run tests by passing stdout/stderr via pre-opened fd so we don't handle it in code

# TODO: read unix socket as nonblocking, check test subprocess.Popen proc status every 0.1sec
