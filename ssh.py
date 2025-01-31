#!/usr/bin/python3

import logging
import os
from atex import util
from atex.conn import ssh

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

conn = {
    "Hostname": "127.0.0.1",
    "Port": "2222",
    "IdentityFile": "/home/user/.ssh/id_rsa",
    "User": "user",
}


#ssh.ssh("echo 1", options=conn)
#ssh.ssh("echo 2", options=conn)
#ssh.ssh("echo 3", options=conn)
#ssh.ssh("echo 4", options=conn)
#ssh.ssh("echo 5", options=conn)

c = ssh.StatelessSSHConn(conn)
c.connect()
c.cmd("echo", "1")
c.cmd("echo", "2")
c.cmd("echo", "3")
c.cmd("echo", "4 4")
c.disconnect()

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
