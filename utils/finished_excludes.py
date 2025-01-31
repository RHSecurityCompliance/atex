#!/usr/bin/python3

import sys
import json
import gzip


if len(sys.argv) != 2:
    print(f"usage: {sys.argv[0]} results.json.gz")
    sys.exit(1)

_, results_json = sys.argv

def yield_testnames(fobj):
    for line in fobj:
        platform, status, test, sub, note, files = json.loads(line)
        if not sub:
            # fmf excludes expect a regexp for re.match()
            yield f"^{test}$"

with gzip.open(results_json, mode="rb") as gz_in:
    print("\n".join(sorted(yield_testnames(gz_in))))
