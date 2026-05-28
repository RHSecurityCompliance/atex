import errno
import logging
import os
import select
import subprocess
import tempfile
from pathlib import Path

from .kickstart import add_kickstart_args, kickstart_from_args


def _run_with_pty(cmd):
    m_fd, s_fd = os.openpty()
    proc = None
    try:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=s_fd,
                stdout=s_fd,
                stderr=subprocess.STDOUT,
            )
        finally:
            os.close(s_fd)

        poller = select.poll()
        poller.register(m_fd, select.POLLIN)

        while True:
            events = poller.poll()
            for _fd, event in events:
                if event & select.POLLIN:
                    try:
                        data = os.read(m_fd, 1024)
                    except OSError as e:
                        if e.errno == errno.EIO:
                            break
                        raise
                    if data == b"":
                        break
                    while data:
                        written = os.write(2, data)
                        data = data[written:]
                elif event & (select.POLLERR | select.POLLHUP):
                    break
            else:
                continue
            break
    except BaseException:
        if proc is not None:
            proc.terminate()
        raise
    finally:
        os.close(m_fd)

    code = proc.wait()
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd)


def install(args):
    ks_contents = kickstart_from_args(args)

    if args.dry_run:
        print(ks_contents, end="")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ks.cfg", delete_on_close=False) as ks_tmp:
        ks_tmp.write(ks_contents)
        ks_tmp.close()

        v_i_args = []
        kernel_args = []

        if args.arch:
            v_i_args += ("--arch", args.arch, "--virt-type", "qemu")
            kernel_args += (
                # eats a lot of emulated CPU time
                "inst.zram=0",
                "systemd.zram=0",
                # takes a while to start up + completely useless
                "rd.plymouth=0",
                # some services used by Anaconda take a LONG time to start
                "systemd.default_timeout_start_sec=3600",
                # for seeing some progress on slower/emulated domains
                "inst.notmux",
                "systemd.journald.forward_to_console=1",
            )
            if args.arch == "ppc64le":
                kernel_args.append("console=hvc0")
                # prevents a lot of console spam by Anaconda trying hvc1
                kernel_args.append("systemd.mask=anaconda-shell@hvc1.service")
            elif args.arch == "aarch64":
                kernel_args.append("console=ttyAMA0")
                # default --cpu fails to emulate via TCG
                v_i_args += ("--cpu", "cortex-a53")
            elif args.arch == "s390x":
                kernel_args.append("console=ttysclp0")
                # s390x does ACPI reboot as a QEMU "crash", so always
                # reboot on crash to make reboot "work"
                v_i_args += ("--events", "on_crash=restart")
            else:
                kernel_args.append("console=ttyS0,115200")
        else:
            if args.bios:
                v_i_args += ("--machine", "pc", "--boot", "hd,bios.useserial=yes")
            else:
                v_i_args += (
                    "--machine", "q35", "--features", "smm=on",
                    "--boot", "firmware=efi,loader.secure=no",
                )
            v_i_args += ("--cpu", "host-passthrough,cache.mode=passthrough")
            kernel_args.append("console=ttyS0,115200")

        connect = ("--connect", args.connect) if args.connect else ()
        pool = f"pool={args.pool}," if args.pool else ""

        # this intentionally doesn't include --network to let v-i use whatever
        # best networking option is available - bridge, default net, user mode
        cmd = (
            "virt-install",
            *connect,
            "--name", args.name,
            "--location", args.location,
            "--memory", str(args.memory),
            "--vcpus", "2",
            "--disk", f"{pool}size={args.size},format={args.format},cache=none,io=native",
            "--graphics", "none",
            "--console", "pty",
            "--rng", "/dev/urandom",
            "--os-variant", "rhel8-unknown",
            "--extra-args", (
                "brltty=no "  # avoid heavy console spam on missing devices
                "mitigations=off "  # make things faster a bit during install
                f"inst.ks=file:/{Path(ks_tmp.name).name} "  # basename
                f"inst.repo={args.location}"
                + ((" " + " ".join(kernel_args)) if kernel_args else "")
            ),
            "--initrd-inject", ks_tmp.name,
            "--autoconsole", "text",
            "--noreboot",
            *v_i_args,
        )

        logging.info(f"running {cmd}")
        if args.emulate_pty:
            _run_with_pty(cmd)
        else:
            subprocess.run(cmd, check=True)

        if args.final_memory:
            subprocess.run(
                ("virsh", "-q", *connect),
                input=(
                    f"setmaxmem {args.name} {args.final_memory}MiB --config\n"
                    f"setmem {args.name} {args.final_memory}MiB --config\n"
                ),
                text=True,
                check=True,
            )


def parse_args(parser):
    parser.add_argument("--connect", "-c", help="libvirt connection URI")
    cmds = parser.add_subparsers(
        dest="_cmd", help="virt sub-command", metavar="<cmd>", required=True,
    )

    cmd = cmds.add_parser(
        "install",
        help="use virt-install to install a new domain (VM)",
    )
    cmd.add_argument(
        "--dry-run",
        help="just generate and print the kickstart",
        action="store_true",
    )
    cmd.add_argument(
        "--emulate-pty",
        help="emulate a terminal for virt-install console output",
        action="store_true",
    )
    cmd.add_argument("--name", "-n", help="domain (VM) name", required=True)
    cmd.add_argument("--location", "-l", help="URL to install from", required=True)
    cmd.add_argument("--format", help="image format", default="qcow2", choices=("qcow2", "raw"))
    cmd.add_argument("--size", help="maximum disk size in GBs", default=20, type=int)
    cmd.add_argument("--memory", help="RAM in MBs", default=4096, type=int)
    cmd.add_argument("--bios", help="use old BIOS instead of UEFI", action="store_true")
    cmd.add_argument("--arch", help="emulate a non-native arch")
    cmd.add_argument("--pool", help="storage pool for the primary disk")
    cmd.add_argument("--final-memory", help="after-install RAM in MBs", type=int)
    add_kickstart_args(cmd)


def main(args):
    match args._cmd:
        case "install":
            install(args)
        case _:
            raise RuntimeError(f"unknown args: {args}")


CLI_SPEC = {
    "help": "utilities for libvirt virtualization",
    "args": parse_args,
    "main": main,
}
