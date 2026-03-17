# AdHoc Orchestrator

The idea here is to use a "pool" of reserved Remotes for test execution,
and schedule tests on them on an as-needed (ad-hoc) basis - as soon as a Remote
is freed up (by a previous test finishing), a new test is chosen to run on it.

This is in contrast to pre-splitting a large list of tests to run in "slices",
where each Remote gets to run a slice of fixed size.

For example, imagine running 10 tests on 3 Remotes (A,B,C):

1. We get our first Remote A
1. We start running test 1 on it
1. Test 1 finishes, and we still got only Remote A, so we run test 2 on it
1. We get Remote B and start running test 3 on it
1. Test 3 finishes and B is now free, so we run test 4 on it
1. Test 4 finishes and B is now free, we run test 5
1. Test 5 finishes and B is free, we run test 6 .. (man, test 2 is taking a long time on A)
1. We finally get Remote C and start test 7 on it
1. Test 2 finally finishes on A, but failed and was destructive, so we throw away A and request a new replacement for it, putting test 2 back on the queue for re-run
1. Test 6 finishes on B, and we start (a rerun of) test 2 on it
1. Test 7 finishes on C, we start test 8 on it
1. Test 8 finishes on C, we start test 9 on it
1. We get a new Remote A, a replacement after the destroyed one, and start test 10 on it
1. Test 9 finishes on C, no more tests to run, we release Remote C
1. Test 10 finishes on A, no more tests to run, we release Remote A
1. Test 2 (rerun) finally finishes B, fails again destructively, but its reruns were exhausted, so we just release Remote B and finish

## Basic use

```python

o = AdHocOrchestrator(
    "

```


## Customization

There are several subclass-overridable functions you can use to customize what
happens at certain stages of the scheduling process.

Namely,

- **`run_setup()`** which is called upon receiving a Remote from a Provisioner,
  but before an Executor is instantiated to run tests on it.
- **`next_test()`** which chooses a test name (from a big set of tests) to be
  scheduled next, on either a recycled Remote, or a fresh new one.
- **`destructive()`** which returns a boolean whether the just-finished test
  destroyed the Remote (made it unsuitable for use by more tests).
- **`should_be_rerun()`** which returns a boolean whether a finished failing
  test should be re-run or not.

TODO: document SetupInfo / RunningInfo / FinishedInfo

## Mixin features

TODO

- LimitedRerunsMixin
- FMFDestructiveMixin
- FMFDurationMixin
- FMFPriorityMixin


...


These Aggregators collect reported results in a line-JSON output file and
uploaded files (logs) from multiple test runs under a shared directory.

For example

- `aggregated/results.json`

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

The primary class is `JSONAggregator`, but there are additional variants that
store the results in a compressed JSON file, and optionally can also compress
the uploaded files.

## Format

The results uses a top-level array (on each line) with a fixed item order:

```
[platform, status, test name, subtest name, files, note]
```

All these are strings except `files`, which is another (nested) array
of strings.

Note that test name is explicitly given to `ingest()`, and subtest name comes
from test artifacts (the `name` result key, which may be non-existent,
indicating the result is relevant to the test itself, not a subtest).  
See also [RESULTS.md](../../executor/RESULTS.md).

Further:
- If subtest name or note missing in test artifacts, a `null` item is used.
- If `testout` is present inside test artifacts (in the result for the test
  itself), it is prepended to the list of `files`.

Also note that the aggregated JSON file **is not related** to any JSON usage
inside test artifacts - both might use JSON as a data format, but for
different purposes.

## Examples

```python
with JSONAggregator("results.json", "uploaded_files") as aggr:
    aggr.ingest("9.8@x86_64", "/some/test", test_artifacts_dir)


aggr_lzma = LZMAJSONAggregator(
    "results.json.xz",
    "uploaded_files",
    compress_files=False,  # do not compress uploaded files
)
with aggr_lzma:
    ...


aggr_gzip = GzipJSONAggregator(
    "results.json.gz",
    "uploaded_files",
    compress_level=5,
    compress_files_suffix="",  # transparent compression
)
with aggr_gzip:
    ...
```
