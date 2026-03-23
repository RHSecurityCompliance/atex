import subprocess
import tempfile
import time


def one_remote(p):
    p.provision(1)
    assert p.get_remote()


def one_remote_nonblock(p):
    p.provision(1)
    # provisioning is probably too slow to make our first get_remote() call
    # return a valid remote, so it should be None
    assert p.get_remote(block=False) is None
    while p.get_remote(block=False) is None:
        time.sleep(0.1)
    # the above being 'not None' depleted the only available remote,
    # so next get_remote() should be forever None
    for _ in range(10):
        assert p.get_remote(block=False) is None
        time.sleep(1)


def two_remotes(p):
    p.provision(2)
    assert p.get_remote()
    assert p.get_remote()


def two_remotes_nonblock(p):
    p.provision(2)
    assert p.get_remote(block=False) is None
    while p.get_remote(block=False) is None:
        time.sleep(0.1)
    while p.get_remote(block=False) is None:
        time.sleep(0.1)
    for _ in range(10):
        assert p.get_remote(block=False) is None
        time.sleep(1)


#def sharing_remote_slot(p):
#    rem = p.get_remote()
#    assert rem
#    rem.release()
#    # even with max_systems=1, this should get a new remote
#    # due to us doing .release() on the previous one
#    assert p.get_remote()
#
#
#def sharing_remote_slot_nonblock(p):
#    assert p.get_remote(block=False) is None
#    while (rem := p.get_remote(block=False)) is None:
#        pass
#    rem.release()
#    while p.get_remote(block=False) is None:
#        pass
#    for _ in range(10):
#        assert p.get_remote(block=False) is None
#        time.sleep(1)

# TODO: replace with .provision() specific tests ^^^


def cmd(p):
    p.provision(1)
    rem = p.get_remote()
    proc = rem.cmd(
        ("echo", "foo bar"),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    out = proc.stdout.rstrip("\n")
    assert out == "foo bar", f"{repr(out)} is 'foo bar'"


def cmd_input(p):
    p.provision(1)
    rem = p.get_remote()
    proc = rem.cmd(
        ("cat",),
        stdout=subprocess.PIPE,
        check=True,
        text=True,
        input="foo bar\n",
    )
    out = proc.stdout.rstrip("\n")
    assert out == "foo bar", f"{repr(out)} is 'foo bar'"


def cmd_binary(p):
    bstr = b"\x00\x01\n\x02\x03"
    p.provision(1)
    rem = p.get_remote()
    proc = rem.cmd(
        ("cat",),
        stdout=subprocess.PIPE,
        check=True,
        input=bstr,
    )
    out = proc.stdout
    assert out == bstr, f"{repr(out)} is {bstr}"


def rsync(p):
    with tempfile.NamedTemporaryFile(delete_on_close=False) as tmpf:
        bstr = b"\x00\x01\n\x02\x03"
        tmpf.write(bstr)
        tmpf.close()

        p.provision(1)
        rem = p.get_remote()
        rem.rsync(tmpf.name, "remote:foobar")
        proc = rem.cmd(
            ("cat", "foobar"),
            stdout=subprocess.PIPE,
            check=True,
        )
        out = proc.stdout
        assert out == bstr, f"{repr(out)} is {bstr}"


# TODO: .start() and .stop() manually
