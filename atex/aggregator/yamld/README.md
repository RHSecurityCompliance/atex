> [!NOTE]
> This describes a specific implementation of the abstract Aggregator API.
> See also the [documentation of the generic API](..).

# YAML Document Aggregator

This Aggregator collects reported results into a single YAML file, each test
result into a new `---` separated **YAML document**.

```yaml
---
first test result here
---
second result here
---
third here
```

This allows efficient streamable reading as the reader has to only store one
result in memory while parsing it.

Note that any subtest results the test may have reported are stored inside the
one YAML document too, so this format is not suited for one test reporting
millions of subtest results. Use [JSONLinesAggregator](../jsonl) for that.

## Format

- `platform` and `name` are the strings given to `.ingest()`,
- `status`, `files`, `note` and `subtests` come from the ingested
  [Test Artifacts](../../executor)

For example,

- `aggregated/results.yaml`

  ```yaml
  ---
  platform: 9.8@x86_64
  name: /some/test
  status: pass
  ---
  platform: 10.2@s390x
  name: /unit/syscalls
  status: pass
  files:
    - full_output.txt
  subtests:
    - name: accept
      status: pass
      files:
        - test.txt
    - name: connect
      status: fail
      files:
        - test.txt
      note: 'Got errno: ECONNABORTED'
    - name: open
      status: warn
      files:
        - test.txt
  ---
  platform: 11.0@x86_64
  name: /ltp
  status: pass
  note: 'Suite version: 20260130'
  subtests:
    - name: syscalls/alarm01
      status: pass
      files:
        - test.out
    - name: syscalls/socketpair02
      status: pass
      files:
        - server/test.out
        - client/test.out
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

If subtest name or note missing in test artifacts, it is omitted in the YAML
(eg. `note: null` never appears).

## Examples

```python
with YAMLDocumentAggregator("results.yaml", "uploaded_files") as aggr:
    aggr.ingest("9.8@x86_64", "/some/test", test_artifacts_dir)
```
