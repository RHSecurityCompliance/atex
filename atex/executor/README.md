> [!NOTE]
> This describes a generic API concept - these classes don't actually do
> anything, but they serve as a template for other implementations to follow,
> providing the API described here for you.\
> IOW there exist several Executors for different use cases, but they all
> follow the API described here.

# Executor

A test runner.

It takes a connected [Connection](../connection) and allows you to run
individual tests over it.

```python
with Executor(conn) as e:
    ret1 = e.run_test("some_test", artifacts_dir1)
    ret2 = e.run_test("another_test", artifacts_dir2)
```

- The test names (identifiers) are specific to Executor implementations.
- The artifacts directories are where test results and uploaded files
  are stored (one artifacts dir per one test executed).
  - These must exist as empty directories before `.run_test()` is called,
    ie. from `tempfile.TemporaryDirectory()` or `os.mkdir()`.
- The return values are exit codes from the test scripts, or their equivalent.

(See [FMFExecutor](fmf) for a more complete example.)

The executor would typically prepare the connected system for testing
by uploading tests or installing OS packages (both via the passed Connection)
during its `.start()`, and clean up during `.stop()`.

Both of these are called by the context manager above, but they can be called
manually:

```python
e = Executor(conn)

try:
    e.start()

    e.run_test(...)
    e.run_test(...)
    ...

finally:
    e.stop()
```

## Test Artifacts

Test artifacts is a directory that contains:

- A file named `results`, which is a line-JSON formatted file (complete JSON
  on each line, see https://jsonltools.com/).
- A directory named `files`, which contains files uploaded by the test.

### Results

Each line in the `results` file represents one *result* reported by the test,
meaning a **test can report more than one result**.

```json
{"status": "pass", "name": "first phase"}
{"status": "fail", "name": "second phase"}
{"status": "fail"}
```

Valid JSON object keys include:

- **`status`** (as string): `pass`, `fail`, `info`, `warn`, `skip`, `error`
  - Testing outcome.
  - Other custom values are permitted, these are just the standard ones.
- **`name`** (as string)
  - Subtest name.
  - If not specified, the result is for the test itself.
- **`note`** (as string)
  - Free-form short addendum to the result.
  - For quick explanation of the failure, if available.
- **`files`** (as array/list)
  - Test-provided file paths.
  - Paths relative to (inside) the `files` dir.
  - If the result contains `name`, it is prepended to each of the file paths.

```json
{"status": "error", "name": "syncfs1", "note": "ENOSPC while running test()"}
{"status": "fail", "name": "listxattr2", "files": ["attrs.log", "script.log"]}
{"status": "error", "files": ["testout.log"]}
```

### Files

These are simply any files (typically logs or reports) uploaded or otherwise
provided by the test. The Executor is in charge of extracting these and storing
them inside the `files` dir.

Note that `files` itself can contain a (sub)directory structure, typically
for logs from various subtests (`name`d results), because:

- The `name` itself may contain `/`, ie. `syscalls/accept01`.
- The paths in `files` may also contain `/`, ie. `reports/scan.html`,
  for both un-`name`d results and `name`d ones.

So that ie.

- `{"files": ["log"]}` is found in `files/log`
- `{"files": ["some/log"]}` is found in `files/some/log`
- `{"name": "subtest", files: ["log"]}` is found in `files/subtest/log`
- `{"name": "sub/test", files: ["some/log"]}` is found in `files/sub/test/some/log`

### Special cases

This is intentionally a loose specification, allowing customizations by an
implementation. As such, all these are *technically valid* results:

- `{}` as an empty result
- `{"name": "something"}` as a name without status
- two results for the base test itself:

  ```json
  {"status": "pass"}
  {"status": "fail"}
  ```

In addition to the Executor leaving test artifacts as an empty directory
(and/or raising an exception during `.run_test()`).

Also, an Executor (or a user) can use custom `status` keywords, or append
custom keys to the JSON object, ie. `"rerun": 3` or `"group": "syscalls"`,
as anything outside of this spec is not forbidden.
