"""
Provides a namedtuple-inspired frozen mapping-backed data structure.

    class MyMap(NamedMapping):
        pass

    m = MyMap(a=123, b=456)

    m["a"]      # 123
    m.a         # 123
    m["a"] = 9  # KeyError (is read-only)
    m.a = 9     # AttributeError (is read-only)

Like namedtuple, you can specify required keys that always need to be given
to the constructor:

    class MyMap(NamedMapping, required=("key1", "key2")):
        pass

    m = MyMap(a=123, b=456, key1=999)  # KeyError (key2 not specified)

Similarly, you can specify defaults (for required or non-required keys),
as a dict, that are used if omitted from the constructor:

    class MyMap(NamedMapping, defaults={"key": 678}):
        pass

    m = MyMap()  # will have m.key == 678

A class instance can unpack via ** with the entirety of its mapping contents:

    m = MyMap(key2=456)
    both = {'key1': 123, **m}  # contains both keys

You can also chain (append to) required / default values through inheritance:

    class MyMap(NamedMapping, required=("key1",), defaults={"key2": 234}):
        pass

    class AnotherMap(MyMap, required=("key3",))
        pass

    m = AnotherMap()      # KeyError (key1 and key3 are required)

    isinstance(m, MyMap)  # would be True

When instantiating, it is also possible to copy just the required keys from
another dict-like object (does not have to be a parent of the class):

    class SmallMap(NamedMapping, required=("key1", "key2")):
        pass

    class BigMap(SmallMap, required=("key3", "key4")):
        pass

    b = BigMap(key1=123, key2=456, key3=789, key4=0)

    s = SmallMap._from(b)             # will copy just key1 and key2
    s = SmallMap._from(b, extra=555)  # can pass extra **kwargs to __init__
    s = SmallMap(**b)                 # will copy all keys

Note that this is a fairly basic implementation without __hash__, etc.
"""

import abc
import collections


class _NamedMappingMeta(abc.ABCMeta):
    def __new__(
        metacls, name, bases, namespace, *, required=None, default=None, **kwargs,  # noqa: N804
    ):
        new_required = []
        for base in bases:
            new_required.extend(getattr(base, "_required", ()))
        if required:
            new_required.extend(required)
        namespace["_required"] = tuple(set(new_required))

        new_default = {}
        for base in bases:
            new_default.update(getattr(base, "_default", {}))
        if default:
            new_default.update(default)
        namespace["_default"] = new_default

        return super().__new__(metacls, name, bases, namespace, **kwargs)


class NamedMapping(collections.abc.Mapping, metaclass=_NamedMappingMeta):
    __slots__ = ("_data",)

    def __init__(self, **keys):
        data = {}
        if hasattr(self, "_default"):
            data.update(self._default)
        data.update(keys)
        if hasattr(self, "_required"):
            for key in self._required:
                if key not in data:
                    raise KeyError(f"'{self.__class__.__name__}' requires key '{key}'")
        object.__setattr__(self, "_data", data)

    @classmethod
    def _from(cls, foreign, **keys):
        """
        (keys is like for __init__)
        """
        foreign_data = {}
        if hasattr(cls, "_required"):
            for key in cls._required:
                if key in foreign:
                    foreign_data[key] = foreign[key]
        foreign_data.update(keys)
        return cls(**foreign_data)

    def __getattr__(self, item):
        if item in ("_data", "_required", "_default"):
            return super().__getattr__(item)
        try:
            return self._data[item]
        except KeyError:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{item}'",
                name=item,
            ) from None

    def __setattr__(self, name, value):
        raise AttributeError(
            f"'{self}' is read-only, cannot set '{name}'",
            name=name,
            obj=value,
        )

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        raise ValueError(f"'{self}' is read-only, cannot set '{key}'")

    def __delitem__(self, key):
        raise ValueError(f"'{self}' is read-only, cannot delete '{key}'")

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            + ", ".join((f"{k}={repr(v)}" for k,v in self._data.items()))
            + ")"
        )
