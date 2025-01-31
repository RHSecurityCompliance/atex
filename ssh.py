#!/usr/bin/python3

import logging
import os
from atex import ssh, util

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

conn = {
    "Hostname": "1.2.3.4",
    "Port": "22",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "root",
}


#ssh.ssh("echo 1", options=conn)
#ssh.ssh("echo 2", options=conn)
#ssh.ssh("echo 3", options=conn)
#ssh.ssh("echo 4", options=conn)
#ssh.ssh("echo 5", options=conn)

#c = ssh.SSHConn(conn)
#c.connect()
#c.ssh("echo 1")
#c.ssh("echo 2")
#c.ssh("echo 3")
#c.ssh("echo 4")
#c.ssh("echo 5")
#c.disconnect()

print("----------------")

import time

c = ssh.SSHConn(conn)
#with ssh.SSHConn(conn) as c:
try:
    with c:
        for i in range(1,100):
            c.ssh(f"echo {i}", options={'ServerAliveInterval': '1', 'ServerAliveCountMax': '1', 'ConnectionAttempts': '1', 'ConnectTimeout': '0'})
            time.sleep(1)
        #c.ssh("for i in {1..100}; do echo $i; sleep 1; done")
except KeyboardInterrupt:
    print("got KB")

print("ended")
input()
