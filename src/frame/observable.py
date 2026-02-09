"""
Reactive Observable system for Frame2.

Provides Rx-style observables with chainable operators for composable reactive programming.
"""

from typing import Any, Callable, Generic, TypeVar, List, Optional, Dict
from dataclasses import dataclass

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class ObservableSettings:
    """Base settings class for Observables. Subclasses extend this."""

    pass


class Observable(Generic[T]):
    """
    Base Observable class implementing Rx-style reactive streams.

    Observables can be:
    - Subscribed to with callbacks
    - Chained with operators via pipe()
    - Typed for type safety

    Example:
        obs = Observable[int]()
        obs.pipe(
            Changed(initial=0),
            Log()
        ).subscribe(lambda x: print(f"Final: {x}"))

        obs.emit(0)  # No output (same as initial)
        obs.emit(5)  # Logs "5", prints "Final: 5"
    """

    def __init__(self, settings: Optional[ObservableSettings] = None):
        """
        Initialize Observable.

        Args:
            settings: Configuration for this observable (follows class hierarchy)
        """
        self.settings = settings or ObservableSettings()
        self._subscribers: List[Callable[[T], None]] = []

    def subscribe(self, callback: Callable[[T], None]) -> "Subscription":
        """
        Subscribe to this observable with a callback.

        Args:
            callback: Function called with each emitted value

        Returns:
            Subscription object for unsubscribing
        """
        self._subscribers.append(callback)
        return Subscription(self, callback)

    def unsubscribe(self, callback: Callable[[T], None]) -> None:
        """
        Unsubscribe a callback from this observable.

        Args:
            callback: The callback to remove
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, value: T) -> None:
        """
        Emit a value to all subscribers.

        Args:
            value: Value to emit
        """
        for callback in self._subscribers:
            try:
                callback(value)
            except Exception as e:
                print(f"Error in subscriber: {e}")

    def pipe(self, *operators: "ObservableOperator") -> "Observable":
        """
        Chain operators to create a new Observable.

        Args:
            *operators: Observable operators to apply in sequence

        Returns:
            New Observable with operators applied

        Example:
            obs.pipe(Changed(initial=0), Log()).subscribe(callback)
        """
        result: Observable = self
        for operator in operators:
            result = operator.apply(result)
        return result


class Subscription:
    """Handle for unsubscribing from an Observable."""

    def __init__(self, observable: Observable[Any], callback: Callable[[Any], None]):
        self.observable = observable
        self.callback = callback

    def unsubscribe(self) -> None:
        """Remove this subscription."""
        self.observable.unsubscribe(self.callback)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.unsubscribe()


class ObservableOperator:
    """
    Base class for Observable operators.

    Operators transform observables in a chain.
    """

    def apply(self, source: Observable) -> Observable:
        """
        Apply this operator to a source observable.

        Args:
            source: Input observable

        Returns:
            New observable with operator applied
        """
        raise NotImplementedError


# Observable Operators


@dataclass
class ChangedSettings(ObservableSettings):
    """Settings for Changed operator."""

    initial: Any = None


class Changed(ObservableOperator):
    """
    Observable operator that only emits when value changes.

    Similar to Rx's distinctUntilChanged operator.

    Settings:
        initial: Initial value to compare against

    Example:
        obs.pipe(Changed(initial=0))  # Only emits when value != last value
    """

    def __init__(self, initial: Any = None):
        self.settings = ChangedSettings(initial=initial)

    def apply(self, source: Observable[T]) -> Observable[T]:
        """Apply Changed operator to source."""
        output = Observable[T](self.settings)
        last_value = [self.settings.initial]  # Use list for mutability in closure

        def on_value(value: T):
            if value != last_value[0]:
                last_value[0] = value
                output.emit(value)

        source.subscribe(on_value)
        return output


@dataclass
class LogSettings(ObservableSettings):
    """Settings for Log operator."""

    prefix: str = "Observable"


class Log(ObservableOperator):
    """
    Observable operator that logs values passing through.

    Useful for debugging observable chains.

    Settings:
        prefix: String to prefix log messages with

    Example:
        obs.pipe(Log(prefix="CPU"))  # Logs: "CPU: 45.2"
    """

    def __init__(self, prefix: str = "Observable"):
        self.settings = LogSettings(prefix=prefix)

    def apply(self, source: Observable[T]) -> Observable[T]:
        """Apply Log operator to source."""
        output = Observable[T](self.settings)

        def on_value(value: T):
            print(f"{self.settings.prefix}: {value}")
            output.emit(value)

        source.subscribe(on_value)
        return output


# Model - Container for named observables


class Model:
    """
    Container for named observables built from YAML config.

    Model items have two modes:
    - value: Stores state, only emits on change (uses Changed operator internally)
    - event: No storage, emits every time

    Example config:
        model:
          cpu:
            mode: value      # or omit (defaults to value)
            type: number     # or omit (defaults to string)
            default: 0       # initial value for Changed operator
          button_click:
            mode: event
            type: string

    Usage:
        model = Model.from_dict(config)
        model.get('cpu').subscribe(callback)  # Already change-filtered

        # Atomic mutations via context manager
        with model.mutable() as m:
            m.push('cpu', 45.2)
            m.push('button_click', 'click')
        # All changes applied atomically on exit

        model.get_value('cpu')  # Get current value (only for mode=value)
    """

    class Mutable:
        """Context manager for atomic state mutations (value items only)."""

        def __init__(self, model: "Model"):
            self.model = model
            self.state: Dict[str, Any] = {}

        def __enter__(self) -> "Model.Mutable":
            # Copy current state
            self.state = dict(self.model._current_values)
            return self

        def __exit__(self, exc_type, exc_value, traceback):  # type: ignore
            if exc_type is None:
                # Only apply changes if no exception
                self.model.update(self.state)

        def __setitem__(self, key: str, value: Any) -> None:
            """
            Set a value for a mode=value item.

            Args:
                key: Model key name
                value: Value to set

            Raises:
                KeyError: If key not defined
                ValueError: If key is mode=event (use model.emit() instead)
            """
            if key not in self.model._modes:
                raise KeyError(f"Model key '{key}' not defined")

            if self.model._modes[key] != "value":
                raise ValueError(f"Cannot set mode=event key '{key}' in mutable context. Use model.emit() instead.")

            # Type coercion
            expected_type = self.model._types[key]
            try:
                typed_value = expected_type(value)
            except (ValueError, TypeError):
                typed_value = value  # Pass through if coercion fails

            self.state[key] = typed_value

        def __getitem__(self, key: str) -> Any:
            """Get current value from mutable state."""
            if key not in self.state:
                raise KeyError(f"Model key '{key}' not defined")
            return self.state[key]

    def __init__(self):
        self._raw_observables: Dict[str, Observable] = {}  # For emitting
        self._observables: Dict[str, Observable] = {}  # For subscribing (may be wrapped)
        self._types: Dict[str, type] = {}
        self._modes: Dict[str, str] = {}
        self._current_values: Dict[str, Any] = {}  # For mode=value items

    def define(self, key: str, value_type: str = "string", mode: str = "value", default: Any = None) -> None:
        """
        Define a model key.

        Args:
            key: Name of the model key
            value_type: Python type name ('string', 'number', 'int', 'bool')
            mode: 'value' (stateful, change-filtered) or 'event' (stateless)
            default: Default/initial value for mode=value items
        """
        # Map type string to Python type
        type_map = {
            "string": str,
            "number": float,
            "int": int,
            "bool": bool,
        }

        py_type = type_map.get(value_type, str)
        self._types[key] = py_type
        self._modes[key] = mode

        # Create base observable (for emitting)
        raw_obs = Observable[py_type]()
        self._raw_observables[key] = raw_obs

        # For value mode, wrap with Changed operator and track current value
        if mode == "value":
            self._current_values[key] = default
            # Create a wrapped observable that applies Changed internally
            wrapped_obs = raw_obs.pipe(Changed(initial=default))

            # Also subscribe to wrapped observable to track current value
            def update_current_value(value: Any) -> None:
                self._current_values[key] = value

            wrapped_obs.subscribe(update_current_value)

            self._observables[key] = wrapped_obs
        else:
            # Event mode - no wrapping
            self._observables[key] = raw_obs

    def get(self, key: str) -> Observable:
        """
        Get the Observable for a model key.

        For mode=value items, the observable is already change-filtered.
        For mode=event items, the observable emits all events.

        Args:
            key: Model key name

        Returns:
            Observable for that key (pre-configured based on mode)

        Raises:
            KeyError: If key not defined
        """
        if key not in self._observables:
            raise KeyError(f"Model key '{key}' not defined")
        return self._observables[key]

    def get_value(self, key: str) -> Any:
        """
        Get the current value of a mode=value model key.

        Args:
            key: Model key name

        Returns:
            Current value

        Raises:
            KeyError: If key not defined
            ValueError: If key is mode=event (events have no current value)
        """
        if key not in self._modes:
            raise KeyError(f"Model key '{key}' not defined")

        if self._modes[key] != "value":
            raise ValueError(f"Cannot get_value for mode=event key '{key}'")

        return self._current_values.get(key)

    def mutable(self) -> "Model.Mutable":
        """
        Create a context manager for atomic state mutations.

        Only for mode=value items. Use emit() to fire events.

        Returns:
            Mutable context manager

        Example:
            with model.mutable() as m:
                m['cpu'] = 45.2
                m['memory'] = 1024.0
            # All state changes applied atomically on exit
        """
        return self.Mutable(self)

    def emit(self, key: str, value: Any) -> None:
        """
        Fire an event immediately (for mode=event items).

        This is atomic - the event fires immediately.

        Args:
            key: Model key name
            value: Event payload

        Raises:
            KeyError: If key not defined
            ValueError: If key is mode=value (use mutable() instead)
        """
        if key not in self._raw_observables:
            raise KeyError(f"Model key '{key}' not defined")

        if self._modes[key] != "event":
            raise ValueError(f"Cannot emit on mode=value key '{key}'. Use mutable() context manager instead.")

        # Type coercion
        expected_type = self._types[key]
        try:
            typed_value = expected_type(value)
        except (ValueError, TypeError):
            typed_value = value  # Pass through if coercion fails

        # Emit immediately
        self._raw_observables[key].emit(typed_value)

    def update(self, new_state: Dict[str, Any]) -> None:
        """
        Apply atomic state updates to the model.

        Called by Mutable context manager on exit.
        Only emits state changes for values that actually changed.

        Args:
            new_state: New values for all mode=value items
        """
        old_state = self._current_values
        for key, new_value in new_state.items():
            if key in self._raw_observables:
                old_value = old_state.get(key)
                if old_value != new_value:
                    # Emit to raw observable, Changed operator will handle filtering
                    # But we already checked it changed, so it will pass through
                    self._raw_observables[key].emit(new_value)

    def keys(self) -> List[str]:
        """Get all defined model keys."""
        return list(self._observables.keys())

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "Model":
        """
        Create Model from dictionary config.

        Config format:
            {
                'cpu': {
                    'type': 'number',     # 'string', 'number', 'int', 'bool'
                    'mode': 'value',      # 'value' or 'event' (default: 'value')
                    'default': 0          # initial value for mode=value
                },
                'button_click': {
                    'mode': 'event'       # type defaults to 'string'
                }
            }

        Args:
            config: Dict mapping keys to configuration

        Returns:
            Configured Model instance

        Example:
            config = {
                'cpu': {'type': 'number', 'mode': 'value', 'default': 0},
                'status': {'type': 'string', 'mode': 'value'},
                'beep': {'mode': 'event'}
            }
            model = Model.from_dict(config)
        """
        model = cls()
        for key, spec in config.items():
            if isinstance(spec, dict):
                value_type = spec.get("type", "string")
                mode = spec.get("mode", "value")
                default = spec.get("default", None)
                model.define(key, value_type=value_type, mode=mode, default=default)
            else:
                # Simple format: just the type as a string
                model.define(key, value_type=spec)
        return model
