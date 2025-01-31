import subprocess
from pathlib import Path

from .subprocess import subprocess_run


def ssh_keygen(dest_dir, key_type="rsa"):
    dest_dir = Path(dest_dir)
    subprocess_run(
        ("ssh-keygen", "-t", key_type, "-N", "", "-f", dest_dir / f"key_{key_type}"),
        stdout=subprocess.DEVNULL,
        check=True,
    )
    return (dest_dir / "key_rsa", dest_dir / "key_rsa.pub")
