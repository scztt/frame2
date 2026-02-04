"""
Unit tests for the Observable system.
"""

import pytest
from frame.observable import (
    Observable,
    Changed,
    Log,
    Model,
    ObservableSettings,
)


class TestObservableBasics:
    """Test basic Observable functionality."""

    def test_subscribe_and_emit(self):
        """Test basic subscribe and emit."""
        obs = Observable[int]()
        received = []

        obs.subscribe(lambda x: received.append(x))
        obs.emit(1)
        obs.emit(2)
        obs.emit(3)

        assert received == [1, 2, 3]

    def test_multiple_subscribers(self):
        """Test multiple subscribers receive values."""
        obs = Observable[str]()
        received1 = []
        received2 = []

        obs.subscribe(lambda x: received1.append(x))
        obs.subscribe(lambda x: received2.append(x))

        obs.emit("hello")
        obs.emit("world")

        assert received1 == ["hello", "world"]
        assert received2 == ["hello", "world"]

    def test_unsubscribe(self):
        """Test unsubscribing removes subscription."""
        obs = Observable[int]()
        received = []

        sub = obs.subscribe(lambda x: received.append(x))
        obs.emit(1)

        sub.unsubscribe()
        obs.emit(2)

        assert received == [1]  # Only received first value

    def test_subscription_context_manager(self):
        """Test subscription auto-unsubscribes in context."""
        obs = Observable[int]()
        received = []

        with obs.subscribe(lambda x: received.append(x)):
            obs.emit(1)

        # Outside context, should not receive
        obs.emit(2)

        assert received == [1]


class TestChangedOperator:
    """Test Changed observable operator."""

    def test_changed_filters_duplicates(self):
        """Test Changed only emits on value change."""
        obs = Observable[int]()
        received = []

        obs.pipe(Changed(initial=0)).subscribe(lambda x: received.append(x))

        obs.emit(0)  # Same as initial, filtered
        obs.emit(5)  # Changed, emitted
        obs.emit(5)  # Duplicate, filtered
        obs.emit(10)  # Changed, emitted
        obs.emit(10)  # Duplicate, filtered

        assert received == [5, 10]

    def test_changed_with_none_initial(self):
        """Test Changed with None as initial value."""
        obs = Observable[str]()
        received = []

        obs.pipe(Changed(initial=None)).subscribe(lambda x: received.append(x))

        obs.emit(None)  # Same as initial
        obs.emit("hello")  # Changed
        obs.emit("hello")  # Duplicate
        obs.emit("world")  # Changed

        assert received == ["hello", "world"]


class TestLogOperator:
    """Test Log observable operator."""

    def test_log_passes_through(self, capsys):
        """Test Log operator passes values through."""
        obs = Observable[int]()
        received = []

        obs.pipe(Log(prefix="Test")).subscribe(lambda x: received.append(x))

        obs.emit(42)

        captured = capsys.readouterr()
        assert "Test: 42" in captured.out
        assert received == [42]


class TestObservableChaining:
    """Test chaining multiple operators."""

    def test_changed_then_log(self, capsys):
        """Test chaining Changed and Log."""
        obs = Observable[int]()
        received = []

        obs.pipe(
            Changed(initial=0),
            Log(prefix="Changed")
        ).subscribe(lambda x: received.append(x))

        obs.emit(0)  # Filtered by Changed
        obs.emit(5)  # Passes through
        obs.emit(5)  # Filtered by Changed
        obs.emit(10)  # Passes through

        captured = capsys.readouterr()
        assert "Changed: 5" in captured.out
        assert "Changed: 10" in captured.out
        assert received == [5, 10]


class TestModel:
    """Test Model class."""

    def test_model_define_and_get(self):
        """Test defining model keys and getting observables."""
        model = Model()
        model.define('cpu', 'number')
        model.define('status', 'string')

        # Should be able to get observables
        cpu_obs = model.get('cpu')
        status_obs = model.get('status')

        assert cpu_obs is not None
        assert status_obs is not None

    def test_model_set_emits_value(self):
        """Test setting model value emits to observable."""
        model = Model()
        model.define('cpu', 'number')

        received = []
        model.get('cpu').subscribe(lambda x: received.append(x))

        model.set('cpu', 45.2)
        model.set('cpu', 67.8)

        assert received == [45.2, 67.8]

    def test_model_type_coercion(self):
        """Test model coerces values to correct type."""
        model = Model()
        model.define('count', 'number')

        received = []
        model.get('count').subscribe(lambda x: received.append(x))

        model.set('count', "42")  # String input
        assert received == [42.0]  # Coerced to float

    def test_model_keys(self):
        """Test getting all model keys."""
        model = Model()
        model.define('cpu', 'number')
        model.define('status', 'string')

        keys = model.keys()
        assert set(keys) == {'cpu', 'status'}

    def test_model_undefined_key_raises(self):
        """Test accessing undefined key raises error."""
        model = Model()

        with pytest.raises(KeyError, match="not defined"):
            model.get('nonexistent')

        with pytest.raises(KeyError, match="not defined"):
            model.set('nonexistent', 42)

    def test_model_from_dict(self):
        """Test creating model from dict config."""
        config = {
            'cpu': {'type': 'number'},
            'status': {'type': 'string'},
        }

        model = Model.from_dict(config)

        assert set(model.keys()) == {'cpu', 'status'}

        # Should work
        received = []
        model.get('cpu').subscribe(lambda x: received.append(x))
        model.set('cpu', 50.0)
        assert received == [50.0]


class TestModelWithObservables:
    """Test Model integration with observable chains."""

    def test_model_with_changed_operator(self):
        """Test model key with Changed operator."""
        model = Model()
        model.define('volume', 'number')

        received = []
        model.get('volume').pipe(
            Changed(initial=-10.0)
        ).subscribe(lambda x: received.append(x))

        model.set('volume', -10.0)  # Filtered (same as initial)
        model.set('volume', -5.0)   # Emitted
        model.set('volume', -5.0)   # Filtered (duplicate)
        model.set('volume', -8.0)   # Emitted

        assert received == [-5.0, -8.0]

    def test_model_complete_chain(self, capsys):
        """Test complete observable chain with model."""
        model = Model()
        model.define('cpu', 'number')

        received = []
        model.get('cpu').pipe(
            Changed(initial=0.0),
            Log(prefix="CPU")
        ).subscribe(lambda x: received.append(x))

        model.set('cpu', 0.0)   # Filtered
        model.set('cpu', 45.2)  # Passes through
        model.set('cpu', 45.2)  # Filtered
        model.set('cpu', 67.8)  # Passes through

        captured = capsys.readouterr()
        assert "CPU: 45.2" in captured.out
        assert "CPU: 67.8" in captured.out
        assert received == [45.2, 67.8]


class TestObservableSettings:
    """Test Observable settings class hierarchy."""

    def test_settings_base(self):
        """Test base settings can be created."""
        settings = ObservableSettings()
        assert settings is not None

    def test_changed_settings(self):
        """Test Changed operator settings."""
        changed = Changed(initial=42)
        assert changed.settings.initial == 42

    def test_log_settings(self):
        """Test Log operator settings."""
        log = Log(prefix="MyPrefix")
        assert log.settings.prefix == "MyPrefix"


class TestModelModes:
    """Test Model mode=value vs mode=event behavior."""

    def test_mode_value_filters_changes(self):
        """Test mode=value items are automatically change-filtered."""
        config = {
            'cpu': {'type': 'number', 'mode': 'value', 'default': 0.0}
        }
        model = Model.from_dict(config)

        received = []
        model.get('cpu').subscribe(lambda x: received.append(x))

        model.set('cpu', 0.0)   # Same as default, filtered
        model.set('cpu', 45.2)  # Changed, emitted
        model.set('cpu', 45.2)  # Duplicate, filtered
        model.set('cpu', 67.8)  # Changed, emitted

        assert received == [45.2, 67.8]

    def test_mode_event_forwards_all(self):
        """Test mode=event items forward all events."""
        config = {
            'button_click': {'mode': 'event'}
        }
        model = Model.from_dict(config)

        received = []
        model.get('button_click').subscribe(lambda x: received.append(x))

        model.set('button_click', 'click')
        model.set('button_click', 'click')  # Not filtered!
        model.set('button_click', 'click')  # Not filtered!

        assert received == ['click', 'click', 'click']

    def test_get_value_for_value_mode(self):
        """Test get_value() returns current value for mode=value items."""
        config = {
            'cpu': {'type': 'number', 'mode': 'value', 'default': 0.0}
        }
        model = Model.from_dict(config)

        # Subscribe to trigger updates
        model.get('cpu').subscribe(lambda x: None)

        assert model.get_value('cpu') == 0.0

        model.set('cpu', 45.2)
        assert model.get_value('cpu') == 45.2

        model.set('cpu', 67.8)
        assert model.get_value('cpu') == 67.8

    def test_get_value_raises_for_event_mode(self):
        """Test get_value() raises for mode=event items."""
        config = {
            'button_click': {'mode': 'event'}
        }
        model = Model.from_dict(config)

        with pytest.raises(ValueError, match="mode=event"):
            model.get_value('button_click')

    def test_mode_defaults_to_value(self):
        """Test that mode defaults to 'value' when not specified."""
        config = {
            'cpu': {'type': 'number', 'default': 0.0}
            # mode not specified, should default to 'value'
        }
        model = Model.from_dict(config)

        received = []
        model.get('cpu').subscribe(lambda x: received.append(x))

        model.set('cpu', 0.0)   # Filtered (same as default)
        model.set('cpu', 45.2)  # Emitted
        model.set('cpu', 45.2)  # Filtered

        assert received == [45.2]

    def test_mixed_modes(self):
        """Test model with both value and event mode items."""
        config = {
            'cpu': {'type': 'number', 'mode': 'value', 'default': 0.0},
            'button': {'mode': 'event'}
        }
        model = Model.from_dict(config)

        cpu_values = []
        button_clicks = []

        model.get('cpu').subscribe(lambda x: cpu_values.append(x))
        model.get('button').subscribe(lambda x: button_clicks.append(x))

        model.set('cpu', 45.2)
        model.set('button', 'click')
        model.set('cpu', 45.2)      # Filtered
        model.set('button', 'click') # Not filtered
        model.set('cpu', 67.8)

        assert cpu_values == [45.2, 67.8]
        assert button_clicks == ['click', 'click']


class TestYAMLIntegration:
    """Test YAML config integration."""

    def test_simple_model_yaml_style(self):
        """Test model with simple YAML-style config."""
        # Simulating what would come from YAML
        config = {
            'cpu': {'type': 'number', 'mode': 'value', 'default': 0.0},
            'memory': {'type': 'number', 'mode': 'value', 'default': 0.0},
            'status': {'type': 'string', 'mode': 'value'},
        }

        model = Model.from_dict(config)

        # Set up subscriptions (no need for manual Changed - it's automatic!)
        cpu_values = []
        memory_values = []
        status_values = []

        model.get('cpu').subscribe(lambda x: cpu_values.append(x))
        model.get('memory').subscribe(lambda x: memory_values.append(x))
        model.get('status').subscribe(lambda x: status_values.append(x))

        # Emit values
        model.set('cpu', 45.2)
        model.set('memory', 1024.0)
        model.set('status', 'running')
        model.set('cpu', 45.2)  # Automatically filtered
        model.set('cpu', 67.8)

        assert cpu_values == [45.2, 67.8]
        assert memory_values == [1024.0]
        assert status_values == ['running']

    def test_can_still_chain_operators(self):
        """Test that we can still layer additional operators on top."""
        config = {
            'cpu': {'type': 'number', 'mode': 'value', 'default': 0.0}
        }
        model = Model.from_dict(config)

        received = []
        # Already change-filtered, add Log on top
        model.get('cpu').pipe(Log(prefix="CPU")).subscribe(
            lambda x: received.append(x)
        )

        model.set('cpu', 45.2)
        model.set('cpu', 45.2)  # Filtered
        model.set('cpu', 67.8)

        assert received == [45.2, 67.8]
