> [!NOTE]
> This describes a specific implementation of the abstract Aggregator API.
> See also the [documentation of the generic API](..).

# JSON Lines Aggregators

These Aggregators collect reported results in a line-JSON output file
(see https://jsonltools.com/) and uploaded files (logs) from multiple
test runs under a shared directory.

For example

- `aggregated/results.jsonl`

  ```json
  ["9.8@x86_64", "pass", "/some/test", null, [], null]

  ["10.2@s390x", "pass", "/unit/syscalls", "accept", ["test.txt"], null]
  ["10.2@s390x", "fail", "/unit/syscalls", "connect", ["test.txt"], "Got errno: ECONNABORTED"]
  ["10.2@s390x", "warn", "/unit/syscalls", "open", ["test.txt"], null]
  ["10.2@s390x", "fail", "/unit/syscalls", null, ["full_output.txt"], null]

  ["11.0@x86_64", "pass", "/ltp", "syscalls/alarm01", ["test.out"], null]
  ["11.0@x86_64", "pass", "/ltp", "syscalls/socketpair02", ["server/test.out", "client/test.out"], null]
  ```

- `aggregated/uploaded_files/`

  ```
  /10.2@s390x/unit/syscalls/accept/test.txt
  /10.2@s390x/unit/syscalls/connect/test.txt
  /10.2@s390x/unit/syscalls/open/test.txt
  /10.2@s390x/unit/syscalls/full_output.txt

  /11.0@x86_64/ltp/syscalls/alarm01/test.out
  /11.0@x86_64/ltp/syscalls/socketpair02/server/test.out
  /11.0@x86_64/ltp/syscalls/socketpair02/client/test.out
  ```

The primary class is `JSONLinesAggregator`, but there are additional variants
that store the results in a compressed JSONL file, and optionally can also
compress the uploaded files.

## Format

The results uses a top-level array (on each line) with a fixed item order:

```
[platform, status, test name, subtest name, files, note]
```

All these are strings except `files`, which is another (nested) array
of strings.

Note that test name is explicitly given to `ingest()`, and subtest name comes
from test artifacts (the `name` result key, which may be non-existent,
indicating the result is relevant to the test itself, not a subtest).\
See also [RESULTS.md](../../executor/RESULTS.md).

Further:
- If subtest name or note missing in test artifacts, a `null` item is used.
- If `testout` is present inside test artifacts (in the result for the test
  itself), it is prepended to the list of `files`.

Also note that the aggregated JSONL file **is not related** to any JSON usage
inside test artifacts - both might use JSON as a data format, but for
different purposes.

## Examples

```python
with JSONLinesAggregator("results.jsonl", "uploaded_files") as aggr:
    aggr.ingest("9.8@x86_64", "/some/test", test_artifacts_dir)


aggr_lzma = LZMAJSONLinesAggregator(
    "results.jsonl.xz",
    "uploaded_files",
    compress_files=False,  # do not compress uploaded files
)
with aggr_lzma:
    ...


aggr_gzip = GzipJSONLinesAggregator(
    "results.jsonl.gz",
    "uploaded_files",
    compress_level=5,
    compress_files_suffix="",  # transparent compression
)
with aggr_gzip:
    ...
```
