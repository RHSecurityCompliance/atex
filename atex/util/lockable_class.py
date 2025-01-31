import threading


class LockableClass:
    """
    A class with (nearly) all attribute accesses protected by threading.RLock,
    making them thread-safe at the cost of some speed.

        class MyClass(LockableClass):
            def writer(self):
                self.attr = 222     # thread-safe instance access
            def reader(self):
                print(self.attr)    # thread-safe instance access
            def complex(self):
                with self.lock:     # thread-safe context
                    self.attr += 1

    Here, 'lock' is a reserved attribute name and must not be overriden
    by a derived class.

    If overriding '__init__', make sure to call 'super().__init__()' *before*
    any attribute accesses in your '__init__'.
    """
    def __init__(self):
        object.__setattr__(self, 'lock', threading.RLock())

    def __getattribute__(self, name):
        # optimize built-ins
        if name.startswith('__') or name == 'lock':
            return object.__getattribute__(self, name)
        lock = object.__getattribute__(self, 'lock')
        with lock:
            return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        lock = object.__getattribute__(self, 'lock')
        with lock:
            object.__setattr__(self, name, value)
