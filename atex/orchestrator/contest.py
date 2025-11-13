from .. import util
from .adhoc import AdHocOrchestrator


# copy/pasted from the Contest repo, lib/virt.py
def calculate_guest_tag(tags):
    if "snapshottable" not in tags:
        return None
    name = "default"
    if "with-gui" in tags:
        name += "_gui"
    if "uefi" in tags:
        name += "_uefi"
    if "fips" in tags:
        name += "_fips"
    return name


class ContestOrchestrator(AdHocOrchestrator):
    """
    Orchestrator for the Contest test suite:
        https://github.com/RHSecurityCompliance/contest

    Includes SCAP content upload via rsync and other Contest-specific
    optimizations (around VM snapshots and scheduling).
    """
    content_dir_on_remote = "/root/upstream-content"

    def __init__(self, *args, content_dir, **kwargs):
        self.content_dir = content_dir
        super().__init__(*args, **kwargs)

    def run_setup(self, sinfo):
        super().run_setup(sinfo)
        # upload pre-built content
        sinfo.remote.rsync(
            "-r", "--delete", "--exclude=.git/",
            f"{self.content_dir}/",
            f"remote:{self.content_dir_on_remote}",
            func=util.subprocess_log,
        )

    @classmethod
    def next_test(cls, to_run, all_tests, previous):
        # fresh remote, prefer running destructive tests (which likely need
        # clean OS) to get them out of the way and prevent them from running
        # on a tainted OS later
        if type(previous) is AdHocOrchestrator.SetupInfo:
            for next_name in to_run:
                next_tags = all_tests[next_name].get("tag", ())
                util.debug(f"considering next_test for destructivity: {next_name}")
                if "destructive" in next_tags:
                    util.debug(f"chosen next_test: {next_name}")
                    return next_name

        # previous test was run and finished non-destructively,
        # try to find a next test with the same Contest lib.virt guest tags
        # as the previous one, allowing snapshot reuse by Contest
        elif type(previous) is AdHocOrchestrator.FinishedInfo:
            finished_tags = all_tests[previous.test_name].get("tag", ())
            util.debug(f"previous finished test on {previous.remote}: {previous.test_name}")
            # if Guest tag is None, don't bother searching
            if finished_guest_tag := calculate_guest_tag(finished_tags):
                for next_name in to_run:
                    util.debug(f"considering next_test with tags {finished_tags}: {next_name}")
                    next_tags = all_tests[next_name].get("tag", ())
                    next_guest_tag = calculate_guest_tag(next_tags)
                    if next_guest_tag and finished_guest_tag == next_guest_tag:
                        util.debug(f"chosen next_test: {next_name}")
                        return next_name

        # fallback to the default next_test()
        return super().next_test(to_run, all_tests, previous)

    @classmethod
    def destructive(cls, info, test_data):
        # if Executor ended with an exception (ie. duration exceeded),
        # consider the test destructive
        if info.exception:
            return True

        # if the test returned non-0 exit code, it could have thrown
        # a python exception of its own, or (if bash) aborted abruptly
        # due to 'set -e', don't trust the remote, consider it destroyed
        # (0 = pass, 2 = fail, anything else = bad)
        if info.exit_code not in [0,2]:
            return True

        # if the test was destructive, assume the remote is destroyed
        tags = test_data.get("tag", ())
        if "destructive" in tags:
            return True

        return False
