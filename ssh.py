#!/usr/bin/python3

import logging
import subprocess
import socket
import time
import os
from atex.connection.ssh import ManagedSSHConn

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

conn = {
    "Hostname": "127.0.0.1",
    "Port": "2222",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "user",
}

def reliable_local_fwd(conn, dest, retries=10):
    for _ in range(retries):
        # let the kernel give us a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        # and try to quickly use it for forwarding
        try:
            conn.forward("LocalForward", f"127.0.0.1:{port} {dest}")
            return port
        except subprocess.CalledProcessError:
            pass
    raise ConnectionError("could not add LocalForward / find a free port")



with ManagedSSHConn(conn) as c:
    c.cmd(("echo", "123"))
    #try:
    #    c.forward("LocalForward", "127.0.0.1:1234 127.0.0.1:2222")
    #except subprocess.CalledProcessError:
    #    pass
    #c.forward("LocalForward", "127.0.0.1:1235 127.0.0.1:2222")
    port = reliable_local_fwd(c, "127.0.0.1:2222")
    print(f"got {port}")
    input()
    c.cmd(("echo", "555"))
    print()
    print()
    cli = c.cmd([], func=lambda *args, **_: args[0])
    print(cli)





#ssh.ssh("echo 1", options=conn)
#ssh.ssh("echo 2", options=conn)
#ssh.ssh("echo 3", options=conn)
#ssh.ssh("echo 4", options=conn)
#ssh.ssh("echo 5", options=conn)

#c = ssh.StatelessSSHConn(conn)
#c.connect()
#c.cmd("echo", "1")
#c.cmd("echo", "2")
#c.cmd("echo", "3")
#c.cmd("echo", "4 4")
#c.disconnect()

#print("----------------")
#
#import time
#
#c = ssh.ManagedSSHConn(conn)
##with ssh.SSHConn(conn) as c:
#try:
#    with c:
#        for i in range(1,100):
#            c.cmd(["echo", i], options={'ServerAliveInterval': '1', 'ServerAliveCountMax': '1', 'ConnectionAttempts': '1', 'ConnectTimeout': '0'})
#            time.sleep(1)
#        #c.ssh("for i in {1..100}; do echo $i; sleep 1; done")
#except KeyboardInterrupt:
#    print("got KB")

#print("ended")
#input()
