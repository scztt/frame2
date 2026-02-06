from typing import Dict, Any, List, Optional
from frame.registry import TypeRegistry
from frame.shell import run_command
import asyncio


class StateBase:
    """
    Base class for all state types.

    A State represents some condition on the current machine that can be
    either true (satisfied) or false (not satisfied). States can depend on
    other states, forming a dependency graph. States also expose properties
    that can be used by dependent states.
    """

    def __init_subclass__(cls, *, name: str, **kwargs):
        """Register state types automatically when subclassed."""
        super().__init_subclass__(**kwargs)
        cls.name = name
        states.register(name, cls)

    def __init__(self, settings: Dict[str, Any]) -> None:
        """
        Initialize a state instance.

        Args:
            settings: Configuration dictionary containing:
                - name: Unique identifier for this state instance
                - dependencies: Optional list of state names this depends on
                - Other type-specific settings
        """
        self.name = settings["name"]
        self.settings = settings
        self.dependencies: List[str] = settings.get("dependencies", [])
        self._properties: Dict[str, Any] = {}

    async def check(self) -> bool:
        """
        Check if this state is currently satisfied on the machine.

        Returns:
            True if the state is satisfied, False otherwise
        """
        raise NotImplementedError("Subclasses must implement this method")

    async def ensure(self, dependency_resolver: Optional['DependencyResolver'] = None) -> bool:
        """
        Attempt to make this state true/satisfied.

        This should first ensure all dependencies are satisfied, then
        perform the necessary actions to satisfy this state.

        Args:
            dependency_resolver: Optional resolver to handle dependencies

        Returns:
            True if the state is now satisfied, False otherwise
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_properties(self) -> Dict[str, Any]:
        """
        Get properties exposed by this state.

        These properties can be used by states that depend on this one.
        For example, a Homebrew state might expose the brew binary path.

        Returns:
            Dictionary of property names to values
        """
        return self._properties.copy()


# Create the registry for state types
states = TypeRegistry[StateBase]("state", {})


def make_state(config: "Config", name: str, settings: str | Dict[str, Any]) -> StateBase:
    """
    Factory function to create state instances.

    Args:
        config: The global configuration object
        name: Unique name for this state instance
        settings: Either a string (state type name) or dict with type and settings

    Returns:
        A StateBase instance of the appropriate type
    """
    if isinstance(settings, str):
        settings = {"type": settings}
    settings["name"] = name
    return states.make(settings, config=config)[0]


############################################################
# Dependency Resolution
############################################################

class DependencyResolver:
    """
    Resolves and ensures state dependencies.

    This handles the dependency graph, ensuring states are satisfied
    in the correct order and detecting circular dependencies.
    """

    def __init__(self, all_states: Dict[str, StateBase]):
        """
        Initialize the resolver with all available states.

        Args:
            all_states: Dictionary mapping state names to state instances
        """
        self.all_states = all_states
        self._visiting: set = set()  # For cycle detection
        self._satisfied_cache: Dict[str, bool] = {}

    async def ensure_dependencies(self, state: StateBase) -> bool:
        """
        Ensure all dependencies of a state are satisfied.

        Args:
            state: The state whose dependencies should be ensured

        Returns:
            True if all dependencies are satisfied, False otherwise

        Raises:
            ValueError: If a circular dependency is detected
        """
        for dep_name in state.dependencies:
            if dep_name not in self.all_states:
                raise ValueError(f"Dependency '{dep_name}' not found for state '{state.name}'")

            dep_state = self.all_states[dep_name]

            # Check for circular dependencies
            if dep_name in self._visiting:
                raise ValueError(f"Circular dependency detected: {dep_name}")

            # Check if already satisfied
            if dep_name in self._satisfied_cache and self._satisfied_cache[dep_name]:
                continue

            # Try to ensure the dependency
            self._visiting.add(dep_name)
            try:
                is_satisfied = await dep_state.ensure(self)
                self._satisfied_cache[dep_name] = is_satisfied
                if not is_satisfied:
                    return False
            finally:
                self._visiting.discard(dep_name)

        return True


############################################################
# Implementations
############################################################

class ShellState(StateBase, name="shell"):
    """
    A state that uses shell commands to check and ensure state.

    This is useful for simple states that can be checked and set using
    shell commands. For example, checking if a file exists and creating it.

    Settings:
        - check_cmd: Shell command that returns 0 (or "true") if state is satisfied
        - ensure_cmd: Shell command to execute to satisfy the state
        - sudo: Whether to run commands with sudo (default: False)
    """

    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.check_command = settings["check_cmd"]
        self.ensure_command = settings["ensure_cmd"]
        self.sudo = settings.get("sudo", False)

    async def check(self) -> bool:
        """
        Run the check command and interpret the result.

        The check command should:
        - Return exit code 0 if state is satisfied
        - Return non-zero exit code if state is not satisfied
        - Or output "true"/"1"/"yes" for satisfied, anything else for not satisfied
        """
        try:
            result = await run_command(self.check_command, sudo=self.sudo)
            # Check both exit code (success) and output
            # Consider "true", "1", "yes" as satisfied
            result_lower = result.strip().lower()
            return result_lower in ("true", "1", "yes") or result_lower == ""
        except Exception:
            # If command fails, state is not satisfied
            return False

    async def ensure(self, dependency_resolver: Optional[DependencyResolver] = None) -> bool:
        """
        Ensure dependencies are met, then run the ensure command.

        Args:
            dependency_resolver: Resolver to handle dependencies

        Returns:
            True if state is now satisfied, False otherwise
        """
        # First ensure dependencies
        if dependency_resolver and self.dependencies:
            deps_satisfied = await dependency_resolver.ensure_dependencies(self)
            if not deps_satisfied:
                return False

        # Check if already satisfied
        if await self.check():
            return True

        # Run the ensure command
        try:
            await run_command(self.ensure_command, sudo=self.sudo)
            # Verify the state is now satisfied
            return await self.check()
        except Exception as e:
            print(f"Failed to ensure state '{self.name}': {e}")
            return False
