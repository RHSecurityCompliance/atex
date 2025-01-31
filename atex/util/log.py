import inspect
import logging
from pathlib import Path

_logger = logging.getLogger('atex')


def _format_msg(msg, *, skip_frames=0):
    stack = inspect.stack()
    if len(stack)-1 <= skip_frames:
        raise SyntaxError("skip_frames exceeds call stack (frame count)")
    stack = stack[skip_frames+1:]

    # bottom of the stack, or runpy executed module
    for frame_info in stack:
        if frame_info.function == '<module>':
            break
    module = frame_info

    # last (topmost) function that isn't us
    parent = stack[0]
    function = parent.function

    # if the function has 'self' and it looks like a class instance,
    # prepend it to the function name
    p_locals = parent.frame.f_locals
    if 'self' in p_locals:
        self = p_locals['self']
        if hasattr(self, '__class__') and inspect.isclass(self.__class__):
            function = f'{self.__class__.__name__}.{function}'

    # don't report module name of a function if it's the same as running module
    if parent.filename != module.filename:
        parent_modname = parent.frame.f_globals['__name__']
        # avoid everything having the package name prefixed
        parent_modname = parent_modname.partition('.')[2] or parent_modname
        return f'{parent_modname}.{function}:{parent.lineno}: {msg}'
    elif parent.function != '<module>':
        return f'{function}:{parent.lineno}: {msg}'
    else:
        return f'{Path(parent.filename).name}:{parent.lineno}: {msg}'


def debug(msg, *, skip_frames=0):
    _logger.debug(_format_msg(msg, skip_frames=skip_frames+1))


def info(msg, *, skip_frames=0):
    _logger.info(_format_msg(msg, skip_frames=skip_frames+1))


def warning(msg, *, skip_frames=0):
    _logger.warning(_format_msg(msg, skip_frames=skip_frames+1))
