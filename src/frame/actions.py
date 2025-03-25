from typing import Callable, Dict, Any
from frame.notification_targets import make_notification_target
from frame.registry import TypeRegistry
from frame.renderers import RendererBase, make_renderer
from frame.shell import run_command
from frame.parsers import make_parser
from pythonosc import udp_client
import jinja2
import asyncio


class ActionBase:
    renderer: RendererBase | None
    display_name: str

    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.name = name
        actions.register(name, cls)

    def __init__(self, settings: Dict[str, Any]) -> None:
        self.renderer = None
        self.name = settings["name"]
        self.url = f"/action/{self.name}"
        self.display_name = settings.get("name", self.name)
        pass

    async def call(self, params: Dict[str, Any], get_action) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


actions = TypeRegistry[ActionBase]("action", {"renderer": "action"})


def make_action(config: "Config", name: str, settings: str | Dict[str, Any]) -> ActionBase:
    settings["name"] = name
    return actions.make(
        settings,
        config=config,
    )[0]


############################################################
# Implementations
############################################################
class ShellAction(ActionBase, name="shell"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.command = settings["cmd"]
        self.parser = make_parser(settings.get("parser", "string"))
        if settings.get("renderer"):
            self.renderer, _ = make_renderer(settings["renderer"])

    async def call(self, params: Dict[str, Any], get_action) -> Any:
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class NestedAccessor:
    def __init__(self, dict: Dict[str, Any]):
        self.dict = dict

    def keys(self):
        # Extract unique top-level keys from the dictionary
        result = set()
        for key in self.dict.keys():
            # Get the top-level part (everything before the first dot, or the whole key if no dot)
            top_level = key.split(".", 1)[0]
            result.add(top_level)

        return result

    def __getattr__(self, name):
        # Check if the name exists as a direct key
        if name in self.dict:
            return self.dict[name]

        # Look for dot-separated keys that start with this name
        prefix = f"{name}."
        nested_dict = {}
        for key, value in self.dict.items():
            if key == name:
                return value
            if key.startswith(prefix):
                suffix = key[len(prefix) :]
                nested_dict[suffix] = value

        # If we found nested keys, return a new accessor for them
        if nested_dict:
            return NestedAccessor(nested_dict)

        # Otherwise raise an attribute error
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __getitem__(self, key):
        # Support dictionary-style access with []
        try:
            return self.__getattr__(key)
        except AttributeError:
            raise KeyError(key)


class Condition:
    def __init__(self, condition: str):
        self.template = jinja2.Template("{{ " + condition + " }}")
        self.last_value = None

    def __call__(self, context: Dict[str, Any], then: Callable[[Any], None]):
        # accessor = NestedAccessor(context)
        result = self.template.render(**context)

        if result.lower() in ("true", "yes", "1"):
            result = True
        elif result.lower() in ("false", "no", "0"):
            result = False
        else:
            pass

        if self.last_value is None:
            self.last_value = result
            return

        if self.last_value != result:
            self.last_value = result

            if result:
                then(context, result)


class NotificationAction(ActionBase, name="notification"):
    def __init__(self, settings: Dict[str, Any], config: "Config"):
        super().__init__(settings)
        self.targets = [make_notification_target(target) for target in settings.get("targets", [])]
        self.message = settings.get("message")
        self.message_template = jinja2.Template(self.message)
        self.condition = Condition(settings.get("condition", "false"))
        self.subscription = config.subscribe(lambda m: m, lambda m: self.condition(m, self.notify))

    def notify(self, context: Dict[str, Any], result: Any):
        message_rendered = self.message_template.render(**context)
        for target in self.targets:
            asyncio.create_task(target.notify({"message": message_rendered}))

    async def call(self, params: Dict[str, Any], get_action) -> Any:
        print(self.message)
        return None


class SequenceAction(ActionBase, name="sequence"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.actions = settings["actions"]
        if settings.get("renderer"):
            self.renderer, _ = make_renderer(settings["renderer"])

    async def call(self, params: Dict[str, Any], get_action) -> Any:
        for action in self.actions:
            await get_action(action).call(params, get_action)
        return None


class OSCAction(ActionBase, name="osc"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.path = settings["path"]
        self.args = settings.get("args", [])
        self.client = udp_client.SimpleUDPClient(settings["address"], int(settings["port"]))

        if settings.get("renderer"):
            self.renderer, _ = make_renderer(settings.get("renderer", "slider"))

    async def call(self, params: Dict[str, Any], get_action) -> Any:
        msg = [item for pair in params.items() for item in pair]
        self.client.send_message(self.path, msg)
