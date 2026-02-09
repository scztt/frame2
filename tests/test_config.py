"""
Tests for configuration deserialization system.

Tests parsing of sources, model, and effects sections with:
- Inline definitions (source/effect within model)
- String references for connections (no @ prefix)
- Validation of conflicts
- Complete reactive system setup
"""

import pytest
import tempfile
import os
from frame.config import load_config, ReactiveConfig, ConfigError
from frame.action_observable import PropertyAction, ReplaceAction


class TestInlineSource:
    """Test model items with inline source definitions."""

    def test_inline_source_simple(self):
        """Model item can have inline source."""
        config = {"model": {"timestamp": {"default": None, "source": {"type": "shell", "command": "echo 'test'"}}}}

        model = load_config(config)

        # Model should be created with initial state
        assert "timestamp" in model.state
        assert model.state["timestamp"] is None

    def test_inline_source_cannot_have_target(self):
        """Inline source with target field should raise error."""
        config = {"model": {"value": {"source": {"type": "shell", "command": "echo test", "target": "other_field"}}}}  # Conflict!

        with pytest.raises(ConfigError, match="inline source with 'target' field"):
            load_config(config)


class TestInlineEffect:
    """Test model items with inline effect definitions."""

    def test_inline_effect_simple(self):
        """Model item can have inline effect."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            config = {"model": {"counter": {"default": 0, "effect": {"type": "file_write", "path": temp_path, "template": "Count: {{ counter }}"}}}}

            model = load_config(config)

            # Update model - should trigger inline effect
            model.emit(PropertyAction("counter", ReplaceAction(42)))

            # Verify effect executed
            with open(temp_path) as f:
                content = f.read()
                assert "Count: 42" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_inline_effect_cannot_have_source(self):
        """Inline effect with source field should raise error."""
        config = {"model": {"value": {"effect": {"type": "shell", "command": "echo test", "source": "other_field"}}}}  # Conflict!

        with pytest.raises(ConfigError, match="inline effect with 'source' field"):
            load_config(config)


class TestSourcesSection:
    """Test sources section with target connections."""

    def test_source_with_plain_target(self):
        """Source with plain target creates model field automatically."""
        config = {"sources": {"date_source": {"type": "shell", "command": "date", "target": "current_date"}}, "model": {"current_date": None}}

        reactive_config = ReactiveConfig(config)
        model = reactive_config.build()

        # Should have created connection
        assert "date_source" in reactive_config.sources_catalog
        assert "current_date" in model.state

    def test_source_with_at_reference(self):
        """Source with reference connects to existing model field."""
        config = {"sources": {"shell_source": {"type": "shell", "command": "echo test", "target": "output"}}, "model": {"output": {"default": None}}}

        reactive_config = ReactiveConfig(config)
        model = reactive_config.build()

        assert "shell_source" in reactive_config.sources_catalog
        assert "output" in model.state


class TestEffectsSection:
    """Test effects section with source connections."""

    def test_effect_with_at_reference(self):
        """Effect with reference subscribes to model field."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            config = {"model": {"status": {"default": "idle"}}, "effects": {"logger": {"type": "file_write", "path": temp_path, "template": "Status: {{ status }}", "source": "status"}}}

            model = load_config(config)

            # Update model - should trigger effect
            model.emit(PropertyAction("status", ReplaceAction("active")))

            # Verify effect executed
            with open(temp_path) as f:
                content = f.read()
                assert "Status: active" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_effect_cannot_have_inline_source_object(self):
        """Effect with inline source object should raise error."""
        config = {"effects": {"my_effect": {"type": "shell", "command": "echo test", "source": {"type": "shell", "command": "date"}}}}  # Not allowed!

        with pytest.raises(ConfigError, match="inline source object"):
            load_config(config)


class TestReferenceConnection:
    """Test  reference connections between components."""

    def test_model_effect_reference(self):
        """Model can reference named effect with ."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            config = {
                "model": {"value": {"default": 0, "effect": "logger"}},  # Reference to effects section
                "effects": {"logger": {"type": "file_write", "path": temp_path, "template": "Value: {{ value }}"}},
            }

            model = load_config(config)

            # Update model - should trigger referenced effect
            model.emit(PropertyAction("value", ReplaceAction(99)))

            # Verify effect executed
            with open(temp_path) as f:
                content = f.read()
                assert "Value: 99" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestCompleteConfig:
    """Test complete configs with all three sections."""

    def test_all_sections_together(self):
        """Config with sources, model, and effects all working together."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            log_path = f.name

        try:
            config = {
                "sources": {"cmd_source": {"type": "shell", "command": "echo hello", "target": "message"}},
                "model": {"message": {"default": None}, "counter": {"default": 0}},
                "effects": {"log_effect": {"type": "file_write", "path": log_path, "template": "Message: {{ message }}\n", "source": "message"}},
            }

            reactive_config = ReactiveConfig(config)
            model = reactive_config.build()

            # Verify catalogs
            assert "cmd_source" in reactive_config.sources_catalog
            assert "log_effect" in reactive_config.effects_catalog

            # Verify model state
            assert "message" in model.state
            assert "counter" in model.state
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_minimal_model_only_config(self):
        """Minimal config with just model section and inline definitions."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            config = {
                "model": {
                    "temperature": {"default": 20, "source": {"type": "shell", "command": "echo '25'"}, "effect": {"type": "file_write", "path": temp_path, "template": "Temp: {{ temperature }}°C"}}
                }
            }

            model = load_config(config)

            # Manually trigger since we can't run the source in test
            model.emit(PropertyAction("temperature", ReplaceAction(25)))

            # Verify effect executed
            with open(temp_path) as f:
                content = f.read()
                assert "Temp: 25°C" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestConfigValidation:
    """Test config validation and error cases."""

    def test_missing_model_field_for_source(self):
        """Source referencing non-existent model field should error."""
        config = {"sources": {"my_source": {"type": "shell", "command": "echo test", "target": "nonexistent"}}}

        with pytest.raises(ConfigError, match="not found in model state"):
            load_config(config)

    def test_missing_effect_for_reference(self):
        """Model referencing non-existent effect should error."""
        config = {"model": {"value": {"default": 0, "effect": "nonexistent_effect"}}}

        with pytest.raises(ConfigError, match="not found in effects catalog"):
            load_config(config)

    def test_empty_config(self):
        """Empty config should create empty model."""
        config = {}
        model = load_config(config)

        assert model.state == {}

    def test_model_with_simple_values(self):
        """Model can have simple non-dict values."""
        config = {"model": {"counter": 0, "name": "test", "active": True}}

        model = load_config(config)

        assert model.state["counter"] == 0
        assert model.state["name"] == "test"
        assert model.state["active"] is True


class TestCatalogNaming:
    """Test naming conventions for inline definitions."""

    def test_inline_source_naming(self):
        """Inline sources are named 'fieldName(source)'."""
        config = {"model": {"data": {"source": {"type": "shell", "command": "echo test"}}}}

        reactive_config = ReactiveConfig(config)
        reactive_config.build()

        assert "data(source)" in reactive_config.sources_catalog

    def test_inline_effect_naming(self):
        """Inline effects are named 'fieldName(effect)'."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            config = {"model": {"value": {"effect": {"type": "file_write", "path": temp_path, "template": "{{ value }}"}}}}

            reactive_config = ReactiveConfig(config)
            reactive_config.build()

            assert "value(effect)" in reactive_config.effects_catalog
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
