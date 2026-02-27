# Command line interface to atex

Submodules (subpackages) of this one must define a module-level dict with
these keys:

- help
  - short oneliner about what the submodule is about (for argparse `--help`)
- aliases (optional)
  - tuple of aliases of the module name, for argument parsing
- args
  - function (or other callable) for argument specification/parsing,
    gets passed one non-kw argument: argparse-style parser
- main
  - function (or other callable) that will be called when invoked by the user,
    gets passed one non-kw argument: argparse-style Namespace

This module-level dict must be named `CLI_SPEC`.
