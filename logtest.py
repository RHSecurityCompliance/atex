#!/usr/bin/python3

import logging

#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
#logging.addLevelName(logging.DEBUG, 'D')
#logging.addLevelName(logging.INFO, 'I')
#logging.addLevelName(logging.WARNING, 'W')
#logging.addLevelName(logging.ERROR, 'E')
#logging.addLevelName(logging.CRITICAL, 'C')

from atex import util

def testfunc():
    util.debug('test func')

testfunc()
util.info('main body')
