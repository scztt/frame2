import asyncio
from asyncio import Protocol
from collections import namedtuple
from functools import singledispatch
from operator import ge
from plistlib import UID
import tempfile
from typing import Any, Callable, Dict, List

from frame.images import image_repo
from frame.parsers import make_parser
from frame.renderers import RendererBase, make_renderer
from frame.shell import run_command

ValueType = namedtuple("ValueType", ["Get", "Set"])


getters: Dict[str, Any] = {}
setters: Dict[str, Any] = {}


class ValueBase:
    def __init_subclass__(cls, name: str, type: ValueType):
        super().__init_subclass__()

        cls.name = name
        cls.type = type

        if type == "Get":
            getters[name] = cls
        elif type == "Set":
            setters[name] = cls

    def __init__(self, settings: Dict[str, Any]):
        super().__init__()
        self.renderer = make_renderer(settings.get("renderer", "string"))
        self.settings = settings


class GetValue(ValueBase, name="get", type="Get"):
    renderer: RendererBase

    def __init_subclass__(cls, name: str):
        super().__init_subclass__(name=name, type="Get")
        cls.name = name
        cls.type = type

    def get(self) -> Any: ...


class SetValue(ValueBase, name="set", type="Set"):
    def __init_subclass__(cls, name: str):
        super().__init_subclass__(name=name, type="Set")
        cls.name = name
        cls.type = type

    def set(self, value: Any): ...


class ValueDelegate:
    def __init__(
        self,
        display_name: str,
        getter: GetValue | None,
        setter: SetValue | None,
    ):
        super().__init__()
        self.display_name = display_name
        self.getter = getter
        self.setter = setter

        if getter is not None:
            self.renderer = getter.renderer

    async def get(self) -> Any:
        if self.getter is None:
            raise NotImplementedError("Getter not implemented")

        return await self.getter.get()

    async def set(self) -> Any:
        if self.getter is None:
            raise NotImplementedError("Getter not implemented")

        return await self.getter.get()


def make_value(
    name: str,
    display_name: str,
    get_settings: Dict[str, Any] | None,
    set_settings: Dict[str, Any] | None,
):
    get = None
    set = None

    if get_settings:
        get = getters[get_settings["type"]](get_settings)

    if set_settings:
        set = setters[set_settings["type"]](set_settings)

    return ValueDelegate(display_name, get, set)


############################################################
# Implementations
############################################################
class ShellGetter(GetValue, name="shell"):
    def __init__(self, settings):
        self.command = settings["cmd"]
        self.parser = make_parser(settings.get("parser", "string"))
        self.renderer = make_renderer(settings.get("renderer", "string"))

    async def get(self):
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class ShellSetter(SetValue, name="shell"):
    def __init__(self, settings):
        self.command = settings["cmd"]
        self.parser = make_parser(settings.get("parser", "string"))

    async def set(self):
        result_str = await run_command(self.command)
        result = self.parser(result_str)
        return result


class ScreenshotGetter(GetValue, name="screenshot"):

    def __init__(self, settings):
        settings["renderer"] = settings.get("renderer", "image")
        super().__init__(settings)
        self.id = "screenshot"

    async def get(self):
        ref = image_repo.get_image_ref(self.id + ".png")
        await run_command(["screencapture", ref.path])
        return ref
