> [!NOTE]
> This describes a specific implementation of the abstract Aggregator API.
> See also the [documentation of the generic API](..).

# ReportPortal Aggregator

This provides basic ingesting functionality via ReportPortal `/v2/` API to
a ReportPortal instance.

```python
from atex.aggregator.reportportal import (
    ReportPortalAggregator,
    ReportPortalAPI,
)

api = ReportPortalAPI(
    url="https://report-portal-instance",
    project="foobar_personal",
    token="rp-mytoken_ABCDEF",
)

with ReportPortalAggregator(api, launch_name="ER#12345 some-component") as aggr:
    aggr.ingest("9.8@x86_64", "/some/test", test_artifacts_dir)
    ...
```

## Nested vs flat

Two test-reporting modes are supported, depending on whether the `join_subtest`
parameter was passed.

1. If it was not (default), subtests are reported as nested items under the
   respective tests.

   This has the advantage of keeping the real tests on the last leaf node that
   still counts for statistics and is observed by the RP AI analyzer.

   ```
   test1
   -> subtest1
   -> subtest2
   test2
   -> subtest1
   ```

2. If it was set (to ie. `/`), it is used as a separator to prefix every subtest
   result name with its parent test name, plus the separator.

   This flattens all tests and subtests into one big list, which is then used
   for statistics and RP AI analysis.

   Useful if you have only a few real tests, but large amounts of subtests -
   in that case, one failing subtest might be incorrectly AI-correlated with
   another one just because they share the one common test name.

   ```
   test1/subtest1
   test1/subtest2
   test2/subtest1
   ```

## Promising tests

Sometimes, you want to fire off a test run and immediately see the to-be-run
tests in the ReportPortal UI as "in progress", and then watch as they become
completed, matching some other result systems, ie. Nitrate.

With the ATEX Aggregator API, this isn't easily possible as an Aggregator does
not know, in advance, all the tests and subtests that are to be reported.

However you do (or your code that discovers tests), and you can pass that list
via `tests_promise`:

```python
ReportPortalAggregator(
    ...
    tests_promise=[
        ("platform1", "first_test"),
        ("platform1", "second_test"),
        ("platform2", "first_test"),
    ],
    ...
)
```

ReportPortalAggregator will then literally go over this list and report all the
tests to ReportPortal.

When the same test names are `.ingest()`ed later, the same items are reused
and finalized with the real test status, logs, etc.

Note that promising only test names (and not subtests) when using flat results
(with `join_subtest`) leads to the test itself being ordered well above
the subtests in the RP UI, due to only the test being started early.\
The easy workaround is to just sort by Name in the UI.

## Launch reruns

ReportPortal natively supports re-starting a launch - all you need is its UUID
and the API-using code is basically identical. It itself then nicely correlates
a second occurrence of a given test in the rerun with the first, and displays it
as a "retry" in a special UI element.

All you need is to pass

```python
ReportPortalAggregator(
    ...
    launch_rerun="UUID-HERE",
    ...
)
```

instead of `launch_name`.

Partial reruns are supported too, just make sure you don't specify the full
list via `tests_promise` (if you're using that functionality). Promise only
what you plan to rerun.

## Rerunning failed tests only

You can use the `get_existing_tests()` function on an existing launch UUID
to get platform/test names, filtered by a given list of statuses.

This can be used to trim the would-be-executed list of tests down to just
the failed ones (or to filter out any passing/info/skipped ones).

This is the main reason this aggregator exposes ReportPortalAPI directly
instead of the constructor having url, project and token arguments.

When used with FMFExecutor:

```python
from atex.executor.fmf import discover
from atex.aggregator.reportportal import ReportPortalAPI, get_existing_tests

all_tests = discover(
    "path/to/repo_with_tests",
    plan="/plans/sanity",
    context={"distro": "rhel-9.6", "arch": "x86_64"},
)
tests_to_run = list(all_tests.data)

api = ReportPortalAPI(...)

passed = get_existing_tests(
    api,
    "LAUNCH-UUID-HERE",
    ["passed", "skipped", "in_progress", "info"],
)

for platform, test in passed:
    if platform == "rhel-9.6@x86_64" and test in tests_to_run:
        tests_to_run.remove(test)

# pass filtered tests_to_run to an Orchestrator or whatever
```

The `platform` above is the same as the platform given to an Orchestrator
(or an Aggregator's `.ingest()`, for that matter).

More realistically, you'd iterate over the existing tests once and match
multiple platforms in the loop body, configuring reruns across all platforms
at the same time. (Or construct a dict from the yielded tuples.)

## Customizing log upload

The `.decide_file()` method can be overridden in a subclass to refine when
a test-uploaded file should be stored in ReportPortal.

You can further decide what log level it should have (ie. INFO stores, but
avoids AI analysis) or if it should be inline on the page or stored as an
attachment (requires click-through to open in browser or download).

Also, you can choose to store logs for passing tests too, or selectively
discard logs by platform or test name.

## Customizing subtest reporting

The `.decide_subtest()` method can be overridden to either not report any
subtests to the ReportPortal instance, or to report only a subset of them,
ie. for specific platform or test names.

Useful for test suites with huge amounts of results, to lighten the load
on ReportPortal's database.
