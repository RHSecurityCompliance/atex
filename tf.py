#!/usr/bin/python3

import time
import logging
import subprocess

from atex import testingfarm as tf

logging.basicConfig(level=logging.DEBUG)

with tf.Reserve(compose='CentOS-Stream-8', timeout=60, api=api) as m:
    print(m)
    subprocess.run([
        'ssh', '-i', m.ssh_key,
        '-oStrictHostKeyChecking=no', '-oUserKnownHostsFile=/dev/null',
        f'{m.user}@{m.host}',
        'ls /',
    ])
