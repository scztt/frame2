from typing import Any, Dict

notification_targets = {}


class NotificationTargetBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        notification_targets[name] = cls

    def __init__(self, settings: Dict[str, Any]): ...

    def notify(self, data: dict) -> Any:
        raise NotImplementedError("Subclasses must implement this method")


def make_notification_target(settings: dict | str) -> NotificationTargetBase:
    """Get an action by name."""
    if isinstance(settings, str):
        settings = {"type": settings}

    cls = notification_targets.get(settings["type"])

    if cls is None:
        raise ValueError(
            f"No notification target registered with name: {settings["type"]}"
        )

    return cls(settings)


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

    def render_data(self, data: dict) -> str:
        return render_nested_dict(data)
