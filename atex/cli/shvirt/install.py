import atexit
import getpass
import json
import logging
import subprocess
import time

from ..virt.kickstart import add_kickstart_args, kickstart_from_args
from .common import make_helper_cmd


def install(args):
    logging.info("preparing kickstart")
    ks_contents = kickstart_from_args(args)

    if args.dry_run:
        print(ks_contents, end="")
        return

    # -------------------------------------------------------------------------

    helper_cmd = make_helper_cmd(args)
    logging.debug(f"connecting to helper: {helper_cmd}")
    helper_proc = subprocess.Popen(
        helper_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    atexit.register(helper_proc.kill)

    def helper_write(data):
        binary_json = json.dumps(data).encode()
        helper_proc.stdin.write(binary_json)
        helper_proc.stdin.write(b"\n")
        helper_proc.stdin.flush()

    def helper_read():
        return json.loads(helper_proc.stdout.readline().decode())

    def helper_query(data):
        helper_write(data)
        return helper_read()

    # ping the helper to make sure we're talking with a compatible one
    response = helper_query({"cmd": "ping"})
    if (
        response.get("cmd") != "ping"
        or response.get("reply") != "atex-virt-helper v1 pong"
    ):
        raise RuntimeError(f"bad pong from remote helper (wrong version?): {response}")

    logging.debug(f"ping successful: {response}")

    if args.reserve and args.reserve_name:
        if name := args.reserve_name.strip():
            response = helper_query({"cmd": "setname", "name": name})
            if not response["success"]:
                raise RuntimeError(f"failed to 'setname': {response}")

    # -------------------------------------------------------------------------

    temp_image = f"{args.name}-temp"

    if args.reserve:
        logging.info("trying to reserve any one domain")
        cmd = {"cmd": "reserve"}
        if args.reserve_filter:
            cmd["filter"] = args.reserve_filter
        while True:
            response = helper_query(cmd)
            if not response["success"]:
                reply = response["reply"]
                if reply == "no domain could be reserved":
                    time.sleep(5)
                    continue
                else:
                    raise RuntimeError(f"failed reserve: {reply}")
            else:
                domain = response["domain"]
                logging.debug(f"got domain {domain}")
                break

        logging.info(f"destroying {domain} to free RAM for our domain")
        helper_query({"cmd": "virsh", "args": ["destroy", domain]})

    # -------------------------------------------------------------------------

    logging.info(f"pre-creating new {temp_image}")
    response = helper_query({
        "cmd": "create-volume",
        "pool": args.pool,
        "name": temp_image,
        "format": args.format,
        "size": args.size * 1024**3,
        "remove_existing": True,
    })
    if not response["success"]:
        output = response["reply"]
        raise RuntimeError(f"create-volume failed: {output}")

    logging.info("uploading kickstart")
    ks_bytes = ks_contents.encode()
    helper_write({"cmd": "upload", "name": "ks.cfg", "length": len(ks_bytes)})
    helper_proc.stdin.write(ks_bytes)
    helper_proc.stdin.flush()
    response = helper_read()
    assert response.get("success")

    if args.bios:
        machine = ("--machine", "pc", "--boot", "hd,bios.useserial=yes")
    else:
        machine = (
            "--machine", "q35", "--features", "smm=on",
            "--boot", "firmware=efi,loader.secure=no",
        )

    virt_install_args = (
        "--transient",
        "--location", args.location,
        "--name", f"installing-{args.name}",
        "--memory", "4096",
        "--disk", (
            f"vol={args.pool}/{temp_image},format={args.format},"
            "cache=none,io=native,discard=unmap"
        ),
        "--network", "passt",
        "--cpu", "host-passthrough,cache.mode=passthrough",
        "--graphics", "none",
        "--console", "pty",
        "--rng", "/dev/urandom",
        "--os-variant", "rhel8-unknown",
        *machine,
        "--extra-args", (
            "console=ttyS0,115200 "
            "inst.sshd inst.notmux inst.noninteractive inst.loglevel=debug "
            "systemd.journald.forward_to_console=1 "
            "inst.ks=file:/ks.cfg "
            f"inst.repo={args.location}"
        ),
        "--initrd-inject", "ks.cfg",
        "--autoconsole", "text",
        "--noreboot",
    )
    logging.info(f"running virt-install: {virt_install_args}")
    response = helper_query({
        "cmd": "virt-install",
        "args": virt_install_args,
        "destroy_on_error": True,
    })
    if not response["success"]:
        output = response["reply"]
        raise RuntimeError(f"virt-install failed: {output}")

    # -------------------------------------------------------------------------

    logging.info(f"moving {temp_image} --> {args.name}")
    response = helper_query({
        "cmd": "copy-volume",
        "pool": args.pool,
        "from": temp_image,
        "to": args.name,
        "move": True,
    })
    if not response["success"]:
        output = response["reply"]
        raise RuntimeError(f"copy-volume failed: {output}")

    # -------------------------------------------------------------------------

    helper_proc.stdin.close()
    rc = helper_proc.wait()
    atexit.unregister(helper_proc.kill)
    if rc != 0:
        raise RuntimeError(f"helper exited with {rc} after closing its stdin")


def add_install_args(parser):
    parser.add_argument(
        "--dry-run",
        help="just generate and print the kickstart",
        action="store_true",
    )

    grp = parser.add_argument_group("Image")
    grp.add_argument("--name", "-n", help="image name", required=True)
    grp.add_argument("--pool", help="storage pool name for the image", default="default")
    grp.add_argument("--location", "-l", help="URL to install from", required=True)
    grp.add_argument("--format", help="image format", default="raw", choices=("qcow2","raw"))
    grp.add_argument("--size", help="maximum image size in GB", default=40, type=int)
    grp.add_argument("--bios", help="create old BIOS image instead of UEFI", action="store_true")

    add_kickstart_args(parser)

    grp = parser.add_argument_group(
        title="Reservation",
        description=(
            "Optionally reserve any one existing domain (VM) and destroy it "
            "prior to image install, offsetting the RAM cost of the "
            "image-installing domain."
        ),
    )
    grp.add_argument("--reserve", help="reserve an existing domain", action="store_true")
    grp.add_argument("--reserve-filter", help="regex to match a domain name")
    grp.add_argument(
        "--reserve-name",
        help="name visible in reservation list",
        default=getpass.getuser(),
    )
