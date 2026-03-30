# Test Control

A way to communicate with the runner (FMFExecutor) from inside the test.

## File Descriptor

The test-to-runner communication is facilitated via a pre-opened file descriptor
(how the data is transferred to the runner is implementation-specific).

The file descriptor number is provided via the `ATEX_TEST_CONTROL` environment
variable.

The test can simply write to this descriptor using the syntax specified below.
It should never read from it, the stream is one-directional.

## Format

The stream consists of *control lines*, consisting of ASCII characters (0-127),
terminated by a newline (`0x0a`).

Each *control line* starts with a *control word*, optionally followed by a space
(`0x20`) and argument(s) in an undefined control-word-specific format.

```
word1\n
word2 arg1 arg2\n
word3 any arbitrary <data>12345</data> here\n
```

There is a parser specific to each *control word*, and, when called, is given
the remainder of the *control line*, without the *control word*, the
optional space after it, and the terminating newline.

This parser is also given full (binary!) access to the stream, allowing it to
read any further (even binary) data from it, before returning control back to
the global stream handler.

### Example

(Imaginary example for illustration, doesn't actually work.)

```
write_file /tmp/foobar 21\n
some!@#$%^binary_dataword2 arg1 arg2\n
```

In this example, the global stream handler read `write_file /tmp/foobar 21\n`
and recognized `write_file` as a *control word*, calling its parser.\
This parser then received `/tmp/foobar 21` as arguments, along with the open
stream handle.

The parser then interpreted `/tmp/foobar` as a destination filename on the host,
and `21` to mean "read 21 more bytes". It then read further 21 (binary) bytes,
`some!@#$%^binary_data` and wrote them to `/tmp/foobar`, before handing control
back to the parent global stream handler.

The parent then read `word2 arg1 arg2\n` as another *control line*, calling
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
  - Typically used by a remote test wrapper, setting the exit code returned by
    the (real) test.
  - This exists to differentiate between a test returning 255 and the ssh client
    on the runner returning 255 due to a connection issue. For this reason,
    the controller **always** expects the remote command (wrapper) to return 0,
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
    - The save/restore logic works a bit like a stack, so ie. library code can
      use its own save/restore commands while already running in a saved
      context.
- **`disconnect`**
  - ie. `disconnect\n`
  - Signals the runner to disconnect the control channel and wait for test
    wrapper exit, ignoring its exit code (likely non-zero due to OS reboot).
    The runner then disconnects the whole Connection and keeps trying to connect
    until the test duration expires, re-starting the test upon successful
    connection.
  - `TMT_REBOOT_COUNT` and `TMT_TEST_RESTART_COUNT` are incremented after
    such reconnect.
    - These are provided for compatibility only, the test should ideally use its
      own stateful logic using on-disk files to track if it was run before.
  - If the Connection used by the runner is disconnected without `disconnect`
    sent over test control, a TestAbortedError is raised.
  - Note that `disconnect` needs to be issued before **every** reboot, the flag
    is cleared after a successful Connection disconnect.
  - Note that `duration save` + `restore` can be used to subtract the disconnect
    time from test run time (as long as the test starts up again and does
    `restore`). Useful for reboots that might take up to 30 minutes on some HW.
- **`noop`**
  - ie. `noop\n`
  - Do nothing.
  - Useful to check, from the test side, whether the control is alive - if not,
    the write should fail with `EPIPE`.
  - Intended for use in a loop, after `disconnect`, to wait for the remote end
    to close the control channel before rebooting an OS, ie.
    - `disconnect\n`
    - `noop\n`
    - `noop\n`
    - `noop\n` - write returns `EPIPE`, the channel is now disconnected

## Limitations

A *control line* is at most 4096 bytes long, incl. the terminating newline.
An implementation may therefore limit the memory used for an internal buffer
(for repeated `read()` calls) to 4096 bytes before it starts discarding data,
potentially reading (discarding) a corrupted *control line*.

Obviously, this does not apply to other binary data sent over the test control
channel. Just *control lines* with words and arguments.
