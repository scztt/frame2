from typing import Any, Dict, List
from frame.actions import ActionBase, make_action
from frame.values import ValueDelegate, make_value


class Config:
    model: Dict[str, ValueDelegate]
    model_order: List[str]
    actions: Dict[str, ActionBase]
    project_name: str

    def __init__(self, config: dict):
        self.path = config.get("path")
        self.settings = self.parse_settings(config.get("settings"))
        (self.model, self.model_order) = self.parse_model(config.get("model"))
        self.actions = self.parse_actions(config.get("actions"))
        self.project_name = config.get("name")

    def parse_settings(self, settings: dict) -> Dict[str, Any]:
        return settings

    def parse_model(self, model_config: dict) -> Dict[str, Any]:
        model_order = []
        model: Dict[str, ValueDelegate] = {}

        for name, value_desc in model_config.items():
            value = make_value(
                name=name,
                display_name=value_desc.get("name", name),
                get_settings=value_desc.get("get"),
                set_settings=value_desc.get("set"),
            )
            model_order.append(name)
            model[name] = value

        return (model, model_order)

    def parse_actions(self, action_config: dict) -> Dict[str, Any]:
        actions = {}

        for name, action_desc in action_config.items():
            actions[name] = make_action(action_desc)

        return actions

    def get_properties(self) -> List[str]:
        return self.model_order

    def get_property(self, name: str) -> ValueDelegate:
        return self.model[name]

    async def get(self, property_name: str) -> Any:
        return await self.model[property_name].get()

    async def set(self, property_name: str, value: Any) -> None:
        self.model[property_name].set(value)

    async def do(self, action_name: str, params: dict) -> Any:
        return await self.actions[action_name].call(params)

    async def get_rendered(self, property_name: str) -> str:
        result = await self.get(property_name)
        renderer = self.model[property_name].renderer
        return renderer.render_data(result)

    async def render_output(self, property_name: str, path: str) -> str:
        renderer = self.model[property_name].renderer
        return renderer.render_list_item(property_name, property_name)
