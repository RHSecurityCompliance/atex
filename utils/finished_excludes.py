#!/usr/bin/python3

# Based on a JSONAggregator output, return all test names as regular expressions
# suitable for FMFTests 'exclude=' argument.
#
# This is useful when doing a second, separate, test run, and wanting to run
# only tests that were not previously executed.

import sys
import json
import gzip


def yield_testnames(fobj):
    for line in fobj:
        _platform, _status, test, sub, _note, _files = json.loads(line)
        if not sub:
            # fmf excludes expect a regexp for re.match()
            yield f"^{test}$"


if len(sys.argv) != 2:
    print(f"usage: {sys.argv[0]} results.json.gz")
    sys.exit(1)

_, results_json = sys.argv

with gzip.open(results_json, mode="rb") as gz_in:
    print("\n".join(sorted(yield_testnames(gz_in))))
