"""
Tests for FormatRenderer and TemplateRenderer.

Tests the new data transformation renderers:
- FormatRenderer: Python .format() with {} placeholders
- TemplateRenderer: Jinja2 templates with ObjectWrapper
- ObjectWrapper: Makes object attributes accessible as dict keys
"""

from frame.renderers import FormatRenderer, TemplateRenderer, ObjectWrapper


class TestFormatRenderer:
    """Test FormatRenderer with Python .format()."""

    def test_format_renderer_with_dict(self):
        """FormatRenderer uses dict values with **kwargs unpacking."""
        renderer = FormatRenderer({"string": "Hello {name}, you are {age} years old"})

        result = renderer.render_data({"name": "Alice", "age": 30})
        assert result == "Hello Alice, you are 30 years old"

    def test_format_renderer_with_list(self):
        """FormatRenderer uses list values with *args unpacking."""
        renderer = FormatRenderer({"string": "{0} + {1} = {2}"})

        result = renderer.render_data([2, 3, 5])
        assert result == "2 + 3 = 5"

    def test_format_renderer_with_tuple(self):
        """FormatRenderer uses tuple values with *args unpacking."""
        renderer = FormatRenderer({"string": "Point: ({}, {})"})

        result = renderer.render_data((10, 20))
        assert result == "Point: (10, 20)"

    def test_format_renderer_with_single_value(self):
        """FormatRenderer uses single value directly."""
        renderer = FormatRenderer({"string": "Value: {}"})

        result = renderer.render_data(42)
        assert result == "Value: 42"

    def test_format_renderer_default_string(self):
        """FormatRenderer has default format string."""
        renderer = FormatRenderer({})

        result = renderer.render_data("test")
        assert result == "test"

    def test_format_renderer_callable(self):
        """FormatRenderer is callable via __call__."""
        renderer = FormatRenderer({"string": "Result: {}"})

        result = renderer(100)
        assert result == "Result: 100"


class TestTemplateRenderer:
    """Test TemplateRenderer with Jinja2."""

    def test_template_renderer_with_dict(self):
        """TemplateRenderer renders dict as template context."""
        renderer = TemplateRenderer({"string": "Hello {{ name }}, you are {{ age }}"})

        result = renderer.render_data({"name": "Bob", "age": 25})
        assert result == "Hello Bob, you are 25"

    def test_template_renderer_with_object(self):
        """TemplateRenderer uses ObjectWrapper for objects."""

        class Person:
            def __init__(self):
                self.name = "Charlie"
                self.age = 35

        renderer = TemplateRenderer({"string": "Hello {{ name }}, you are {{ age }}"})
        person = Person()

        result = renderer.render_data(person)
        assert result == "Hello Charlie, you are 35"

    def test_template_renderer_with_simple_value(self):
        """TemplateRenderer falls back to 'value' variable for simple values."""
        renderer = TemplateRenderer({"string": "Number: {{ value }}"})

        result = renderer.render_data(42)
        assert result == "Number: 42"

    def test_template_renderer_default_template(self):
        """TemplateRenderer has default template."""
        renderer = TemplateRenderer({})

        result = renderer.render_data(123)
        assert result == "123"

    def test_template_renderer_with_expression(self):
        """TemplateRenderer supports Jinja2 expressions."""
        renderer = TemplateRenderer({"string": "{{ x * 2 }}"})

        result = renderer.render_data({"x": 5})
        assert result == "10"

    def test_template_renderer_callable(self):
        """TemplateRenderer is callable via __call__."""
        renderer = TemplateRenderer({"string": "Value: {{ value }}"})

        result = renderer("test")
        assert result == "Value: test"


class TestObjectWrapper:
    """Test ObjectWrapper for making object attributes dict-accessible."""

    def test_object_wrapper_getitem_with_object(self):
        """ObjectWrapper allows dict-style access to object attributes."""

        class TestObj:
            def __init__(self):
                self.x = 10
                self.y = 20

        obj = TestObj()
        wrapper = ObjectWrapper(obj)

        assert wrapper["x"] == 10
        assert wrapper["y"] == 20

    def test_object_wrapper_getitem_with_dict(self):
        """ObjectWrapper passes through dict access."""
        data = {"a": 1, "b": 2}
        wrapper = ObjectWrapper(data)

        assert wrapper["a"] == 1
        assert wrapper["b"] == 2

    def test_object_wrapper_keys_with_object(self):
        """ObjectWrapper returns non-private attributes as keys."""

        class TestObj:
            def __init__(self):
                self.public1 = "a"
                self.public2 = "b"
                self._private = "c"

        obj = TestObj()
        wrapper = ObjectWrapper(obj)
        keys = list(wrapper.keys())

        assert "public1" in keys
        assert "public2" in keys
        assert "_private" not in keys

    def test_object_wrapper_keys_with_dict(self):
        """ObjectWrapper returns dict keys."""
        data = {"key1": 1, "key2": 2}
        wrapper = ObjectWrapper(data)

        assert set(wrapper.keys()) == {"key1", "key2"}

    def test_object_wrapper_items(self):
        """ObjectWrapper provides items() iteration."""
        data = {"x": 10, "y": 20}
        wrapper = ObjectWrapper(data)

        items = dict(wrapper.items())
        assert items == {"x": 10, "y": 20}

    def test_object_wrapper_values(self):
        """ObjectWrapper provides values() iteration."""
        data = {"a": 1, "b": 2}
        wrapper = ObjectWrapper(data)

        values = list(wrapper.values())
        assert set(values) == {1, 2}

    def test_object_wrapper_unpacking_in_template(self):
        """ObjectWrapper enables ** unpacking in Jinja2 templates."""
        import jinja2

        class Config:
            def __init__(self):
                self.host = "localhost"
                self.port = 8080

        config = Config()
        wrapper = ObjectWrapper(config)
        template = jinja2.Template("Server: {{ host }}:{{ port }}")

        # This is the key test - can we unpack wrapper with **?
        result = template.render(**wrapper)
        assert result == "Server: localhost:8080"


class TestRenderersInEffects:
    """Test renderers used in effects."""

    def test_format_renderer_in_effect_context(self):
        """FormatRenderer can be used to pre-process effect input."""
        from frame.action_observable import FileWriteEffect, FileWriteEffectSettings
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            # Create effect with format renderer
            effect = FileWriteEffect(FileWriteEffectSettings(path=temp_path, template="{{ value }}", renderer={"type": "format", "string": "Formatted: {}"}))

            # Call effect with simple value
            effect(42)

            # Verify renderer was applied
            with open(temp_path) as f:
                content = f.read()
                assert "Formatted: 42" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_template_renderer_in_effect_context(self):
        """TemplateRenderer can be used to pre-process effect input."""
        from frame.action_observable import FileWriteEffect, FileWriteEffectSettings
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            # Create effect with template renderer
            effect = FileWriteEffect(FileWriteEffectSettings(path=temp_path, template="{{ value }}", renderer={"type": "template", "string": "Processed: {{ x * 2 }}"}))

            # Call effect with dict
            effect({"x": 10})

            # Verify renderer was applied
            with open(temp_path) as f:
                content = f.read()
                assert "Processed: 20" in content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
