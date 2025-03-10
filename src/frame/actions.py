from typing import Callable, Dict, Any
from frame.notification_targets import make_notification_target
from frame.shell import run_command
from frame.parsers import make_parser


class ActionBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        actions[name] = cls

    def __init__(self, settings: Dict[str, Any]) -> None:
        pass

    async def call(self, settings: Dict[str, Any]) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


actions: Dict[str, type] = {}


def make_action(settings: str | Dict[str, Any]) -> ActionBase:
    if isinstance(settings, str):
        settings = {"type": settings}

    type = settings.get("type")
    cls = actions.get(type)

    if cls is None:
        raise ValueError(f"No action registered with name: {type}")

    return cls(settings)


############################################################
# Implementations
############################################################
class ShellAction(ActionBase, name="shell"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.command = settings["cmd"]
        self.parser = make_parser(settings.get("parser", "string"))

    async def call(self, settings: Dict[str, Any]) -> Any:
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class NotificationAction(ActionBase, name="notification"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.targets = [
            make_notification_target(target) for target in settings.get("targets", [])
        ]
        self.message = settings.get("message")

    async def call(self, settings: Dict[str, Any]) -> Any:
        print(self.message)
        return None


class SequenceAction(ActionBase, name="sequence"):
    def __init__(
        self, settings: Dict[str, Any], get_action: Callable[[str], ActionBase]
    ):
        super().__init__(settings)
        self.actions = settings["actions"]
        self.get_action = get_action

    async def call(self, settings: Dict[str, Any]) -> Any:
        for action in self.actions:
            await self.get_action(action).call(settings)
        return None
