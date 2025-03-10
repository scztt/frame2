import json
from os import name
import re
from typing import Any, Dict


class ParserBase:
    def __init_subclass__(cls, name: str):
        super().__init_subclass__()
        cls.name = name
        parsers[name] = cls

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings

    def __call__(self, value: str) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


parsers: Dict[str, type] = {}


class JsonParser(ParserBase, name="json"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

    def __call__(self, value: str):
        return json.loads(value)


class RegexParser(ParserBase, name="regex"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.pattern = settings.get("pattern", (".*"))
        self.group = settings.get("group", 0)

    def __call__(self, value: str) -> str:
        match = re.search(self.pattern, value)
        if not match:
            return None
        else:
            return match.group(self.group)


class StringParser(ParserBase, name="string"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.settings = settings

    def __call__(self, value: str):
        return value


class DetectParser(RegexParser, name="detect"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.invert = settings.get("invert", False)

    def __call__(self, value: str) -> str:
        match = re.search(self.pattern, value)
        if not match:
            return False if not (self.invert) else True
        else:
            return True if not (self.invert) else False


class SequenceParser(ParserBase, name="sequence"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.parsers = [make_parser(parser) for parser in settings["parsers"]]

    def __call__(self, value: str) -> Any:
        for parser in self.parsers:
            value = parser(value)
        return value


def make_parser(settings: str | Dict[str, Any]) -> ParserBase:
    if isinstance(settings, str):
        settings = {"type": settings}

    type = settings.get("type")
    return parsers.get(type)(settings)
