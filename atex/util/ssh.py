import subprocess
from pathlib import Path


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
