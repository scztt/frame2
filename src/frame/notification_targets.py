from typing import Any, Dict

from pythonosc import udp_client
from frame.registry import TypeRegistry
from frame.renderers import render_nested_dict
from starlette.exceptions import HTTPException
import httpx


class NotificationTargetBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        notification_targets.register(name, cls)

    def __init__(self, settings: Dict[str, Any]): ...

    async def notify(self, data: Dict[str, Any]) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


notification_targets = TypeRegistry[NotificationTargetBase]("target")


def make_notification_target(settings: Dict[str, Any] | str) -> NotificationTargetBase:
    return notification_targets.make(settings)[0]


############################################################
# Implementations
############################################################
class StringRenderer(NotificationTargetBase, name="string"):
    def render_data(self, data: Any) -> str:
        return f"<div class='value'>{data}</div>"


class JSONRenderer(NotificationTargetBase, name="json"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.folding = settings.get("folding", True)

    def render_data(self, data: Dict[str, Any]) -> str:
        return render_nested_dict(data)


class IFTTT(NotificationTargetBase, name="ifttt"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

        if settings.get("url") is not None:
            self.url = settings["url"]
        else:
            self.url = f"https://maker.ifttt.com/trigger/{settings["event_name"]}/json/with/key/{settings["key"]}"

    async def notify(self, data: Dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, headers={"Content-Type": "application/json"}, json={"value1": data.get("subject"), "value2": data.get("message")})
            response.raise_for_status()
            return response
        except HTTPException as e:
            # Log the error or handle it as needed
            print(e)
            return {"error": str(e)}


class OSCTarget(NotificationTargetBase, name="osc"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.path = settings["path"]
        self.args = settings.get("args", [])
        self.client = udp_client.SimpleUDPClient(settings["address"], int(settings["port"]))

    async def notify(self, data: Dict[str, Any]) -> Any:
        value = data.get("message")
        if value is None:
            return
        try:
            value = int(value)
        except (ValueError, TypeError):
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass
        self.client.send_message(self.path, value)
