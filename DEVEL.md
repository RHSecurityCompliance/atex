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

## Blocking functions

- this is about `get_remote(block=True/False)` and similar ones
- the key difference is that `True` blocks until the function has something
  to return, or until Exception, and `False` does not
- it does NOT mean that `False` cannot block on any IO
  - ie. `False` can still wait 1 second for HTTP GET to finish, effectively
    "blocking" the parent process, but the important part is that it doesn't
    block all the way until a Remote is provisioned
- best practice for `False`: never block on IO, offload any IO requests
  to internal threads, incl. URL retrieval, on-disk file read/writes, etc.,
  have the `False`-called code only check python variables on whether XYZ
  is ready or not
  - but, often, best practice != reality, and code complexity also has to be
    considered
- finally, `False` is not a guarantee, just a wish of the caller; if a function
  cannot be implemented non-blocking, it should behave as if called with `True`
  rather than throwing an error
  - any code using `False` should still theoretically work given that `False`
    provides no guarantees on how quickly it returns, it will just work more
    slowly

- TODO: `Remote.release(block=True/False)`
  - dictates whether to block until the remote is successfully released or
    the release fails with an Exception (`True`), or whether the caller doesn't
    care and wants to fire off the release, to be handled in some background
    thread (set up by the Remote/Provisioner)
