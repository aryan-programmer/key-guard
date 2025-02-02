from contextlib import contextmanager
from functools import wraps
from time import perf_counter
from logger_instance import logger
import logging


def timing_decorator(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = perf_counter()
        result = f(*args, **kw)
        te = perf_counter()
        logger.log(
            logging.INFO, f'func:{f.__name__!r} args:[{args!r}, {kw!r}] took: {te - ts:2.4f} sec')
        return result

    return wrap


@contextmanager
def time_catcher() -> float:
    t1 = t2 = perf_counter()
    yield lambda: t2 - t1
    t2 = perf_counter()


@contextmanager
def timing_wither(name) -> float:
    t1 = t2 = perf_counter()
    yield
    t2 = perf_counter()
    logger.log(logging.INFO, f'func:{name} took: {t2 - t1:2.4f} sec')
