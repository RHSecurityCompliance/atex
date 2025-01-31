# Custom results reporting

Note that this format is designed to be used via a special "test control"
file descriptor, as specified by [TEST_CONTROL.md](TEST_CONTROL.md).

Specifically, this format is meant to be used as an argument to the `result`
_control word_.

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
{"status": "pass"}

{"status": "pass", "name": "my-first-result"}

{"status": "skip", "name": "some/nested/result"}
```

### JSON format details

For the sake of understandability, this document puts one result on one line,
leading to potentially long line examples, but clearly separating results
from each other.  
Note, however, that this is an artificial limitation - a result is any valid
JSON object, even a multi-line one.

Given the [TEST_CONTROL.md](TEST_CONTROL.md) syntax, this JSON object is sent
as binary data following a `result <bytes>\n` _control line_, and the JSON
object must be exactly `<bytes>` long.

Note that only one result may be sent using one `result` _control word_,
eg. no top-level arrays/lists or multiple `{...}` objects allowed.

## Name

Any `name` specified in a result is appended to the test name automatically.

Ie.
```
{"status": "pass", "name": "my-first-result"}
```
becomes `/path/to/test/my-first-result`.

A `name`-less result is meant for the test itself (no "sub" result).

A test can therefore report multiple results under its namespace before,
ultimately, reporting its own result:
```
{"status": "pass", "name": "my-first-result"}
{"status": "fail", "name": "my-second-result"}
{"status": "fail"}
```

### Fallback result

If a test doesn't report a result for itself (with `name` missing), we append
a simple result for it, autodetecting `status` from the `test` shell exit code,
`0` as `pass`, non-`0` as `fail`.  
We also attach its stdout+stderr as `output.txt` (name inspired by tmt).

This is roughly equivalent to ie.
```
{"status": "pass", "testout": "output.txt"}
```

## Files

The `files` key denotes an array of JSON Objects (dictionaries), each
representing one file to be uploaded. Each object must specify

- a file name (as string)
- length (as integer, in bytes)

```
{"status": "pass", "files": [{"name": "foobar.log", "length": 100}]}
```

After we receive such a result, we start treating any incoming data as binary
`foobar.log` contents, reading exactly 100 bytes, after which we swich back
to parsing results (see [TEST_CONTROL.md](TEST_CONTROL.md) for details).

If a result specifies multiple `files` entries, we read their contents in the
order they were specified in the `files` array, splitting the incoming binary
data stream by the lengths specified.

A file name may contain zero or more `/`, but it must not start with `/`.

A sanity check will cause an error (discarding the result) if you specify
multiple identical file names within one result.  
However, this does not extend across results - a second result with the same
`name` specifying the same `files` `name` results in undefined behavior
(the file may be overwritten by us, result discarded, or error triggered).

### Full binary stream example

An example of reporting two results, first with two files `A` and `B`, using
full [TEST_CONTROL.md](TEST_CONTROL.md) syntax, incl. _control lines_, **exactly
as they would appear in the binary stream** (any newlines are part of the data,
not for readability here):

```
result 109
{"status": "pass", "name": "some/test", "files": [{"name": "A", "length": 13}, {"name": "B", "length": 13}]}contents of Acontents of Bresult 43
{"status": "pass", "name": "another/test"}
```

Explaining the example:

1. `result 109\n` _control line_ is read, `result` is identified as a
   _control word_
1. The `result`-specific parser is called, with `109` passed via arguments,
   and given control over the input.
1. The parser reads the next 109 bytes (JSON with first result) and parses them
   via a JSON decoder.
1. The result data indicate a 13-byte file `A` and a 13-byte file `B`.
1. The parser reads the next 13 bytes (`contents of A`) as file content of `A`.
1. The parser reads the next 13 bytes (`contents of B`) as file content of `B`.
1. The parser then handles the result how it sees fit (write to CSV?).
1. No more files were specified, nothing more for the `result` parser to read,
   it exits, giving control back.
1. `result 43\n` _control line_ is read, `result` identified as a _control word_
1. The `result`-specific parser is called, with `43` passed via arguments,
   and given control over the input.
1. The parser reads the next 43 bytes (JSON with second result) and parses them
   via a JSON decoder.
1. The parser handles the result how it sees fit (write to CSV?), no files
   specified, nothing more to read.
1. The parser exits, giving control back.

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
{"name": "some/test", "status": "error", "partial": true, "files": [{"name": "out.log", "length": 29}]}
this is out.log with newline\n

{"name": "another/test", "status": "pass"}

{"name": "some/test", "partial": true, "files": [{"name": "report.log", "length": 32}]}
this is report.log with newline\n

{"name": "some/test", "status": "pass"}
```
will result in us parsing it as equivalent to
```
{"status": "pass", "name": "another/test"}

{"status": "pass", "name": "some/test", "files": [{"name": "out.log", "length": 29}, {"name": "report.log", "length": 32}]}
this is out.log with newline\n
this is report.log with newline\n
```
because `another/test` was a regular non-`partial` result (reported
immediately), and the last `some/test` result also lacked `partial`, so it was
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
{"status": "pass", "name": "some/test", "testout": "test.log"}
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

- Any invalid JSON or deviation from this spec causes the whole control channel
  (per [TEST_CONTROL.md](TEST_CONTROL.md)) to shut down with an error, to avoid
  data corruption and force the user (test) to fix the issue.
- `files` inside a `"partial": true` result are written out immediately,
  to on-disk files with the names specified, they are not held back until
  the full result is assembled from partial reports.
  - This can cause issues if two partial results for the same `name` specify
    the same file name - an error will be triggered, because that file already
    exists.
  - This abnormality is a result of efficiency; it is not feasible to keep
    file contents for partial results in memory, or as open file descriptors
    for temporary files.

### Custom result keys

Any JSON keys other than those specified in [Basic format](#basic-format) are
ignored - your test can freely add custom keys to the results, ie.

- `note` for adding extra details about a result (like tmt has)
- `rerun` if a test tries to run its logic several times before `pass`-ing
- `group` for result grouping by a tag/name, in a 3rd party software

Note however that it's a good idea to prefix keys with something unique to you,
to prevent conflicts with future changes to this spec.
