# Custom results reporting

Note that this format is designed to be used via a UNIX socket provided by
a "control file" logic, specified in [CONTROL_FILE.md](CONTROL_FILE.md).

## Basic format

Each test can report between 0 and many "results", specified as a dictionary
(a.k.a. JSON Object):

- `name` (as string)
- `status` (as string): `pass`, `fail`, `info`, `warn`, `skip`, `error`
- `files` (as array/list)
- `partial` (as boolean)
- `testout` (as string)

(This is somewhat similar to tmt's internal YAML results.)  
This structure is called a "result".

Ie.
```
{"status": "pass", "name": "/some/test/my-first-result"}
{"status": "skip", "name": "/some/test/foreign/nested/result"}
```
(Notice there are no commas at EOL, no start/end `[` `]` to signify an array
over multiple results, each result / line is its own JSON.)

With the [Control File](CONTROL_FILE.md) syntax, this would look like
```
result {"status": "pass", "name": "/some/test/my-first-result"}\n
result {"status": "skip", "name": "/some/test/foreign/nested/result"}\n
```

## Name

Unlike tmt, **the test is responsible for prefixing its name**, we don't modify
the reported `name` in any way - instead, we provide `TMT_TEST_NAME` with
the absolute test name, just like tmt.

```
$TMT_TEST_NAME/my-first-result
$TMT_TEST_NAME/foreign/nested/result
```

With great responsibility comes great power - a test can report any result
with any name, anywhere.  

Ie.

- a test named `/misc/ltp` could report results as `/suites/ltp/accept01`
- any test could check for `VALGRIND=1` and prefix its results with `/valgrind/`
- there could be multiple mutually-exclusive tests as "variants",
  `/testset/small`, `/testset/medium` and `/testset/big`, all reporting results
  under the same prefix `/testset/*`, just different amounts of tests/results
- multiple tests `/syscalls/01`, `/syscalls/02`, etc. could run in parallel
  and report their results under a shared `/syscalls/` namespace, ie.
  `/syscalls/open`, `/syscalls/openat`, `/syscalls/openat2`, etc.

### Fallback result

If a test doesn't send/write anything to `MINITMT_RESULTS` before exiting,
we append a simple result with the test name itself, and autodetect `status`
from the `test` shell exit code, `0` as `pass`, non-`0` as `fail`.  
We also attach its stdout+stderr as `output.txt` (name inspired by tmt).

```
result {"status": "pass", "name": "/some/test", "testout": "output.txt"}\n
```

## Files

The `files` key denotes an array of JSON Objects (dictionaries), each
representing one file to be uploaded. Each object must specify

- a file name (as string)
- length (as integer, in bytes)

```
result {"status": "pass", "name": "/some/test", "files": [{"name": "foobar.log", "length": 100}]}\n
```

After we receive such a result (incl. its terminating newline byte), we start
treating any incoming data as binary `foobar.log` contents, reading exactly
100 bytes, after which we swich back to parsing results.

If a result specifies multiple `files` entries, we read their contents in the
order they were specified in the `files` array, splitting the incoming binary
data stream by the lengths specified.

```
result {"status": "pass", "name": "/some/test", "files": [{"name": "A", "length": 13}, {"name": "B", "length": 13}]}\n
contents of Acontents of Bresult {"status": "pass", "name": "/another" ...
```

A file name may contain zero or more `/`, but it must not start with `/`.

A sanity check will cause an error (discarding the result) if you specify
multiple identical file names within one result.  
However, this does not extend across results - a second result with the same
`name` specifying the same `files` `name` results in undefined behavior
(the file may be overwritten by us, result discarded, or error triggered).

## Partial results

If a result contains `partial` as a key with `true` as a value, the result is
temporarily cached by us in memory (not passed along further) until either
another result of the same `name` and without `partial` (or with it `false`)
is received, or until the test exits.

Until the result is closed (`"partial": false` or test exit), a test may send
zero or more results with the same `name`, and we perform a union over both
the old and the just-received new result:

- `name` remains unchanged (implicitly)
- any new keys (not in the old result) with non-`null` value are added
- any existing keys with `null` as the new value are deleted
- any existing keys with string and number values are replaced with new values
- any existing keys with array (list) values have new values appended
- any existing keys with object (dict) values are recursively union'd using
  this algorithm
- any existing keys with values of different data types between old/new results
  have values replaced with the new version

```
result {"name": "/some/test", "status": "error", "partial": true, "files": [{"name": "out.log", "length": 29}]}\n
this is out.log with newline\n
result {"name": "/unrelated/result", "status": "pass"}\n
result {"name": "/some/test", "partial": true, "files": [{"name": "report.log", "length": 32}]}\n
this is report.log with newline\n
result {"name": "/some/test", "status": "pass"}\n
```
will result in us parsing it as equivalent to
```
result {"status": "pass", "name": "/unrelated/result"}\n
result {"status": "pass", "name": "/some/test", "files": [{"name": "out.log", "length": 29}, {"name": "report.log", "length": 32}]}\n
this is out.log with newline\n
this is report.log with newline\n
```
because `/unrelated/result` was a regular non-`partial` result (reported
immediately), and the last `/some/test` line also lacked `partial`, so it was
reported along with previously-stored data.

This allows a test to "prepare" a final picture of how its results should
look in the end, and gradually update that picture - if it times out or
otherwise crashes (exits unexpectedly), the `error` status gets used.  
It also allows a test to send out critical logs before a risky operation,
without that creating a separate result entry.

Note that there can be more than one `"partial": true` result queued up
at the same time (with different `name`s), from one test - useful if the test
is running multiple operations in parallel and wants to report each as
a separate result.  
Multiple `"partial": true` results retain the order they first appeared in,
new additions/updates don't change the order.

For obvious reasons, please don't send too many `"partial": true` results, as
we need to keep them in memory - excessive amounts will increase memory use.

## Test stdout and stderr

If a result specifies `testout` in a result, we take the value as a file name
to be added to `files` by us, with test stdout+stderr as the contents.

```
result {"status": "pass", "name": "/some/test", "testout": "test.log"}\n
```

The result doesn't need to (but may) specify other unrelated `files` in the
same result.  
It must not specify a `files` entry with `name` identical to the name passed
in `testout`, doing so triggers a sanity check error, discarding the result.

`testout` may be specified in a `"partial": true` result, overriden in any
later `"partial": true` result for the same test `name`, just like any other
string. It is parsed by us only on a final `"partial": false` submission.

A test may send multiple results with `testout` specified, possibly using
different strings as file names, and we will link the stdout+stderr log to all
of them. (Probably not super useful, though.)

## Corner cases

- A line with invalid JSON causes a sanity check to trigger an error and
  and discard the entire line.  
  Note that this is particularly sneaky if you send a partial result (broken up
  by a newline), because the next line will receive an unfinished JSON,
  possibly followed up by a valid result JSON, which will be discarded, because
  it sits on the same `\n`-separated line as the second half of a malformed one.
- `name` and `status` are mandatory keys, if a result doesn't have them,
  a sanity check triggers an error and discards the result.
  - Note that a `"partial": true` result may be without `status` as long as
    `status` is provided before/during a `"partial": false` result later.

### Custom result keys

Any JSON keys other than those specified in [Basic format](#basic-format) are
ignored - your test can freely add custom keys to the results, ie.

- `note` for adding extra details about a result (like tmt has)
- `rerun` if a test tries to run its logic several times before passing
- `group` for result grouping by a tag/name, in a 3rd party software

Note however that it's a good idea to prefix keys with something unique to you,
to prevent conflicts with future changes to this spec.
