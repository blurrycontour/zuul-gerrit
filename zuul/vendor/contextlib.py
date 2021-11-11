# Copied from https://github.com/python/cpython/blob/main/Lib/contextlib.py
# Licensed under the Python Software Foundation License Version 2
#
# This is included in Python versions 3.7+
# TODO: Remove after Zuul drops support for 3.6

from contextlib import AbstractContextManager


class nullcontext(AbstractContextManager):
    """Context manager that does no additional processing.
    Used as a stand-in for a normal context manager, when a particular
    block of code is only sometimes used with a normal context manager:
    cm = optional_cm if condition else nullcontext()
    with cm:
        # Perform operation, using optional_cm if condition is True
    """

    def __init__(self, enter_result=None):
        self.enter_result = enter_result

    def __enter__(self):
        return self.enter_result

    def __exit__(self, *excinfo):
        pass
