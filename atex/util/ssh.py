import contextlib
import errno
import socket
import subprocess
import time
from pathlib import Path

from .null_logger import NULL_LOGGER


def ssh_keygen(dest_dir, key_type="rsa"):
    dest_dir = Path(dest_dir)
    subprocess.run(
        ("ssh-keygen", "-t", key_type, "-N", "", "-f", dest_dir / f"key_{key_type}"),
        stdout=subprocess.DEVNULL,
        check=True,
    )
    return (dest_dir / f"key_{key_type}", dest_dir / f"key_{key_type}.pub")


def default_ssh_key():
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return None
    for file in ssh_dir.iterdir():
        # if .pub exists for it too
        if file.name.startswith("id_") and Path(f"{file}.pub").exists():
            return file
    return None


def wait_for_sshd(host, port, *, logger=NULL_LOGGER):
    """
    Wait for a real OpenSSH server to start responding on `host`:`port`,
    in an interruptible way.

    This is a generator that performs a complex set of steps of resolving,
    connecting to and reading a remote non-blocking socket, driven only by
    the caller's repeated `next()` iteration, up until either StopIteration
    (success) or any other exception (failure).

    Again - the caller is responsible for any `sleep(1)` to guide the frequency
    of checking the connectivity and they are free to perform other tasks
    outside the scope of this function.

    - `logger` is an optional logging-based logger to write in-progress
      debug details to.
    """
    # resolve the name once, retrying until DNS answers
    # - unfortunately, this may block for some time
    addrs = None
    while addrs is None:
        try:
            addrs = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            logger.debug(f"cannot resolve {host} yet, re-trying: {e}")
            yield

    if not addrs:
        raise ConnectionError(f"unable to get a single address for {host}")
    family, _, _, _, sockaddr = addrs[0]

    backoff = 1
    while True:
        backoff = min(backoff * 2, 180)  # up to 3min
        deadline = time.monotonic() + backoff
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.setblocking(False)

            try:
                s.connect(sockaddr)
            except BlockingIOError:
                # this is expected and normal for a non-blocking socket
                pass

            connected = False
            while not connected and time.monotonic() < deadline:
                yield
                # has connecting failed?
                if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) != 0:
                    break
                # has it succeeded, but is still in progress?
                try:
                    s.getpeername()
                except OSError as e:
                    if e.errno == errno.ENOTCONN:
                        continue
                    break
                connected = True
            if not connected:
                logger.debug("no connection to sshd, re-trying")
                continue

            # connected: read enough of the banner to recognise sshd,
            # accumulating in case it arrives in more than one piece
            buffer = b""
            while time.monotonic() < deadline:
                yield
                try:
                    chunk = s.recv(4 - len(buffer))
                except BlockingIOError:
                    continue
                except OSError:
                    break
                # no data to read - closed connection?
                if not chunk:
                    break
                buffer += chunk
                if buffer == b"SSH-":
                    return
                # could the less-than-4 bytes we have potentially match or not?
                if not b"SSH-".startswith(buffer):
                    raise ConnectionError(f"remote side is not sshd: {buffer!r}")
            logger.debug("connected to sshd, but no banner, re-trying")


def blocking_wait_for_sshd(host, port, *, logger=NULL_LOGGER, sleep=1):
    """
    Wait for a real OpenSSH server to start responding on `host`:`port`.

    This is just a fully synchronous blocking wrapper of `wait_for_ssh()`.
    """
    with contextlib.closing(wait_for_sshd(host, port, logger=logger)) as waiter:
        for _ in waiter:
            time.sleep(sleep)
