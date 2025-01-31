import time
import tempfile

from atex import util

#import subprocess

#import concurrent.futures
#from atex import util
#from atex.provision.podman import PodmanProvisioner


def one_remote(p):
    assert p.get_remote()


def one_remote_nonblock(p):
    # provisioning is probably too slow to make our first get_remote() call
    # return a valid remote, so it should be None
    assert p.get_remote(block=False) is None
    while p.get_remote(block=False) is None:
        pass
    # the above being 'not None' depleted the only available remote,
    # so next get_remote() should be forever None
    for _ in range(10):
        assert p.get_remote(block=False) is None
        time.sleep(1)


def two_remotes(p):
    assert p.get_remote()
    assert p.get_remote()


def two_remotes_nonblock(p):
    assert p.get_remote(block=False) is None
    while p.get_remote(block=False) is None:
        pass
    while p.get_remote(block=False) is None:
        pass
    for _ in range(10):
        assert p.get_remote(block=False) is None
        time.sleep(1)


def sharing_remote_slot(p):
    rem = p.get_remote()
    assert rem
    rem.release()
    # even with max_systems=1, this should get a new remote
    # due to us doing .release() on the previous one
    assert p.get_remote()


def sharing_remote_slot_nonblock(p):
    assert p.get_remote(block=False) is None
    while (rem := p.get_remote(block=False)) is None:
        pass
    rem.release()
    while p.get_remote(block=False) is None:
        pass
    for _ in range(10):
        assert p.get_remote(block=False) is None
        time.sleep(1)


def cmd(p):
    rem = p.get_remote()
    out = rem.cmd(
        ("echo", "foo bar"),
        func=util.subprocess_output,
    )
    assert out.rstrip("\n") == "foo bar"


def cmd_input(p):
    rem = p.get_remote()
    out = rem.cmd(
        ("cat",),
        func=util.subprocess_output,
        input="foo bar\n",
    )
    assert out.rstrip("\n") == "foo bar", f"{repr(out)} is 'foo bar'"


def cmd_binary(p):
    bstr = b"\x00\x01\n\x02\x03"
    rem = p.get_remote()
    out = rem.cmd(
        ("cat",),
        func=util.subprocess_output,
        text=False,
        input=bstr,
    )
    assert out == bstr, f"{repr(out)} is {bstr}"


def rsync(p):
    with tempfile.NamedTemporaryFile(delete_on_close=False) as tmpf:
        bstr = b"\x00\x01\n\x02\x03"
        tmpf.write(bstr)
        tmpf.close()

        rem = p.get_remote()
        rem.rsync("-v", tmpf.name, "remote:foobar")
        out = rem.cmd(
            ("cat", "foobar"),
            func=util.subprocess_output,
            text=False,
        )
        assert out == bstr, f"{repr(out)} is {bstr}"


# TODO: .start() and .stop() manually

# TODO: .stop_defer() via
#try:
#    p.start()
#finally:
#    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
#        for f in p.stop_defer(p):
#            ex.submit(f)
