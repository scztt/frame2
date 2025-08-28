import json
import re
from typing import Any, Dict, Tuple

from frame.registry import TypeRegistry


class ParserBase:
    def __init_subclass__(cls, name: str):
        super().__init_subclass__()
        cls.name = name
        registry.register(name, cls)

    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings

    def __call__(self, value: str) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


registry = TypeRegistry[ParserBase]("parser")


class JsonParser(ParserBase, name="json"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

    def __call__(self, value: str):
        return json.loads(value)


class RegexParser(ParserBase, name="regex"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

        self.pattern = settings.get("pattern", (".*"))
        self.is_list = settings.get("list", False)

        group_setting = settings.get("group", 0)
        if isinstance(group_setting, int):
            self.group = group_setting
            self.group_struct = None
        elif isinstance(group_setting, dict):
            self.group_struct = settings.get("group", False)
            self.group = None
        else:
            raise ValueError("Invalid group setting")

    def parse_item(self, match: re.Match[str]) -> str | Dict[str, str]:
        if self.group_struct is not None:
            return {k: match.group(v) for k, v in self.group_struct.items()}
        else:
            return match.group(self.group)

    def __call__(self, value: str) -> str | Dict[str, str] | list[str | Dict[str, str]]:
        if self.group_struct is not None:
            match = re.finditer(self.pattern, value)
            if not match:
                raise ValueError(f"Pattern {self.pattern} not found in {value}")
            else:
                return [self.parse_item(m) for m in match]
        else:
            match = re.search(self.pattern, value)
            if not match:
                raise ValueError(f"Pattern {self.pattern} not found in {value}")
            else:
                return match.group(self.group)


class StringParser(ParserBase, name="string"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.settings = settings

    def __call__(self, value: str) -> str:
        return value


class DetectParser(RegexParser, name="detect"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.invert = settings.get("invert", False)

    def __call__(self, value: str) -> bool:  # type: ignore
        match = re.search(self.pattern, value)
        if not match:
            return False if not (self.invert) else True
        else:
            return True if not (self.invert) else False


class SequenceParser(ParserBase, name="sequence"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.parsers = [make_parser(parser)[0] for parser in settings["parsers"]]

    def __call__(self, value: str) -> Any:
        for parser in self.parsers:
            value = parser(value)
        return value


def register_parsers(settings: Dict[str, Any]) -> None:
    for name, ref_settings in settings.items():
        registry.register_ref(name, ref_settings)


def make_parser(settings: str | Dict[str, Any]) -> Tuple[ParserBase, Dict[str, Any]]:
    return registry.make(settings)
