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

All these receive `info` as one of their (positional-only) arguments, which
is a namespace that holds information about the Provisioner, Remote, the test
and anything else that might be useful for the functions.

Depending on the state of the testing, the `info` argument is one of:

- `AdHocOrchestrator.SetupInfo`
  - Has `.provisioner`, `.remote` and `.executor` attrs.
- `AdHocOrchestrator.RunningInfo`
  - Extends `SetupInfo` with `.test_name` and `.artifacts`.
- `AdHocOrchestrator.FinishedInfo`
  - Extends `RunningInfo` with `.exit_code` and `.exception`.

Some functions receive only one type (ie. `run_setup()` only ever gets
`SetupInfo`), some get any of these. Check `type(info)` if you need to access
specific namespace.

## Mixin features

There are several Mixins available to easily customize the behavior of the
orchestrator, typically overriding the functions mentioned above.

All of these can be combined (chained) together, see their docstrings.

- **`LimitedRerunsMixin`** to provide N retries for every test name.
  - By default, AdHocOrchestrator assumes you might want a custom retry logic
    (hence `should_be_rerun()` and not a number), but most users just want
    "if it fails, try it 2 more times".
  - Use the `cond` argument to specify what a "failure" means (all non-zero
    exit codes by default).

  ```python
  class CustomOrchestrator(LimitedRerunsMixin(2), AdHocOrchestrator):
      pass
  ```
  ```python
  class CustomOrchestrator(
      LimitedRerunsMixin(reruns=2, cond=lambda code: code not in [0,2]),
      AdHocOrchestrator,
  ):
      pass
  ```

- **`FMFDurationMixin`** to run longer-running tests sooner.
  - The idea is that, with multiple parallel test executions, you can dedicate
    some of the Remotes to very-long-running tests while the short ones finish
    (and maybe are re-run) in parallel on other Remotes.  
    Basically - you don't want to leave a 12h test toward the end of your test
    run and then it fails, and you need another 12h to rerun it, waiting on the
    one single test running on one Remote the whole time.
  - It takes `fmf_tests` so it can inspect discovered test metadata.

  ```python
  class CustomOrchestrator(FMFDurationMixin(fmf_tests), AdHocOrchestrator):
      pass
  ```

- **`FMFPriorityMixin`** to prioritize some tests over others.
  - You know your tests best. Some fail (and need reruns) way more frequently.
    So give them `extra-priority` as metadata and this mixin will prioritize
    them above/below other tests.
  - Default priority (if not specified) is `0`, larger number = higher priority
    = runs sooner.
  - It takes `fmf_tests` so it can inspect discovered test metadata.

  ```python
  class CustomOrchestrator(FMFPriorityMixin(fmf_tests), AdHocOrchestrator):
      pass
  ```

- **`FMFDestructiveMixin`** to throw away a Remote after a destructive test.
  - If a test has 'destructive' as a tag in its metadata, the Remote it ran on
    will the released and a new one provisioned in its place.
  - Useful for tests that need to "destroy" the OS in order to exercise the
    functionality under test (ie. tools that "harden" the OS).
  - It takes `fmf_tests` so it can inspect discovered test metadata.

  ```python
  class CustomOrchestrator(FMFDestructiveMixin(fmf_tests), AdHocOrchestrator):
      pass
  ```
