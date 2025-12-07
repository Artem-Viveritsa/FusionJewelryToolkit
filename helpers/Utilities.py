import time
from .showMessage import showMessage


def timeit(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        showMessage(f"{func.__name__}: {elapsed:.4f}s")
        return result
    return wrapper