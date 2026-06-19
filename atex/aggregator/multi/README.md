> [!NOTE]
> This describes a specific implementation of the abstract Aggregator API.
> See also the [documentation of the generic API](..).

# Multiple Aggregator wrapper

This simple wrapper serves a copy of [Test Artifacts](../../executor) supplied
to the `.ingest()` method to multiple other Aggregator instances, passed to
MultiAggregator's `__init__()`.

This is useful in places which take a single Aggregator instance (ie. the
AdHocOrchestrator) but you need the result to be stored to multiple locations,
ie. full results as JSON lines, but a subset of them uploaded to ReportPortal.

```python
from atex.aggregator import jsonl, multi, reportportal
from atex.orchestrator.adhoc import AdHocOrchestrator

json_aggr = jsonl.JSONLinesAggregator(...)
rp_aggr = reportportal.ReportPortalAggregator(...)

with multi.MultiAggregator([json_aggr, rp_aggr]) as aggr:
    orchestrator = AdHocOrchestrator(
        ...
        aggregator=aggr,
        ...
    )
```

MultiAggregator also takes care of starting and stopping all of the passed
aggregators.
