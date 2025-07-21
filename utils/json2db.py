#!/usr/bin/python3

import sys
import json
import gzip
import sqlite3
import tempfile
import subprocess
from pathlib import Path


def parse_lines(fobj):
    for line in fobj:
        platform, status, test, sub, note, files = json.loads(line)
        files = json.dumps(files) if files else None  # also does [] -> None
        yield (platform, status, test, sub, note, files)


if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} results.json.gz results.sqlite.gz")
    sys.exit(1)

_, results_json, results_sqlite = sys.argv

if Path(results_sqlite).exists():
    raise RuntimeError(f"{results_sqlite} already exists")

with tempfile.NamedTemporaryFile(dir="/var/tmp") as tmpf:
    db_conn = sqlite3.connect(tmpf.name)
    db_cur = db_conn.cursor()

    db_cur.execute("""
        CREATE TABLE results (
            platform    TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            test        TEXT    NOT NULL,
            sub         TEXT,
            note        TEXT,
            files       JSONB
        )
    """)

    with gzip.open(results_json, mode="rb") as gz_in:
        db_cur.executemany(
            "INSERT INTO results VALUES(?,?,?,?,?,?)",
            parse_lines(gz_in),
        )

    db_conn.commit()
    db_conn.close()

    with open(results_sqlite, "wb") as gz_out:
        subprocess.run(
            ("gzip", "-9"),
            stdin=tmpf.fileno(),
            stdout=gz_out.fileno(),
        )
