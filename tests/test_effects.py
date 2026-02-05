"""
Tests for Effects system.

Tests all effect components:
- Effect registry (make_effect)
- ShellEffect
- FileWriteEffect
- OSCEffect (mocked)
- NotificationEffect
- SequenceEffect
- Effects as observables (subscribing to state changes)
"""

import pytest
import tempfile
import os
from frame.action_observable import (
    Model, PropertyObserver, PropertyAction, ReplaceAction,
    ShellEffect, ShellEffectSettings,
    FileWriteEffect, FileWriteEffectSettings,
    SequenceEffect, SequenceEffectSettings,
    make_effect
)


class TestShellEffect:
    """Test ShellEffect."""

    def test_shell_effect_simple_command(self):
        """ShellEffect executes simple shell commands."""
        settings = ShellEffectSettings(command="echo hello")
        effect = ShellEffect(settings)

        # Effects are callable
        effect("trigger")  # Should execute command

    def test_shell_effect_with_template(self):
        """ShellEffect uses Jinja2 templates in commands."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            settings = ShellEffectSettings(
                command=f'echo "{{{{ message }}}}" > {temp_path}'
            )
            effect = ShellEffect(settings)

            # Call effect with dict context
            effect({"message": "Hello from template"})

            # Verify file was written
            with open(temp_path) as f:
                content = f.read()
                assert "Hello from template" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_shell_effect_list_command(self):
        """ShellEffect accepts list-style commands."""
        settings = ShellEffectSettings(command=["echo", "test"])
        effect = ShellEffect(settings)

        effect("trigger")  # Should execute

    def test_shell_effect_from_make_effect(self):
        """make_effect creates ShellEffect from dict."""
        effect, _ = make_effect({
            "type": "shell",
            "command": "echo registry test"
        })

        assert isinstance(effect, ShellEffect)
        effect("trigger")


class TestFileWriteEffect:
    """Test FileWriteEffect."""

    def test_file_write_effect_basic(self):
        """FileWriteEffect writes to file with template."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            settings = FileWriteEffectSettings(
                path=temp_path,
                template="Message: {{ msg }}"
            )
            effect = FileWriteEffect(settings)

            # Call effect with context
            effect({"msg": "Hello World"})

            # Verify file content
            with open(temp_path) as f:
                content = f.read()
                assert content == "Message: Hello World"
        finally:
            os.unlink(temp_path)

    def test_file_write_effect_append_mode(self):
        """FileWriteEffect can append to files."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Line 1\n")
            temp_path = f.name

        try:
            settings = FileWriteEffectSettings(
                path=temp_path,
                template="Line 2\n",
                append=True
            )
            effect = FileWriteEffect(settings)

            effect({})

            # Verify both lines present
            with open(temp_path) as f:
                content = f.read()
                assert "Line 1" in content
                assert "Line 2" in content
        finally:
            os.unlink(temp_path)

    def test_file_write_effect_non_dict_value(self):
        """FileWriteEffect handles non-dict values."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            settings = FileWriteEffectSettings(
                path=temp_path,
                template="Value: {{ value }}"
            )
            effect = FileWriteEffect(settings)

            # Call with simple value
            effect(42)

            with open(temp_path) as f:
                content = f.read()
                assert "Value: 42" in content
        finally:
            os.unlink(temp_path)

    def test_file_write_effect_from_make_effect(self):
        """make_effect creates FileWriteEffect from dict."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            effect, _ = make_effect({
                "type": "file_write",
                "path": temp_path,
                "template": "Test: {{ x }}"
            })

            assert isinstance(effect, FileWriteEffect)
            effect({"x": "registry"})

            with open(temp_path) as f:
                assert "Test: registry" in f.read()
        finally:
            os.unlink(temp_path)


class TestSequenceEffect:
    """Test SequenceEffect."""

    def test_sequence_effect_multiple_effects(self):
        """SequenceEffect executes multiple effects in order."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            settings = SequenceEffectSettings(
                effects=[
                    {
                        "type": "file_write",
                        "path": temp_path,
                        "template": "First\n"
                    },
                    {
                        "type": "file_write",
                        "path": temp_path,
                        "template": "Second\n",
                        "append": True
                    }
                ]
            )
            effect = SequenceEffect(settings)

            effect({})

            # Both effects should have executed
            with open(temp_path) as f:
                content = f.read()
                assert "First" in content
                assert "Second" in content
        finally:
            os.unlink(temp_path)

    def test_sequence_effect_from_make_effect(self):
        """make_effect creates SequenceEffect from dict."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            effect, _ = make_effect({
                "type": "sequence",
                "effects": [
                    {
                        "type": "file_write",
                        "path": temp_path,
                        "template": "Sequence test"
                    }
                ]
            })

            assert isinstance(effect, SequenceEffect)
            effect({})

            with open(temp_path) as f:
                assert "Sequence test" in f.read()
        finally:
            os.unlink(temp_path)


class TestEffectsAsObservables:
    """Test effects used as observables in the reactive system."""

    def test_effect_triggered_by_model_change(self):
        """Effect executes when model state changes."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            # Create model
            model = Model({"count": 0})

            # Create effect
            effect = FileWriteEffect(
                FileWriteEffectSettings(
                    path=temp_path,
                    template="Count: {{ count }}"
                )
            )

            # Subscribe effect to model changes
            model.subscribe(effect)

            # Update model - should trigger effect
            model.emit(PropertyAction("count", ReplaceAction(42)))

            # Verify effect was executed
            with open(temp_path) as f:
                content = f.read()
                assert "Count: 42" in content
        finally:
            os.unlink(temp_path)

    def test_effect_with_property_observer(self):
        """Effect triggered by PropertyObserver lens."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            # Create model
            model = Model({"value": 0, "other": "ignored"})

            # Create effect
            effect = FileWriteEffect(
                FileWriteEffectSettings(
                    path=temp_path,
                    template="Value: {{ value }}"
                )
            )

            # Use PropertyObserver to extract specific field
            prop_obs = PropertyObserver("value")

            # Chain: model -> PropertyObserver -> effect
            # But effect expects full state dict, not just value
            # So we need a wrapper
            def wrap_value(value):
                effect({"value": value})

            prop_obs.subscribe(wrap_value)
            model.subscribe(prop_obs)

            # Update model
            model.emit(PropertyAction("value", ReplaceAction(99)))

            # Verify effect was executed with extracted value
            with open(temp_path) as f:
                content = f.read()
                assert "Value: 99" in content
        finally:
            os.unlink(temp_path)

    def test_multiple_effects_on_same_model(self):
        """Multiple effects can subscribe to the same model."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='_1.txt') as f:
            temp_path1 = f.name
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='_2.txt') as f:
            temp_path2 = f.name

        try:
            model = Model({"status": "unknown"})

            # Create two effects
            effect1 = FileWriteEffect(
                FileWriteEffectSettings(
                    path=temp_path1,
                    template="Effect1: {{ status }}"
                )
            )
            effect2 = FileWriteEffect(
                FileWriteEffectSettings(
                    path=temp_path2,
                    template="Effect2: {{ status }}"
                )
            )

            # Both subscribe to model
            model.subscribe(effect1)
            model.subscribe(effect2)

            # Update model
            model.emit(PropertyAction("status", ReplaceAction("active")))

            # Both effects should have executed
            with open(temp_path1) as f:
                assert "Effect1: active" in f.read()
            with open(temp_path2) as f:
                assert "Effect2: active" in f.read()
        finally:
            if os.path.exists(temp_path1):
                os.unlink(temp_path1)
            if os.path.exists(temp_path2):
                os.unlink(temp_path2)


class TestEffectRegistry:
    """Test effect registry functionality."""

    def test_make_effect_from_dict(self):
        """make_effect creates effects from dict config."""
        effect, settings = make_effect({
            "type": "shell",
            "command": "echo test"
        })

        assert isinstance(effect, ShellEffect)
        assert settings["command"] == "echo test"

    def test_make_effect_settings_dataclass_construction(self):
        """make_effect constructs settings dataclass from dict."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            effect, _ = make_effect({
                "type": "file_write",
                "path": temp_path,
                "template": "{{ x }}",
                "append": True
            })

            assert isinstance(effect, FileWriteEffect)
            assert effect.path == temp_path
            assert effect.append is True
        finally:
            os.unlink(temp_path)
