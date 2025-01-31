#!/usr/bin/python3

import time
import logging
import subprocess

from atex import testingfarm as tf, ssh

logging.basicConfig(level=logging.DEBUG)

with tf.Reserve(compose='CentOS-Stream-9', timeout=60) as m:
    print(m)
#    subprocess.run([
#        'ssh', '-i', m.ssh_key,
#        '-oStrictHostKeyChecking=no', '-oUserKnownHostsFile=/dev/null',
#        f'{m.user}@{m.host}',
#        'ls --color=auto /',
#    ])
    conn = {
        'Hostname': m.host,
        'Port': m.port,
        'IdentityFile': m.ssh_key,
        'User': m.user,
        'RequestTTY': 'yes',
    }
    with ssh.SSHConn(conn) as c:
        c.ssh('dnf install -y python3-pytest &>/dev/null')

    with ssh.SSHConn(conn) as c:
        c.ssh('cd /tmp && pytest /foobar')
        c.ssh('ls --color=auto /')
