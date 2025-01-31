#!/usr/bin/python3

import os
from atex.minitmt.report import CSVReporter

rep = CSVReporter('/tmp/resdir', '/tmp/results.gz')

with rep:
    sub = rep.make_subreporter('rhel-9', 'x86_64')
    sub({'name': '/some/test', 'status': 'pass'})
    sub({'name': '/another/test', 'status': 'error'})

    sub = rep.make_subreporter('rhel-9', 'ppc64le')
    sub({'name': '/ppc/test', 'status': 'fail', 'note': 'foo bar note', 'files': [{'name':'../..//some//ppc,log'}]})
    #sub({'name': '/ppc/test', 'status': 'fail', 'note': 'foo bar note'})

    rep.report('mydistro', 'myarch', 'mystatus', 'myname', 'mynote', 'file1', 'file2')

    with open('/etc/passwd', 'rb') as f:
        rep.store_file('/some/test', 'my.log', f.fileno(), 2672)

    with rep.open_tmpfile() as fd:
        os.write(fd, b'foo\n')
        os.write(fd, b'bar\n')
        rep.link_tmpfile_to('/another/test', 'my2.log', fd)
        rep.link_tmpfile_to('/another/test', 'my3.log', fd)
