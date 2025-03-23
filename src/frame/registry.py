from copy import deepcopy
from typing import Any, Dict, Generic, Tuple, Type
from annotated_types import T
import inspect


def can_accept_kwargs(func, kwargs_dict):
    """Check if function can accept the provided kwargs."""
    sig = inspect.signature(func)

    # Check for **kwargs parameter
    for param in sig.parameters.values():
        if param.kind == param.VAR_KEYWORD:
            return True

    # Check for specific named parameters
    return any(name in sig.parameters for name in kwargs_dict)


defaults: Dict[str, Dict[str, Any]] = {}


class TypeRegistry(Generic[T]):
    defaults: Dict[str, Any]

    def __init__(self, name: str, defaults: Dict[str, Any] = {}) -> None:
        self.name = name
        self.types: Dict[str, Type[T]] = {}
        self.refs: Dict[str, Dict[str, Any]] = {}
        self.defaults = defaults

    def register(self, name: str, cls: Type[T]) -> None:
        """Register a type with a given name."""
        self.types[name] = cls

    def register_ref(self, name: str, settings: Dict[str, Any]) -> None:
        """Register reference settings for a type."""
        self.refs[name] = settings

    def default_settings(self, name: str) -> Dict[str, Any]:
        return {**self.defaults, **deepcopy(defaults.get(self.name, {}).get(name, {}))}

    def make(self, settings: Dict[str, Any] | str, **kwargs) -> Tuple[T, Dict[str, Any]]:
        """Create an instance of the requested type with proper settings."""
        if isinstance(settings, str):
            settings = {"type": settings}

        base_settings: Dict[str, Any] = self.default_settings(settings["type"])
        type_chain: set[str] = set()
        type_chain.add(settings["type"])

        ref_type = self.refs.get(settings["type"])
        while ref_type is not None:
            settings["type"] = ref_type["type"]
            base_settings = {
                **base_settings,
                **self.default_settings(ref_type["type"]),
                **ref_type,
            }

            if ref_type["type"] in type_chain:
                raise ValueError(f"Circular reference in types: {type_chain}")

            type_chain.add(ref_type["type"])
            ref_type = self.refs.get(ref_type["type"])

        settings = {**base_settings, **settings}

        cls: Type[T] | None = self.types.get(settings["type"])

        if cls is None:
            raise ValueError(f"No type registered with name: {settings['type']}")

        # Create instance with kwargs only if the class can accept them
        if kwargs and can_accept_kwargs(cls.__init__, kwargs):
            return cls(settings, **kwargs), settings
        else:
            return cls(settings), settings


def set_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Set default values for all types."""
    defaults.update(settings)
    return defaults
