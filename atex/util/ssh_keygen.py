import subprocess
from pathlib import Path


def ssh_keygen(dest_dir, key_type="rsa"):
    dest_dir = Path(dest_dir)
    subprocess.run(
        ("ssh-keygen", "-t", key_type, "-N", "", "-f", dest_dir / f"key_{key_type}"),
        stdout=subprocess.DEVNULL,
        check=True,
    )
    return (dest_dir / "key_rsa", dest_dir / "key_rsa.pub")
