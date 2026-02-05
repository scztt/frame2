"""
Action-based Observable system for Frame2.

Provides Redux/Elm-style architecture with:
- Actions: State transformers with apply(state: T) -> T
- Model: Observable container that accepts actions
- Observers: Callable state watchers that chain with >>
- Sources: Data producers (e.g., ShellSource)
"""

from typing import TypeVar, Generic, Callable, Any, Dict, List
from copy import deepcopy

T = TypeVar('T')


# === Actions ===

class Action(Generic[T]):
    """Base class for state transformers."""

    def apply(self, state: T) -> T:
        """
        Apply this action to a state, returning a new state.

        Args:
            state: Current state

        Returns:
            New state after applying the action
        """
        raise NotImplementedError


class ReplaceAction(Action[T]):
    """Action that always returns a specific value."""

    def __init__(self, value: T):
        """
        Initialize ReplaceAction.

        Args:
            value: The value to return
        """
        self.value = value

    def apply(self, state: T) -> T:
        """Replace state with the stored value."""
        return self.value


class FuncAction(Action[T]):
    """Action that wraps a lambda/function."""

    def __init__(self, func: Callable[[T], T]):
        """
        Initialize FuncAction.

        Args:
            func: Function that transforms state
        """
        self.func = func

    def apply(self, state: T) -> T:
        """Apply the wrapped function to the state."""
        return self.func(state)


class PropertyAction(Action[Dict]):
    """
    Action that gets state[key], applies inner action, sets result back.

    Used to target specific properties in a dictionary-based state.
    """

    def __init__(self, key: str, inner_action: Action):
        """
        Initialize PropertyAction.

        Args:
            key: Dictionary key to target
            inner_action: Action to apply to the property value
        """
        self.key = key
        self.inner_action = inner_action

    def apply(self, state: Dict) -> Dict:
        """
        Apply inner action to state[key], returning new state with updated property.

        Args:
            state: Dictionary state

        Returns:
            New dictionary with updated property
        """
        new_state = deepcopy(state)
        current_value = new_state.get(self.key)
        new_value = self.inner_action.apply(current_value)
        new_state[self.key] = new_value
        return new_state


# === Model ===

class Subscription:
    """Handle for unsubscribing from a Model."""

    def __init__(self, model: 'Model', observer: Callable):
        """
        Initialize Subscription.

        Args:
            model: The model to unsubscribe from
            observer: The observer callback to remove
        """
        self.model = model
        self.observer = observer

    def unsubscribe(self) -> None:
        """Remove this subscription."""
        self.model.unsubscribe(self.observer)

    def __enter__(self) -> 'Subscription':
        return self

    def __exit__(self, *args: Any) -> None:
        self.unsubscribe()


class Model(Generic[T]):
    """
    Observable container for state that accepts actions.

    Model emits (old_state, new_state) tuples to subscribers when actions are applied.
    State updates are immutable - each action creates a new state.

    Example:
        model = Model({'count': 0})
        model.subscribe(lambda state: print(f"State: {state}"))
        model.emit(PropertyAction('count', ReplaceAction(42)))
    """

    def __init__(self, initial_state: T):
        """
        Initialize Model.

        Args:
            initial_state: Initial state value
        """
        self.state = initial_state
        self.subscribers: List[Callable[[T], None]] = []

    def emit(self, action: Action[T]) -> None:
        """
        Apply an action to the state and notify subscribers.

        Process:
        1. Copy current state
        2. Apply action to copy
        3. Replace current state
        4. Notify all subscribers with new_state

        Args:
            action: Action to apply
        """
        old_state = self.state
        new_state = action.apply(deepcopy(old_state))
        self.state = new_state

        for subscriber in self.subscribers:
            try:
                subscriber(new_state)
            except Exception as e:
                print(f"Error in subscriber: {e}")

    def subscribe(self, observer: Callable) -> Subscription:
        """
        Subscribe to state changes.

        Args:
            observer: Callable that receives new_state

        Returns:
            Subscription object for unsubscribing
        """
        self.subscribers.append(observer)
        return Subscription(self, observer)

    def unsubscribe(self, observer: Callable) -> None:
        """
        Unsubscribe an observer.

        Args:
            observer: The observer to remove
        """
        if observer in self.subscribers:
            self.subscribers.remove(observer)


# === Observers ===

class Observer:
    """
    Base class for callable observers.

    Observers can be chained with the >> operator.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """
        Called when the observer receives a value.

        Subclasses must implement this method.
        """
        raise NotImplementedError

    def __rshift__(self, next_observer: 'Observer') -> 'Observer':
        """
        Chain this observer with the next one using >> operator.

        Args:
            next_observer: Observer to chain

        Returns:
            The next observer (for further chaining)
        """
        if hasattr(self, 'subscribe'):
            self.subscribe(next_observer)
        return next_observer


class PropertyObserver(Observer):
    """
    Observer that extracts a specific property from a dictionary state.

    Acts as a lens - takes a dict, extracts state[key], forwards to subscribers.
    Composable with other observers for filtering, logging, etc.
    """

    def __init__(self, key: str):
        """
        Initialize PropertyObserver.

        Args:
            key: Dictionary key to extract
        """
        self.key = key
        self.subscribers: List[Callable[[Any], None]] = []

    def __call__(self, state: Dict) -> None:
        """
        Extract property value from state and forward to subscribers.

        Args:
            state: Dictionary state
        """
        value = state.get(self.key)
        for subscriber in self.subscribers:
            try:
                subscriber(value)
            except Exception as e:
                print(f"Error in PropertyObserver subscriber: {e}")

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to property value changes.

        Args:
            callback: Function called with property value
        """
        self.subscribers.append(callback)


class ChangedObserver(Observer):
    """
    Observer that only forwards values when they change.

    Similar to Rx's distinctUntilChanged operator.
    """

    def __init__(self):
        """Initialize ChangedObserver with sentinel for first value."""
        self.last_value = object()  # Sentinel for "no value yet"
        self.subscribers: List[Callable[[Any], None]] = []

    def __call__(self, value: Any) -> None:
        """
        Forward value to subscribers only if it differs from last value.

        Args:
            value: Current value
        """
        if value != self.last_value:
            self.last_value = value
            for subscriber in self.subscribers:
                try:
                    subscriber(value)
                except Exception as e:
                    print(f"Error in ChangedObserver subscriber: {e}")

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to changed values.

        Args:
            callback: Function called with changed value
        """
        self.subscribers.append(callback)


class LogObserver(Observer):
    """
    Observer that logs values to console.

    Useful for debugging observer chains.
    """

    def __init__(self, prefix: str = "Log"):
        """
        Initialize LogObserver.

        Args:
            prefix: String to prefix log messages with
        """
        self.prefix = prefix

    def __call__(self, value: Any) -> None:
        """
        Log the value to console.

        Args:
            value: Value to log
        """
        print(f"{self.prefix}: {value}")


# === Sources ===
# Re-export sources from the new sources module
from frame.new.sources import (
    ShellSource, ShellSourceSettings,
    TailSource, TailSourceSettings,
    ScreenshotSource, ScreenshotSourceSettings,
    OSCSource, OSCSourceSettings,
    make_source
)

# === Effects ===
# Re-export effects from the new effects module
from frame.new.effects import (
    ShellEffect, ShellEffectSettings,
    FileWriteEffect, FileWriteEffectSettings,
    OSCEffect, OSCEffectSettings,
    NotificationEffect, NotificationEffectSettings,
    SequenceEffect, SequenceEffectSettings,
    make_effect
)

# === Config ===
# Note: Config system available in frame.config
# Import directly from frame.config to avoid circular imports:
#   from frame.config import load_config, ReactiveConfig, ConfigError
