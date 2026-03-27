# API Rules

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
   of the API and are thus implementation-specific.

## Using implementation-specific arguments

If your code needs to make use of the extended functionality of a specific
implementation, it can check an instance using `isinstance()` and then safely
pass non-API arguments:

```python
def serve_to_employees(brewer):
    if isinstance(brewer, CoffeeBrewer):
        intake(ingredients, grind=False)
    else:
        intake(ingredients)
```

Using `inspect` to get a function signature is not recommended as the meaning
of a named argument may be different between implementations.
