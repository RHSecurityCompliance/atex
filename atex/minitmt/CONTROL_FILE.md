# Control file

A way to communicate with test runner from inside the test.

## UNIX Domain Socket

The control file is accessible to the test at an absolute path specified in the
`MINITMT_CONTROL_FILE` env variable, as a listening UNIX socket (expects
connections from clients via `SOCK_STREAM`, it does not support `SOCK_DGRAM`),
mainly to preserve compatibility with UNIX socket forwarding via OpenSSH.

A client may send one or more `\n`-separated (`0x0a`) control commands within
one connection. A malformed or unknown command will terminate the connection,
for safety (to reset the stream state for further commands / avoid corruption).

## Format

Each line starts with a _control word_, optionally followed by a space (`0x20`)
and argument(s) in an undefined control-word-specific format.

```
word1\n
word2 arg1 arg2\n
word3 {"json": "here"}\n
```

In addition, the parser recognizes only the control word + the following space
and otherwise gives complete control over the UNIX connection to per-word
handlers. A control word handler can therefore embed additional (even binary!)
data into the stream, before handing control over back to the global parser.

```
write_file /tmp/foobar 21\n
some!@#$%^binary_dataword2 arg1 arg2\n
```

In this example, the global control file parser read `write_file` as a word,
and called its handler, which then read `/tmp/foobar` as a filename, `21` as
length, the `\n` as end-of-arguments, and then it read 21 bytes (in binary)
from the UNIX socket stream (`some!@#$%^binary_data`), writing them to
`/tmp/foobar`.  
It then handed control back to the global control file parser, which read
`word2` as another control word, called its parser, etc., etc.

If any handler encounters any error while parsing its arguments or any other
data, it will simply close the connection.

## Supported control words

(Currently a proposal.)

- **`result`**
  - ie. `result {"name": ...}\n`
  - Used for reporting test results using the format described in
    [RESULTS.md](RESULTS.md).
  - Each result must be transmitted on a single line (terminated by `\n`),
    multi-line JSON is not allowed.
- **`restart`**
  - ie. `restart\n`
  - Tells the controller to expect a disconnect and try to re-start the test
    (attempting to connect to the SUT).
  - Useful for expecting a reboot done by the test.
  - The overall waiting-to-connect is still subject to test duration,
    so a test should modify `duration` (see below) before `restart` if it
    expects a crash (shorten duration to ie. 600 seconds) or to account
    for extra time spent rebooting (increase duration end by ie. 300 seconds).
  - Can be given a value, ie. `restart 300\n` to give-up reconnect early,
    before duration runs out; the number given doesn't go beyond existing
    `duration`, it just is a way for test to retain its metadata-defined
    `duration` while having sensible reboot fail-safe time.
  - After a successful reconnect, the restart flag is re-set, the test runner
    will not expect a second restart unless the test specifies `restart` again
- **`duration`**
  - ie. `duration 1000\n` or `duration +60\n` or `duration -60\n`
  - Used to set or modify fmf-metadata-defined `duration` upper limit
  - Useful when a very long-running test iterates over (and reports) many
    small results, expecting each to take ie. 30 seconds, but the test overall
    taking ie. 24 hours - having a keepalive watchdog might be useful.
  - An absolute value sets a new maximum `duration` for the test and re-sets
    the current test runtime to `0` (effectively giving it the full new
    `duration` from that moment onwards).
  - A relative value adjusts the maximum `duration` without resetting current
    test run time.
  - A special value of `refresh` can be used to set the test run time to `0`,
    effectively re-starting the duration timer.
    - (Useful with duration set low (ie. 60 seconds) and the test regularly
       pinging the runner, ie. after every `rlRun`), as a keepalive-based
       watchdog.
- **`abort`**
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
