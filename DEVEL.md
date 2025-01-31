# Misc development notes

## Contributing

TODO - coding style

## Release workflow

NEVER commit these to git, they are ONLY for the PyPI release.

1. Increase `version = ` in `pyproject.toml`
1. Tag a new version in the `atex-reserve` repo, push the tag
1. Point to that tag from `atex/provisioner/testingfarm/api.py`,
   `DEFAULT_RESERVE_TEST`
1. ...
1. `python3 -m build`
1. `pip install -U twine`
1. `python3 -m twine upload dist/*`

## Parallelism and cleanup

There are effectively 3 methods of running things in parallel in Python:

- `threading.Thread` (and related `concurrent.futures` classes)
- `multiprocessing.Process` (and related `concurrent.futures` classes)
- `asyncio`

and there is no clear winner (in terms of cleanup on `SIGTERM` or Ctrl-C):

- `Thread` has signal handlers only in the main thread and is unable to
  interrupt any running threads without super ugly workarounds like `sleep(1)`
  in every thread, checking some "pls exit" variable
- `Process` is too heavyweight and makes sharing native Python objects hard,
  but it does handle signals in each process individually
- `asyncio` handles interrupting perfectly (every `try`/`except`/`finally`
  completes just fine, `KeyboardInterrupt` is raised in every async context),
  but async python is still (3.14) too weird and unsupported
  - `asyncio` effectively re-implements `subprocess` with a slightly different
    API, same with `asyncio.Transport` and derivatives reimplementing `socket`
  - 3rd party libraries like `requests` or `urllib3` don't support it, one needs
    to resort to spawning these in separate threads anyway
  - same with `os.*` functions and syscalls
  - every thing exposed via API needs to have 2 copies - async and non-async,
    making it unbearable
  - other stdlib bugs, ie. "large" reads returning BlockingIOError sometimes

The approach chosen by this project was to use `threading.Thread`, and
implement thread safety for classes and their functions that need it.  
For example:

```python
class MachineReserver:
    def __init__(self):
        self.lock = threading.RLock()
        self.job = None
        self.proc = None

    def reserve(self, ...):
        try:
            ...
            job = schedule_new_job_on_external_service()
            with self.lock:
                self.job = job
            ...
            while not reserved(self.job):
                time.sleep(60)
            ...
            with self.lock:
                self.proc = subprocess.Popen(["ssh", f"{user}@{host}", ...)
            ...
            return machine
        except Exception:
            self.abort()
            raise

    def abort(self):
        with self.lock:
            if self.job:
                cancel_external_service(self.job)
                self.job = None
            if self.proc:
                self.proc.kill()
                self.proc = None
```

Here, it is expected for `.reserve()` to be called in a long-running thread that
provisions a new machine on some external service, waits for it to be installed
and reserved, connects an ssh session to it and returns it back.

But equally, `.abort()` can be called from an external thread and clean up any
non-pythonic resources (external jobs, processes, temporary files, etc.) at
which point **we don't care what happens to .reserve()**, it will probably fail
with some exception, but doesn't do any harm.

Here is where `daemon=True` threads come in handy - we can simply call `.abort()`
from a `KeyboardInterrupt` (or `SIGTERM`) handle in the main thread, and just
exit, automatically killing any leftover threads that are uselessly sleeping.  
(Realistically, we might want to spawn new threads to run many `.abort()`s in
parallel, but the main thread can wait for those just fine.)

It is not perfect, but it's probably the best Python can do.

Note that races can still occur between a resource being reserved and written
to `self.*` for `.abort()` to free, so resource de-allocation is not 100%
guaranteed, but single-threaded interrupting has the same issue.  
Do have fallbacks (ie. max reserve times on the external service).

Also note that `.reserve()` and `.abort()` could be also called by a context
manager as `__enter__` and `__exit__`, ie. by a non-threaded caller (running
everything in the main thread).


