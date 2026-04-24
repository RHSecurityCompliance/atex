import atexit
import getpass
import json
import logging
import socket
import subprocess
import time
import xml.etree.ElementTree as ET

from .common import make_helper_cmd


def _wait_for_sshd(host, port):
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0)
            try:
                s.connect((host, port))
                if s.recv(4) == b"SSH-":
                    return
                else:
                    logging.debug("connected to sshd, but no signature, re-trying")
            except OSError:
                logging.debug("connection attempt to sshd failed, re-trying")
        time.sleep(0.1)


def reserve(args):
    helper_cmd = make_helper_cmd(args)
    logging.debug(f"connecting to helper: {helper_cmd}")
    helper_proc = subprocess.Popen(
        helper_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    atexit.register(helper_proc.kill)

    def helper_query(data):
        binary_json = json.dumps(data).encode()
        helper_proc.stdin.write(binary_json)
        helper_proc.stdin.write(b"\n")
        helper_proc.stdin.flush()
        response = helper_proc.stdout.readline()
        if not response:
            raise RuntimeError("empty response from helper (not running?)")
        return json.loads(response.decode())

    # ping the helper to make sure we're talking with a compatible one
    response = helper_query({"cmd": "ping"})
    if (
        response.get("cmd") != "ping"
        or response.get("reply") != "atex-virt-helper v1 pong"
    ):
        raise RuntimeError(f"bad pong from remote helper (wrong version?): {response}")

    logging.debug(f"ping successful: {response}")

    if args.name and (name := args.name.strip()):
        response = helper_query({"cmd": "setname", "name": name})
        if not response["success"]:
            raise RuntimeError(f"failed to 'setname': {response}")

    # -------------------------------------------------------------------------

    logging.info("trying to reserve any one domain")
    cmd = {"cmd": "reserve"}
    if args.domain_filter:
        cmd["filter"] = args.domain_filter
    while True:
        response = helper_query(cmd)
        if not response["success"]:
            reply = response["reply"]
            if reply == "no domain could be reserved":
                time.sleep(0.2)  # give priority to an interactive user
                continue
            else:
                raise RuntimeError(f"failed reserve: {reply}")
        else:
            domain = response["domain"]
            logging.debug(f"got domain {domain}")
            break

    # destroy the domain if running
    response = helper_query({"cmd": "virsh", "args": ["domstate", domain]})
    if not response["success"]:
        raise RuntimeError(f"failed domstate {domain}: {response['reply']}")
    if response["reply"] != "shut off\n":
        logging.info(f"destroying reserved {domain}")
        response = helper_query({"cmd": "virsh", "args": ["destroy", domain]})
        if not response["success"]:
            raise RuntimeError(f"failed destroy {domain}: {response['reply']}")
        while True:
            time.sleep(0.1)
            response = helper_query({"cmd": "virsh", "args": ["domstate", domain]})
            if not response["success"]:
                raise RuntimeError(f"failed domstate {domain}: {response['reply']}")
            if response["reply"] == "shut off\n":
                logging.debug(f"destroyed domain {domain}")
                break

    # -------------------------------------------------------------------------

    # find the forwarded port via virsh over atex-virt-helper
    response = helper_query({
        "cmd": "virsh",
        "args": [
            "dumpxml", domain, "--xpath",
            "//devices/interface[backend/@type='passt']/portForward/range",
        ],
    })
    output = response["reply"]
    if not response["success"]:
        raise RuntimeError(f"'virsh dumpxml {domain}' failed: {output}")

    first_range, _, _ = output.partition("\n")  # first <range> only
    logging.debug(f"found portForward range {first_range}")
    port_range = ET.fromstring(first_range)
    domain_ssh_port = port_range.get("start")  # string!
    assert domain_ssh_port

    # -------------------------------------------------------------------------

    logging.info(f"cloning {args.image} for {domain}")
    response = helper_query({
        "cmd": "copy-volume",
        "pool": args.pool,
        "from": args.image,
        "to_domain": domain,
    })
    if not response["success"]:
        output = response["reply"]
        raise RuntimeError(f"copy-volume failed: {output}")

    logging.info(f"starting up {domain}")
    response = helper_query({"cmd": "virsh", "args": ["start", domain]})
    if not response["success"]:
        raise RuntimeError(f"'virsh start {domain}' failed: {response['reply']}")

    # -------------------------------------------------------------------------

    domain_ssh_host = "127.0.0.1" if args.helper_localhost else args.helper_host

    logging.info(f"waiting for sshd on {domain_ssh_host}:{domain_ssh_port}")
    _wait_for_sshd(domain_ssh_host, int(domain_ssh_port))

    while True:
        logging.info(
            f"launching ssh for root@{domain_ssh_host}:{domain_ssh_port} "
            f"with key:{args.helper_sshkey}",
        )

        proc = subprocess.run([
            "ssh", "-q", "-i", args.helper_sshkey, "-p", domain_ssh_port,
            "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null",
            f"root@{domain_ssh_host}",
        ])
        if proc.returncode != 0:
            print(f"ssh terminated with exit code {proc.returncode}\n")
            try:
                input("Press RETURN to try to reconnect, Ctrl-C to quit ...")
            except KeyboardInterrupt:
                print()
                break
        else:
            break

    # -------------------------------------------------------------------------

    logging.info("closing helper connection")
    helper_proc.stdin.close()
    rc = helper_proc.wait()
    atexit.unregister(helper_proc.kill)
    if rc != 0:
        raise RuntimeError(f"helper exited with {rc} after closing its stdin")


def add_reserve_args(parser):
    parser.add_argument(
        "--name",
        help="name visible in reservation list",
        default=getpass.getuser(),
    )
    parser.add_argument("--pool", help="storage pool to operate on", default="default")
    parser.add_argument("--domain-filter", help="regex to match a domain name")
    parser.add_argument("image", help="existing image name to clone for use")
