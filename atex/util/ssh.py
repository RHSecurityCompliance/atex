import errno
import logging
import socket
import subprocess
import threading
import time
from pathlib import Path


def ssh_keygen(dest_dir, key_type="rsa"):
    dest_dir = Path(dest_dir)
    subprocess.run(
        ("ssh-keygen", "-t", key_type, "-N", "", "-f", dest_dir / f"key_{key_type}"),
        stdout=subprocess.DEVNULL,
        check=True,
    )
    return (dest_dir / f"key_{key_type}", dest_dir / f"key_{key_type}.pub")


def wait_for_sshd(host, port, *, event=None, logger=None):
    """
    Wait for a real OpenSSH server to start responding on `host`:`port`,
    in an interruptible way.

    - `event` is an optional `threading.Event` that, when set, interrupts
      the wait. If None, the wait blocks until sshd is up.

    Return True if successful, False if `event` was set and the waiting
    was thus interrupted.
    """
    logger = logger or logging.getLogger("atex")
    event = event or threading.Event()

    # 2 secs to reply over connected socket initially,
    # with exponential back off (in case the system is too slow
    # to respond)
    backoff_sleep = 2

    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setblocking(False)

            # try connecting
            try:
                s.connect((host, port))
            except BlockingIOError:
                pass

            connected = False
            while not connected:
                if event.wait(timeout=0.1):
                    return False
                # wait for the connection to either fail (SO_ERROR)
                if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) != 0:
                    break
                # or succeed (getpeername)
                try:
                    s.getpeername()
                except OSError as e:
                    if e.errno == errno.ENOTCONN:
                        continue
                    break
                else:
                    connected = True

            # re-try connecting with a new socket
            if not connected:
                logger.debug("connection attempt to sshd failed, re-trying")
                continue

            # connected, try receiving
            sshd_signature = False
            end = time.monotonic() + backoff_sleep
            backoff_sleep = min(backoff_sleep * 2, 180)  # up to 3min
            while not sshd_signature and time.monotonic() < end:
                if event.wait(timeout=0.1):
                    return False
                try:
                    data = s.recv(4)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                else:
                    if data == b"SSH-":
                        sshd_signature = True
                    break

            if not sshd_signature:
                logger.debug("connected to sshd, but no signature, re-trying")
                continue

            return True


def default_ssh_key():
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.is_dir():
        return None
    for file in ssh_dir.iterdir():
        # if .pub exists for it too
        if file.name.startswith("id_") and Path(f"{file}.pub").exists():
            return file
    return None
