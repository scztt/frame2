"""
Reactive Observable system for Frame2.

Provides Rx-style observables with chainable operators for composable reactive programming.
"""

from typing import Any, Callable, Generic, TypeVar, List, Optional, Dict
from dataclasses import dataclass

T = TypeVar('T')
U = TypeVar('U')


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

    def subscribe(self, callback: Callable[[T], None]) -> 'Subscription':
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

    def pipe(self, *operators: 'ObservableOperator') -> 'Observable':
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

    def __enter__(self) -> 'Subscription':
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

    Provides key-based access to typed observables.

    Example config:
        model:
          cpu: {type: number}
          status: {type: string}

    Usage:
        model = Model.from_yaml(config)
        model.get('cpu').pipe(Changed(initial=0)).subscribe(callback)
        model.set('cpu', 45.2)
    """

    def __init__(self):
        self._observables: Dict[str, Observable] = {}
        self._types: Dict[str, type] = {}

    def define(self, key: str, value_type: str, **kwargs) -> None:
        """
        Define a model key with a type.

        Args:
            key: Name of the model key
            value_type: Python type name ('string', 'number', etc.)
            **kwargs: Additional configuration
        """
        # Map type string to Python type
        type_map = {
            'string': str,
            'number': float,
            'int': int,
            'bool': bool,
        }

        py_type = type_map.get(value_type, str)
        self._types[key] = py_type
        self._observables[key] = Observable()

    def get(self, key: str) -> Observable:
        """
        Get the Observable for a model key.

        Args:
            key: Model key name

        Returns:
            Observable for that key

        Raises:
            KeyError: If key not defined
        """
        if key not in self._observables:
            raise KeyError(f"Model key '{key}' not defined")
        return self._observables[key]

    def set(self, key: str, value: Any) -> None:
        """
        Set a value for a model key (emits to its Observable).

        Args:
            key: Model key name
            value: Value to emit

        Raises:
            KeyError: If key not defined
        """
        if key not in self._observables:
            raise KeyError(f"Model key '{key}' not defined")

        # Type coercion
        expected_type = self._types[key]
        try:
            typed_value = expected_type(value)
        except (ValueError, TypeError):
            typed_value = value  # Pass through if coercion fails

        self._observables[key].emit(typed_value)

    def keys(self) -> List[str]:
        """Get all defined model keys."""
        return list(self._observables.keys())

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'Model':
        """
        Create Model from dictionary config.

        Args:
            config: Dict mapping keys to type info
                   e.g. {'cpu': {'type': 'number'}, 'status': {'type': 'string'}}

        Returns:
            Configured Model instance
        """
        model = cls()
        for key, spec in config.items():
            if isinstance(spec, dict):
                value_type = spec.get('type', 'string')
                model.define(key, value_type)
            else:
                # Simple format: key: type
                model.define(key, spec)
        return model
