from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from frame.values import make_value
from frame.actions import make_action


@dataclass
class SetupResult:
    success: bool
    output: str
    error: Optional[str] = None


class SetupItem:
    def __init__(self, name: str, settings: Dict[str, Any], config: Any):
        self.name = name
        self.settings = settings
        self.depends = settings.get("depends", [])

        # Create verify value (defaults to shell with detect parser)
        verify_settings = settings.get("verify", "")
        if isinstance(verify_settings, str):
            # String shorthand for shell command - use detect parser to return true/false
            verify_settings = {"type": "shell", "cmd": verify_settings, "parser": {"type": "detect", "pattern": ".*"}}  # Detect any output as true
        elif isinstance(verify_settings, dict):
            # Ensure there's a parser, default to detect
            if "parser" not in verify_settings:
                verify_settings["parser"] = {"type": "detect", "pattern": ".*"}

        self.verify_value = make_value(f"setup/{name}", {"get": verify_settings})

        # Create set action (defaults to shell)
        set_settings = settings.get("set", "")
        if isinstance(set_settings, str):
            # String shorthand for shell command
            set_settings = {"type": "shell", "cmd": set_settings}

        self.set_action = make_action(config, f"setup/{name}", set_settings)

        self.verify_status = None

    async def verify(self, force=False) -> Any:
        """Verify using the value delegate (synchronous wrapper)."""
        if self.verify_status is None or force:
            self.verify_status = SetupResult(success=False, output="Not verified")
            try:
                self.verify_status.success = await self.verify_value.get()
            except Exception as e:
                self.verify_status = SetupResult(success=False, output="Error verifying", error=str(e))
        return self.verify_status

    async def set(self, force=False) -> Any:
        """Async set using the action delegate."""
        if not (self.verify_status) or force:
            try:
                result = await self.set_action.call({}, lambda name: None)
                return result
            except Exception as e:
                return "Error setting up: " + str(e)


def make_setup(name: str, settings: Dict[str, Any], config: Any) -> SetupItem:
    """Create a SetupItem instance from settings."""
    return SetupItem(name, settings, config)


def resolve_dependencies(setup_items: Dict[str, Dict[str, Any]]) -> List[str]:
    """Resolve setup dependencies and return items in dependency order."""
    resolved: List[str] = []
    visited: set[str] = set()
    temp_visited: set[str] = set()

    def visit(item_name: str):
        if item_name in temp_visited:
            raise ValueError(f"Circular dependency detected involving {item_name}")
        if item_name in visited:
            return

        temp_visited.add(item_name)

        item = setup_items.get(item_name)
        if not item:
            raise ValueError(f"Setup item '{item_name}' not found")

        depends = item.get("depends", [])
        for dep in depends:
            visit(dep)

        temp_visited.remove(item_name)
        visited.add(item_name)
        resolved.append(item_name)

    for item_name in setup_items.keys():
        visit(item_name)

    return resolved
