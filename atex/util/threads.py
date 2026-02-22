import queue
import threading

from .named_mapping import NamedMapping


class ThreadReturn(threading.Thread):
    """
    Simple wrapper around threading.Thread that propagates the target function
    return value or raised exception to the parent via .join().
    """
    def __init__(self, *args, **kwargs):
        self.__result = None
        self.__exception = None
        super().__init__(*args, **kwargs)

    def run(self):
        try:
            if self._target is not None:
                self.__result = self._target(*self._args, **self._kwargs)
        except Exception as e:
            self.__exception = e
        # taken from the original threading.Thread.run
        finally:
            # Avoid a refcycle if the thread is running a function with
            # an argument that has a member that points to the thread.
            del self._target, self._args, self._kwargs

    def join(self, timeout=None):
        super().join(timeout)
        if self.is_alive():
            raise TimeoutError("thread still alive after timeout expired")
        if self.__exception:
            raise self.__exception
        else:
            return self.__result


class ThreadReturnQueue:
    """
    Extension of ThreadReturn to support multiple threads and a central
    SimpleQueue that collects their return values (or exceptions).

    This is very similar to concurrent.futures.ThreadPoolExecutor and its
    .submit() and .as_completed() or FIRST_COMPLETED, but with support for
    additional metadata via a custom NamedMapping and (crucially) support
    for daemon=True threads.

    (Also, this starts one thread per function, not a thread pool of workers.)

    Example:
        def func(*args):
            return args

        queue = ThreadReturnQueue(daemon=True)
        queue.start_thread(target=func, target_args=(1,2,3))
        queue.start_thread(target=func, target_args=(4,5,6))
        queue.get()  # returns (1,2,3) or (4,5,6)
        queue.get()  # returns (1,2,3) or (4,5,6)

    """
    class ThreadResult(NamedMapping, required=("thread", "returned", "exception")):
        pass

    Empty = queue.Empty

    def __init__(self, daemon=False):
        self.lock = threading.RLock()
        self.queue = queue.SimpleQueue()
        self.daemon = daemon
        self.threads = set()

    def _wrapper(self, func, func_args, func_kwargs, **user_kwargs):
        current_thread = threading.current_thread()
        try:
            ret = func(*func_args, **func_kwargs)
            result = self.ThreadResult(
                thread=current_thread,
                returned=ret,
                exception=None,
                **user_kwargs,
            )
        except Exception as e:
            result = self.ThreadResult(
                thread=current_thread,
                returned=None,
                exception=e,
                **user_kwargs,
            )
        self.queue.put(result)

    def start_thread(self, target, target_args=None, target_kwargs=None, **user_kwargs):
        """
        Start a new thread and call `target` as a callable inside it, passing it
        `target_args` as arguments and `target_kwargs` as keyword arguments.

        Any additional `user_kwargs` specified are NOT passed to the callable,
        but instead become part of the ThreadResult namespace returned by the
        `.get_raw()` method.
        """
        t = threading.Thread(
            target=self._wrapper,
            args=(target, target_args or (), target_kwargs or {}),
            kwargs=user_kwargs,
            daemon=self.daemon,
        )
        with self.lock:
            self.threads.add(t)
        t.start()

    def get_raw(self, block=True, timeout=None):
        """
        Wait for and return the next available ThreadResult instance on the
        queue, as enqueued by a finished callable started by the
        `.start_thread()` method.
        """
        with self.lock:
            if block and timeout is None and not self.threads:
                raise AssertionError("no threads are running, would block forever")
        treturn = self.queue.get(block=block, timeout=timeout)
        with self.lock:
            self.threads.remove(treturn.thread)
        return treturn

    # get one return value from any thread's function, like .as_completed()
    # or concurrent.futures.FIRST_COMPLETED
    def get(self, block=True, timeout=None):
        """
        Wait for and return the next available return value of a callable
        enqueued via the `.start_thread()` method.

        If the callable raised an exception, the exception is re-raised here.
        """
        treturn = self.get_raw(block, timeout)
        if treturn.exception is not None:
            raise treturn.exception
        else:
            return treturn.returned

    # wait for all threads to finish (ignoring queue contents)
    def join(self):
        """
        Wait for all threads to finish, ignoring the state of the queue.
        """
        while True:
            with self.lock:
                try:
                    thread = self.threads.pop()
                except KeyError:
                    break
            thread.join()

    def qsize(self):
        """
        Return the amount of elements `.get()` can retrieve before it raises
        `queue.Empty`.
        """
        return self.queue.qsize()
