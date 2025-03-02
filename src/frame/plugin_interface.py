from asyncio import Future
from typing import Any, List, Protocol, TypeAlias, Callable

from frame.plugin_loading import load_tagged

Key: TypeAlias = str


class SubscriptionInterface(Protocol):
    def unsubscribe(self) -> None:
        """Unsubscribe from a property change."""


def plugin_getter(func: Callable) -> Callable:
    """Decorator to mark a property as a plugin property."""
    setattr(func, "plugin_getter", True)
    return func


def plugin_setter(func: Callable) -> Callable:
    """Decorator to mark a property as a plugin property."""
    setattr(func, "plugin_setter", True)
    return func


class PluginInterface(Protocol):
    @classmethod
    def name(cls) -> str:
        """Return the plugin name."""
        ...

    def setup(self) -> None:
        """Initialize the plugin."""
        ...

    def setdown(self) -> None:
        """Clean up the plugin."""
        ...

    def list_properties(self) -> List[str]:
        """List all properties."""
        ...

    def get_property(self, key: Key) -> Any:
        """Retrieve a property value."""
        ...

    def set_property(self, key: Key, value: Any) -> None:
        """Set a property value."""
        ...

    def subscribe_property(
        self, key: Key, callback: Callable[[Any], None]
    ) -> SubscriptionInterface:
        """Notify about a property change."""
        ...

    def subscribe_stream(
        self, key: Key, callback: Callable[[Any], None]
    ) -> SubscriptionInterface:
        """Stream log or debugging data."""
        ...

    def call(self, method: Key, params: dict) -> Future[Any]:
        """Handle an RPC-like query."""
        ...


class PluginBase(PluginInterface):
    def __init_subclass__(cls, name: str):
        cls.name = name

    @classmethod
    def name(cls) -> str:
        return cls.name

    def __init__(self, settings):
        super().__init__()

        self.getters = load_tagged(self, "plugin_getter")
        self.setters = load_tagged(self, "plugin_setter")
        self.notifiers = load_tagged(self, "plugin_notifiers")
        self.stream_notifiers = load_tagged(self, "plugin_stream_notifiers")
        self.calls = load_tagged(self, "plugin_calls")

        print(self.getters)

    def list_properties(self) -> List[str]:
        return self.getters.keys()

    def get_property(self, key: Key) -> Future[Any]:
        return self.getters[key]()

    def set_property(self, key: Key, value: Any) -> None:
        return self.setters[key](value)

    def subscribe_property(
        self, key: Key, callback: Callable[[Any], None]
    ) -> SubscriptionInterface:
        return self.notifiers[key](callback)

    def subscribe_stream(
        self, key: Key, callback: Callable[[Any], None]
    ) -> SubscriptionInterface:
        return self.stream_notifiers[key](callback)

    def call(self, method: Key, params: dict) -> Future[Any]:
        return self.calls[method](params)
