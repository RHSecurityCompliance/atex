# Misc development notes

## Coding style

This project mostly (fully?) follows PEP8 - it makes some creative choices
compared to others, but still within the bounds of what PEP8 mentions as valid.

- Line length up to 99 characters, but try to keep docstrings and comments
  within 80 if possible.
  - Keep Markdown docs within 80 characters too, except for links.
- No type hints (see a dedicated section below on that).
- Always double-quote (`"`) strings, unless a literal double quote needs to
  appear inside, in which case use single quotes (`'`) for the string itself.
- Generally avoid backslashes as line breaks, use parentheses to define
  multi-line content (even for string concatenation).
- Generally prefer newer Python features over older ones.
  - ie. `pathlib.Path` over `os.path`
- Use `:=` only where it makes the code more readable.

Multi-line `if` statements or function calls should put the closing `)` on
its own line, indented to the same level as the starting statement, ie.

```python
if (
    some_thing and
    not some_other_thing
):
    conditioned_code_here

func_call(
    arg1, arg2, arg3,
    arg4="foo",
    arg5="bar",
)
```

Similarly, don't strictly follow one-arg-per-line, try to instead maximize
readability - if multiple args look messy in your case (ie. passing kwargs),
put each on its own line.

Generally speaking, when in doubt, see how the rest of the project looks like,
and what `ruff` and other Pull Request checks allow.

## Contributions

- Q: "I created a Provisioner, could you please include it?"
- A: Maybe.

ATEX is at its best as a distributed ecosystem - people creating base API
implementations on their own and sharing them with the community using repos
under their control - there is no big benefit from centralized development
(unlike projects that compile from source code).

Feel free to create a git repo with your code (and `pyproject.toml`, etc.)
and tell people to just install it alongside base ATEX:

```shell
pip install atex git+https://gitwhatever.com/your/repo.git
```

If you depend on a specific ATEX API version, you can use branch/tag names:

```
pip install 'atex>=1,<2' git+https://gitwhatever.com/your/repo.git@version1
```

(You could also declare `atex` (even a specific version) in your
`pyproject.toml` and then just use your URL alone.)

This works best for more domain-specific implementations (ie. an Executor
that can run tests for an in-house framework used by your team) - if you made
something with much wider reach that you believe would be generally useful,
feel free to submit an upstream issue for inclusion into base ATEX.

But keep in mind the base project's code style and allergy towards adding
additional PyPI dependencies.

If unsure, reach out and ask first - no point in putting a ton of work into
a PR that might never be merged.

## Release workflow

NEVER commit these to git, they are ONLY for the PyPI release.

1. Tag a new version in this repo and push the tag
1. Set appropriate `version = ` in `pyproject.toml`
1. `git status --ignored` to check what would be cleaned
1. `git clean -fdx`
1. `python3 -m build`
1. `pip install -U twine`
1. `python3 -m twine upload dist/*`

## Public vs private attributes

In general, prefer attributes assigned from `__init__()` arguments to be public,
along with any publicly-documented attributes. Prefix internal-only attributes
with `_` to hide them.

## SSH with -T (RequestTTY) problems

We don't allow pseudo-tty allocation via SSH, Podman or any other Connection
because **it can bypass stdout/stderr redirect** done by the test wrapper,
messing up the control channel (`TEST_CONTROL.md`).

Normally, we redirect `stdout` of the Connection to be the control channel,
leaving `stdin` / `stderr` to be used by the test. However, a clever test can
(even accidentally by launching a tty emulator) regain access to the original
`stdout`, often closing it when the tty emulation ends, causing Executor to
either report EOF, or straight out lose the session with ie.

```
TestAbortedError(test wrapper unexpectedly exited with 255 and disconnect was not sent via test control)
```

To avoid this, we always treat the `ATEX<->SUT` connection as sacred, TTY-less,
to guarantee that a `dup()` of `stdout` (to a higher `fd` number), followed by
`dup2(2, 1)` can never be reversed accidentally.

(A malicious test could write bogus data to `ATEX_TEST_CONTROL` anyway, that's
beside the point.)

## Type hinting

It's a design choice of this project to *not* use python type hints.

The main reason is to keep the API simple to read and use - even for beginner
Python programmers.

There has been a decent effort to try using them, see commit
0e92fbbb5083f3aa7884a814583bb2ec46ce5078 - the idea was to use them only for
user-facing APIs where they would make the most sense as self-documenting
function arguments and return values, without the overhead of using them in the
entire codebase.

And it **mostly worked** - modern Python provides nice ways of defining more
or less specific types, depending on project preferences, ie. a `Sequence`
instead of prescribing a `list` specifically.

But the key issue is that automated tools like `mypy` cannot reasonably work
with only partially-typed codebases. Especially the dynamically-imported `util`
would need hardcoded "stub files" with pre-resolved modules.\
So the main benefit of static typing - type checking - wouldn't work without
the entire codebase switching to static typing.

Even the smaller benefits like IDE GUIs checking for types on-the-fly aren't
as widespread amongst Python programmers as it seems - only a fraction of users
actually use them, especially amongst QA people.

OTOH type hints made reading the API (in the source) a lot harder by introducing
extra visual clutter, needing each argument to be on its own line, etc., and -
overall - this, along with very limited usefulness, led to them being reverted,
and the project adopting a "no type hints pls" stance.

If the project's source was not The Primary Interface for its users, they would
have likely remained.
