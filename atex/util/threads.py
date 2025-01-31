import queue
import threading

from .named_mapping import NamedMapping

# TODO: documentation; this is like concurrent.futures, but with daemon=True support

# TODO: also document that via .get_raw() you can pass arbitrary **kwargs to
#       .start_thread() and they become reachable in the ThreadReturn


class ThreadQueue:
    class ThreadReturn(NamedMapping, required=("thread", "returned", "exception")):
        pass

    Empty = queue.Empty

    def __init__(self, daemon=False):
        self.queue = queue.SimpleQueue()
        self.daemon = daemon
        self.threads = set()

    def _wrapper(self, func, func_args, func_kwargs, **kwargs):
        current_thread = threading.current_thread()
        try:
            ret = func(*func_args, **func_kwargs)
            result = self.ThreadReturn(
                thread=current_thread,
                returned=ret,
                exception=None,
                **kwargs,
            )
        except Exception as e:
            result = self.ThreadReturn(
                thread=current_thread,
                returned=None,
                exception=e,
                **kwargs,
            )
        self.queue.put(result)

    def start_thread(self, target, target_args=None, target_kwargs=None, **kwargs):
        t = threading.Thread(
            target=self._wrapper,
            args=(target, target_args or (), target_kwargs or {}),
            kwargs=kwargs,
            daemon=self.daemon,
        )
        t.start()
        self.threads.add(t)

    def get_raw(self, block=True, timeout=None):
        if block and timeout is None and not self.threads:
            raise AssertionError("no threads are running, would block forever")
        treturn = self.queue.get(block=block, timeout=timeout)
        self.threads.remove(treturn.thread)
        return treturn

    # get one return value from any thread's function, like .as_completed()
    # or concurrent.futures.FIRST_COMPLETED
    def get(self, block=True, timeout=None):
        treturn = self.get_raw(block, timeout)
        if treturn.exception is not None:
            raise treturn.exception
        else:
            return treturn.returned

    # wait for all threads to finish (ignoring queue contents)
    def join(self):
        while self.threads:
            t = self.threads.pop()
            t.join()
