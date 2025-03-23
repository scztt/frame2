from enum import Enum
from typing import Any, Dict

from frame.images import image_repo
from frame.parsers import make_parser
from frame.registry import TypeRegistry
from frame.renderers import RendererBase, make_renderer
from frame.shell import run_command
from frame.utility import tail_lines
import os

ValueType = Enum("ValueType", [("Get", 1), ("Set", 2)])


class ValueBase:
    def __init_subclass__(cls, name: str):
        super().__init_subclass__()

        cls.name = name
        values.register(name, cls)

    def __init__(self, settings: Dict[str, Any]):
        pass


values = TypeRegistry[ValueBase]("get")


class GetValue(ValueBase, name="get"):
    renderer: RendererBase

    def get(self) -> Any: ...


class ValueDelegate:
    display_name: str
    update_time: float | None
    renderer: RendererBase

    def __init__(
        self,
        name: str,
        desc: Dict[str, Any],
    ):
        super().__init__()
        self.display_name = desc.get("name", name)
        self.update_time = float(desc.get("poll")) if desc.get("poll") else None

        self.getter, get_settings = values.make(desc.get("get"))

        self.updates = get_settings.get("poll", None)
        self.renderer, _ = make_renderer(desc.get("renderer", "string"))

    async def get(self) -> Any:
        if self.getter is None:
            raise NotImplementedError("Getter not implemented")

        return await self.getter.get()


def make_value(name: str, value_desc: Dict[str, Any]):
    return ValueDelegate(name, value_desc)


############################################################
# Implementations
############################################################
class ShellGetter(ValueBase, name="shell"):
    def __init__(self, settings):
        settings["renderer"] = settings.get("renderer", "string")
        super().__init__(settings)
        self.command = settings["cmd"]
        self.parser, _ = make_parser(settings.get("parser", "string"))

    async def get(self):
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class ScreenshotGetter(ValueBase, name="screenshot"):
    def __init__(self, settings):
        settings["renderer"] = settings.get("renderer", "image")
        super().__init__(settings)
        self.id = "screenshot"

    async def get(self):
        ref = image_repo.make_image_ref(self.id + ".png")
        await run_command(["screencapture", ref.path])
        return ref


class Tail(ValueBase, name="tail"):
    def __init__(self, settings):
        settings["renderer"] = settings.get("renderer", "log")
        super().__init__(settings)

        self.path = settings["path"]
        self.lines = settings.get("lines", 100)
        self.mod_time = 0
        self.last_value = ""

    async def get(self):
        mod_time = os.path.getmtime(self.path)

        if mod_time > self.mod_time:
            self.mod_time = mod_time
            self.last_value = tail_lines(self.path, self.lines)

        return self.last_value
