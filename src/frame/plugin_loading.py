import inspect
from typing import Any, Callable, Dict


def load_tagged(self, tag: str) -> Dict[str, Callable[[], Any]]:
    tagged = {}
    for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
        if getattr(method, tag, False):
            tagged[name] = method
    return tagged
