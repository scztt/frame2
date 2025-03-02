from typing import Callable, Dict, Any
from frame.shell import run_command
from frame.parsers import make_parser

actions = {}


class ActionBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        actions[name] = cls

    async def call(self, settings: Dict[str, Any]) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


def make_action(settings: str | Dict[str, Any]):
    if isinstance(settings, str):
        settings = {"type": settings}

    type = settings.get("type")
    return actions.get(type)(settings)


############################################################
# Implementations
############################################################
class ShellAction(ActionBase, name="shell"):
    def __init__(self, settings: Dict[str, Any]):
        self.command = settings["cmd"]
        self.parser = make_parser(settings.get("parser", "string"))

    async def call(self, settings: Dict[str, Any]) -> Any:
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class SequenceAction(ActionBase, name="sequence"):
    def __init__(self, settings: Dict[str, Any]):
        self.actions = settings["actions"]

    async def call(
        self, settings: Dict[str, Any], find_action: Callable[[str], ActionBase]
    ) -> Any:
        for action in self.actions:
            await find_action(action)(settings)
        return None
