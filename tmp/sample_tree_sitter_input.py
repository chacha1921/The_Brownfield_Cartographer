import os
import sys as system
from pathlib import Path
from pkg import thing


def public_fn():
    return 1


def _private_fn():
    return 2


class Example:
    def method(self):
        return 3
