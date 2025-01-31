#!/usr/bin/python3

import logging
import os
from atex import ssh, util

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

conn = {
    'Hostname': '1.2.3.4',
    'Port': '22',
#    'IdentityFile': '/home/user/.ssh/id_rsa',
    'User': 'foobar',
}


ssh.ssh('echo 1', options=conn)
ssh.ssh('echo 2', options=conn)
ssh.ssh('echo 3', options=conn)
ssh.ssh('echo 4', options=conn)
ssh.ssh('echo 5', options=conn)

#c = ssh.SSHConn(conn)
#c.connect()
#c.ssh('echo 1')
#c.ssh('echo 2')
#c.ssh('echo 3')
#c.ssh('echo 4')
#c.ssh('echo 5')
#c.disconnect()

print('----------------')

c = ssh.SSHConn(conn)
#with ssh.SSHConn(conn) as c:
with c:
    c.ssh('echo 1')
    c.ssh('echo 2')
    c.ssh('echo 3')
    c.ssh('echo 4')
    c.ssh('echo 5')
