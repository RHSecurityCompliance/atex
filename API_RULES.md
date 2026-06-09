# API Rules

## Abstract API

As [the README specifies](README.md), the API contains abstract classes defining
various subsystems through methods.

```python
class Brewer:
    def intake(self, ingredients):
        """Input `ingredients` for brewing."""

    def brew(self):
        """Brew the beverage and return it."""
```

```python
class CoffeeBrewer(Brewer):
    def __init__(self, kind, strength=None):
        self.kind = kind
        self.strength = strength if strength is not None else 5

    def _the_actual_brewing(self):
        ...

    def intake(self, ingredients, *, grind=True):
        ...

    def brew(self, *, speed=100):
        return self._the_actual_brewing()
```

The basic rules are:

1. If an abstract API class defines a method, the implemented version of it
   must be callable without any extra positional or keyword arguments.
   - Implementation may extend both positional and keyword arguments with its
     own, but they must have defaults.

1. If an abstract API method consumes all `*args`, the implemented version
   must not add any custom positional arguments.

1. If an abstract API method has a wildcard `**kwargs`, the implemented version
   may have its own keyword arguments injected before it.
   - Note that this is risky if the implementation-specific keywords are
     not unique enough.

1. Return values of the abstract API methods **are part of the API** too.

1. Any other methods or attributes, including `__init__`, are out of scope
   of the abstract API and are thus implementation-specific.

### Using implementation-specific arguments

If your code needs to make use of the extended functionality of a specific
implementation, it can check an instance using `isinstance()` and then safely
pass non-API arguments:

```python
def serve_to_employees(brewer):
    if isinstance(brewer, CoffeeBrewer):
        brewer.intake(ingredients, grind=False)
    else:
        brewer.intake(ingredients)
```

Using `inspect` to get a function signature is not recommended as the meaning
of a named argument may be different between implementations.

## API stability

Generally speaking:

- Any class methods and attributes that **do not** begin with `_` are considered
  stable.
- Any module-level objects defined in `__all__` (importable via wildcard) are
  considered stable.
- Anything else is unstable.

This applies to abstract API classes, their specific implementations as well as
any supporting functions or constants.

Here, "stable" means that they are guaranteed to exist and retain their callable
signature (or attribute data type) **within the same project major version**.

This means you can ie. `pip install 'atex>=1,<2'` and always get the latest
`1.x` version with the same stable API, and switch to a `2.x` API on your terms.

## Accessing/modifying private `_` attributes

When subclassing, you might want to sometimes access the parent's private
attributes or methods - this is fine and permitted, as long as you realize that
these are **not stable** and may change **within** a major version.

It's up to you to keep your subclass updated to continue working if the parent
project changes the implementation.
