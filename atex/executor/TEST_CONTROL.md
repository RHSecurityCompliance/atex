# Test Control

A way to communicate with test runner from inside the test.

## File Descriptor

The test-to-runner communication is facilitated via a pre-opened file descriptor
(how the data is transferred to the runner is implementation-specific).

The file descriptor number is provided via the `ATEX_TEST_CONTROL` environment
variable.

The test can simply write to this descriptor using the syntax specified below.
It should never read from it, the stream is one-directional.

## Format

The stream consists of _control lines_, consisting of ASCII characters (0-127),
terminated by a newline (`0x0a`).

Each _control line_ starts with a _control word_, optionally followed by a space
(`0x20`) and argument(s) in an undefined control-word-specific format.

```
word1\n
word2 arg1 arg2\n
word3 any arbitrary <data>12345</data> here\n
```

There is a parser specific to each _control word_, and, when called, is given
the remainder of the _control line_, without the _control word_`, the
optional space after it, and the terminating newline.

This parser is also given full (binary!) access to the stream, allowing it to
read any further (even binary) data from it, before returning control back to
the global stream handler.

### Example

```
write_file /tmp/foobar 21\n
some!@#$%^binary_dataword2 arg1 arg2\n
```

In this example, the global stream handler read `write_file /tmp/foobar 21\n`
and recognized `write_file` as a _control word_, calling its parser.  
This parser then received `/tmp/foobar 21` as arguments, along with the open
stream handle.

The parser then interpreted `/tmp/foobar` as a destination filename on the host,
and `21` to mean "read 21 more bytes". It then read further 21 (binary) bytes,
`some!@#$%^binary_data` and wrote them to `/tmp/foobar`, before handing control
back to the parent global stream handler.

The parent then read `word2 arg1 arg2\n` as another _control line_, calling
`word2` parser, etc., etc.

## Supported control words

- **`result`**
  - ie. `result 123\n`
  - Used for reporting test results using the format described in
    [RESULTS.md](RESULTS.md).
  - The argument specifies JSON object length (in bytes) to be read, following
    the control line.
  - This object might be single-line or multi-line, we don't care as long as
    the length in bytes is accurate.
  - The JSON might contain further logic for reading more binary data (ie. log
    file contents), which is handled internally by the `result` parser.
- **`exitcode`**
  - ie. `exitcode 1\n`
  - Typically used by a remote test wrapper (runner), setting the exit code
    returned by the (real) test.
  - This exists to differentiate between a test returning 255 and the ssh client
    on the controller returning 255 due to a connection issue. For this reason,
    the controler **always** expects the remote command (wrapper) to return 0,
    and treats anything else as a non-test failure.
  - If a remote test wrapper does not write this control word, that is also
    considered a fatal non-test failure.
- **`duration`**
  - Sets or modifies the `duration` specified in test FMF metadata.
  - An absolute value, ie. `duration 15m\n`, sets a new maximum duration
    for the test and re-sets the current test runtime to `0` (effectively
    giving it the full new duration from that moment onwards).
    - Useful when a very long-running test iterates over (and reports) many
      small results, expecting each to take ie. 30 seconds, but the test overall
      taking ie. 24 hours - having a keepalive watchdog might be useful.
    - The time specification follows the same syntax as FMF-defined `duration`.
  - A special value starting with `+` or `-`, ie. `duration +60\n`, adjusts
    the maximum duration upper limit without changing current test run time.
    - Useful for dynamically inserting a lengthy test section into the test,
      giving it extra time, without overriding FMF-defined duration.
  - A special value of `save` saves the current value of test run time, allowing
    a subsequent value of `restore` to re-set test run time to the saved value.
    - Useful when performing infrastructure tasks (log upload) that may take
      unknown amount of time that should not be deducted from the test duration.
    - Can be used as `duration save` + `duration 600` + perform infra action
      + `duration restore` to add a 600sec safety timer for the infra task.
    - The save/restore logic works with a stack, so ie. library code can use its
      own save/restore commands while already running in a saved context.
- **`reconnect`**
  - ie. `reconnect\n`
  - Signals to the controller that an upcoming ssh disconnect is intentionally
    caused by the test (ie. due to a reboot or temporary firewall change),
    instructing it to reconnect and restart the test.
  - If ssh disconnect happens without this flag, the controller treats it as
    an abnormal situation and will abort the testing on that remote.
  - The flag is automatically cleared on new reconnect and needs to be issued
    before every disconnect.
  - To always reconnect and always restart the test, the test can issue
    `reconnect always\n` once.
    - Useful for ie. reserve background tasks that should be immune to OS
      reboots caused by the user.
  - Note that `duration save` + `restore` can be used to subtract the disconnect
    time from test run time (as long as the test starts up again and does
    `restore`). Useful for reboots that might take up to 30 minutes on some HW.
- **`setenv`** (IDEA ONLY)
  - ie. `setenv FOO=some value\n`
  - Exports one KEY=VALUE environment variable to the test environment.
    - These are applied *after* FMF-defined env variables, potentially
      overriding them.
  - Note that this does not impact the currently running test, but does impact
    any test restarts caused by disconnects.
  - Useful to keep track of test state across reboots, ie.
    - FMF-defined metadata have `environment: PHASE: setup`
    - Setup-related test code sends `setenv PHASE=exec\n` and reboots
    - Exec-related test code sends `setenv PHASE=cleanup\n` and reboots
    - Cleanup-related test code cleans up and exits cleanly with 0
- **`abort`** (IDEA ONLY)
  - ie. `abort\n`
  - Forcibly terminate test execution from the runner (and potentially destroy
    or release the OS environment).
- **`addtest`** (IDEA ONLY)
  - ie. `addtest /some/fmf/test VAR1=abc VAR2=123`
  - Schedule a new fmf-defined test to be run, with the specified env vars.
  - Useful for dynamically-created tests
    - Some setup test that downloads test suite, creates 1000 tests based on
      running some code to list test cases.
    - Unlike one test reporting 1000 results, this allows true parallelization.

## Limitations

A _control line_ is at most 4096 bytes long, incl. the terminating newline.
An implementation may therefore limit the memory used for an internal buffer
(for repeated `read()` calls) to 4096 bytes before it starts discarding data,
potentially reading (discarding) a corrupted _control line_.
