import pytest
import testutil

from atex.connection import Connection
from atex.provisioner import ProvisionerError, Remote
from atex.provisioner.anyconn import AnyConnectionProvisioner


class TestingConnection(Connection):
    def __init__(self):
        self.events = []
        self.custom_attr = "test_value"

    def connect(self):
        self.events.append("connect")

    def disconnect(self):
        self.events.append("disconnect")

    def cmd(self, command, **_):
        self.events.append(f"cmd {command}")

    def rsync(self, *args, **_):
        self.events.append(f"rsync {args}")


@pytest.fixture(scope="function", autouse=True)
def setup_timeout():
    with testutil.Timeout(30):
        yield


# ------------------------------------------------------------------------------


def test_one_remote():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        remote.release()
    assert remote.events == ["connect", "disconnect"]


def test_two_remotes():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(2)
        remote1 = p.get_remote()
        remote2 = p.get_remote()
        assert p.get_remote(block=False) is None
        remote1.release()
        remote2.release()
    assert remote1.events == ["connect", "disconnect"]
    assert remote2.events == ["connect", "disconnect"]


def test_stop_release():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
    assert remote.events == ["connect", "disconnect"]


def test_cmd():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        remote.cmd(("echo", "hello"))
    assert remote.events == ["connect", "cmd ('echo', 'hello')", "disconnect"]


def test_rsync():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        remote.rsync("-v", "src", "remote:dst")
    assert remote.events == ["connect", "rsync ('-v', 'src', 'remote:dst')", "disconnect"]


def test_connect():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        assert remote.events == ["connect"]


def test_disconnect():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        assert remote.events == ["connect"]
        remote.release()
        assert remote.events == ["connect", "disconnect"]


def test_max_remotes():
    with AnyConnectionProvisioner(TestingConnection, max_remotes=1) as p:
        p.provision(2)
        remote1 = p.get_remote()
        assert p.get_remote(block=False) is None
        remote1.release()
        remote2 = p.get_remote()
        remote2.release()
    assert remote1.events == ["connect", "disconnect"]
    assert remote2.events == ["connect", "disconnect"]


def test_no_provision():
    with AnyConnectionProvisioner(TestingConnection) as p:
        assert p.get_remote(block=False) is None


def test_clear():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(2)
        p.clear()
        assert p.get_remote(block=False) is None


class BrokenConnection(Connection):
    def __init__(self):
        raise RuntimeError("constructor broke")

    def connect(self):
        pass

    def disconnect(self):
        pass

    def cmd(self, command, **_):
        pass

    def rsync(self, *args, **_):
        pass


def test_constructor_failure():
    with AnyConnectionProvisioner(BrokenConnection) as p:
        p.provision(1)
        with pytest.raises(RuntimeError):
            p.get_remote()
        # provisioner must recover
        p.provision(1)
        with pytest.raises(RuntimeError):
            p.get_remote()


def test_stopped():
    p = AnyConnectionProvisioner(TestingConnection)
    with pytest.raises(ProvisionerError):
        p.provision(1)


def test_isinstance():
    with AnyConnectionProvisioner(TestingConnection) as p:
        p.provision(1)
        remote = p.get_remote()
        assert isinstance(remote, Remote)
        assert isinstance(remote, Connection)
        assert isinstance(remote, TestingConnection)


class ParameterizedConnection(Connection):
    def __init__(self, label, *, option=None):
        self.label = label
        self.option = option

    def connect(self):
        pass

    def disconnect(self):
        pass

    def cmd(self, command, **_):
        pass

    def rsync(self, *args, **_):
        pass


def test_conn_args():
    with AnyConnectionProvisioner(
        ParameterizedConnection, conn_args=("hello",),
    ) as p:
        p.provision(1)
        remote = p.get_remote()
        assert remote.label == "hello"
        assert remote.option is None


def test_conn_kwargs():
    with AnyConnectionProvisioner(
        ParameterizedConnection,
        conn_args=("hello",),
        conn_kwargs={"option": "world"},
    ) as p:
        p.provision(1)
        remote = p.get_remote()
        assert remote.label == "hello"
        assert remote.option == "world"


class ConnectFailConnection(Connection):
    def __init__(self):
        pass

    def connect(self):  # noqa: PLR6301
        raise ConnectionError("connect failed")

    def disconnect(self):
        pass

    def cmd(self, command, **_):
        pass

    def rsync(self, *args, **_):
        pass


def test_connect_failure():
    with AnyConnectionProvisioner(ConnectFailConnection) as p:
        p.provision(1)
        with pytest.raises(ConnectionError):
            p.get_remote()
        # provisioner must recover -- _reserving was decremented,
        # so a new provision+get_remote must not deadlock
        p.provision(1)
        with pytest.raises(ConnectionError):
            p.get_remote()
