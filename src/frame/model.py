import asyncio
from contextlib import ExitStack
from copy import deepcopy
import json
from queue import Queue
from re import sub
from sys import settrace
from typing import Any, Callable, Dict, List, Tuple
from frame.actions import ActionBase, make_action
from frame.parsers import register_parsers
from frame.registry import set_defaults
from frame.values import ValueDelegate, make_value


State = Dict[str, Any]

Selector = Callable[[State], Any]
Callback = Callable[[Any], None]


class Trigger:
    class Subscription:
        trigger: "Trigger"
        callback: Callback

        def __init__(self, trigger: "Trigger", callback: Callback):
            self.trigger = trigger
            self.callback = callback

        def __enter__(self):
            return self

        def __exit__(self, *args):
            if self.callback in self.trigger.subscribers:
                self.trigger.subscribers.remove(self.callback)

        def unsubscribe(self):
            if self.callback in self.trigger.subscribers:
                self.trigger.subscribers.remove(self.callback)

    selector: Selector
    subscribers: List[Callback]

    def __init__(self, selector: Selector):
        self.selector = selector
        self.subscribers: List[Callback] = []

    def subscribe(self, callback: Callback) -> Subscription:
        self.subscribers.append(callback)
        return self.Subscription(self, callback)

    def update(self, old_model: State, new_model: State):
        new_value = self.selector(new_model)
        old_value = self.selector(old_model)
        if new_value != old_value:
            for subscriber in self.subscribers:
                subscriber(new_value)


class Config:
    project_name: str

    state: State
    state_order: List[str]
    delegates: Dict[str, ValueDelegate]
    actions: Dict[str, ActionBase]
    triggers: List[Trigger] = []
    update_tasks: Dict[str, asyncio.Task[Any]] = {}

    class Mutable:
        config: "Config"
        model: Dict[str, ValueDelegate]

        def __init__(self, config: "Config"):
            self.config = config
            self.model = deepcopy(config.state)

        def __enter__(self):
            return self.model

        def __exit__(self, exc_type, exc_value, traceback):  # type: ignore
            self.config.update(self.model)

    def __init__(self, config: Dict[str, Any]):
        self.path = config.get("path")
        self.settings = self.parse_settings(config.get("settings", {}))
        self.parse_types(config.get("types", {}))
        self.parse_defaults(config.get("defaults", {}))
        (self.delegates, self.state_order) = self.parse_model(config.get("model", {}))
        self.state = {name: None for name, delegate in self.delegates.items()}
        self.actions = self.parse_actions(config.get("actions", {}))
        self.project_name = config.get("name", "Untitled Project")

        # ...update all values...
        self.ready = self.pull(*self.state_order)

    def done(self):
        return asyncio.ensure_future(self.ready)

    ##########################################################################
    # PARSING
    ##########################################################################
    def parse_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        return settings

    def parse_defaults(self, defaults: Dict[str, Any]):
        set_defaults(defaults)
        pass

    def parse_types(self, types: Dict[str, Any]):
        register_parsers(types.get("parsers", {}))

    def parse_model(
        self, model_config: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str]]:
        model_order: List[str] = []
        delegates: Dict[str, ValueDelegate] = {}

        for name, value_desc in model_config.items():
            value = make_value(name, value_desc)
            model_order.append(name)
            delegates[name] = value

        return (delegates, model_order)

    def parse_actions(self, action_config: Dict[str, Any]):
        actions: Dict[str, ActionBase] = {}

        for name, action_desc in action_config.items():
            actions[name] = make_action(action_desc)

        return actions

    ##########################################################################
    # STATE
    ##########################################################################
    def update(self, new_model: Dict[str, ValueDelegate]):
        old_model = self.state
        self.state = new_model
        for trigger in self.triggers:
            trigger.update(old_model, new_model)

    def mutable(self):
        return self.Mutable(self)

    async def pull_task(self, key: str):
        value = await self.delegates[key].get()
        with self.mutable() as m:
            m[key] = value

    async def pull(self, *keys: str):
        await asyncio.gather(*[self.pull_task(key) for key in keys])

    ##########################################################################
    # ACCESS
    ##########################################################################
    def subscribe(
        self, selector: Selector | str, callback: Callback
    ) -> Trigger.Subscription:
        if isinstance(selector, str):
            asyncio.create_task(self.pull(selector))
            return self.subscribe(lambda m: m[selector], callback)

        trigger = Trigger(selector)
        self.triggers.append(trigger)
        return trigger.subscribe(callback)

    async def do_auto_update(self, property_name: str, seconds: float):
        await self.pull(property_name)
        while True:
            await asyncio.sleep(seconds)
            await self.pull(property_name)

    def auto_update(self, property_name: str, seconds: float):
        if self.update_tasks.get(property_name):
            self.update_tasks[property_name].cancel()

        self.update_tasks[property_name] = asyncio.ensure_future(
            self.do_auto_update(property_name, seconds)
        )

    def get_properties(self) -> List[str]:
        return self.state_order

    def get_property(self, name: str) -> ValueDelegate:
        return self.delegates[name]

    def get_property_path(self, property_name: str) -> str:
        url_path = property_name.replace(".", "/")
        return f"/model/{url_path}"

    def get(self, property_name: str) -> Any:
        return self.state[property_name]

    def get_rendered(self, property_name: str) -> str:
        result = self.get(property_name)
        renderer = self.delegates[property_name].renderer
        return renderer.render_data(result)

    def subscribe_rendered_updates(
        self, property_name: str, queue: asyncio.Queue[Any]
    ) -> Trigger.Subscription:
        renderer = self.delegates[property_name].renderer

        def callback(value: Any):
            """Push a new value into the queue."""
            asyncio.create_task(queue.put((property_name, renderer.render_data(value))))

        return self.subscribe(property_name, callback)

    async def get_rendered_update_stream(self):
        await self.pull(*self.get_properties())

        for property_name in self.get_properties():
            renderer = self.delegates[property_name].renderer
            data = {
                "id": self.get_property_path(property_name).replace("/", "-"),
                "rendered": renderer.render_data(self.state[property_name]),
            }
            yield f"data: {json.dumps(data)}\n\n"  # Must follow SSE format

        queue = asyncio.Queue[Any]()
        with ExitStack() as stack:
            subscriptions = [
                stack.enter_context(self.subscribe_rendered_updates(name, queue))
                for name in self.get_properties()
            ]

            while True:
                property_name, rendered = await queue.get()
                data = {
                    "id": self.get_property_path(property_name).replace("/", "-"),
                    "rendered": rendered,
                }
                yield f"data: {json.dumps(data)}\n\n"  # Must follow SSE format

    async def do(self, action_name: str, params: Dict[str, Any]) -> Any:
        return await self.actions[action_name].call(params)

    async def render_output(self, property_name: str, path: str) -> str:
        renderer = self.state[property_name].renderer
        name = self.state[property_name].display_name
        return renderer.render_list_item(name, property_name)
