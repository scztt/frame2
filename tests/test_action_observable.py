"""
Tests for Action-based Observable system.

Tests all components:
- Actions (ReplaceAction, FuncAction, PropertyAction)
- Model (emit, subscribe, state immutability)
- Observers (PropertyObserver, ChangedObserver, LogObserver, chaining)
- Sources (ShellSource)
- Integration (full target example)
"""

import pytest
import tempfile
import os
from frame.action_observable import (
    ReplaceAction, FuncAction, PropertyAction,
    Model, PropertyObserver, ChangedObserver, LogObserver,
    ShellSource, ShellSourceSettings,
    TailSource, TailSourceSettings,
    ScreenshotSource, ScreenshotSourceSettings,
    OSCSource, OSCSourceSettings,
    make_source
)


class TestActions:
    """Test Action implementations."""

    def test_replace_action(self):
        """ReplaceAction always returns the same value."""
        action = ReplaceAction(42)
        assert action.apply(0) == 42
        assert action.apply(100) == 42
        assert action.apply(None) == 42

    def test_func_action(self):
        """FuncAction wraps a lambda/function."""
        action = FuncAction(lambda x: x + 10)
        assert action.apply(5) == 15
        assert action.apply(0) == 10

        # Test with different function
        action2 = FuncAction(lambda x: x * 2)
        assert action2.apply(5) == 10

    def test_property_action(self):
        """PropertyAction targets specific dict key."""
        action = PropertyAction("count", ReplaceAction(100))
        state = {"count": 0, "name": "test"}
        new_state = action.apply(state)

        # Check new state has updated value
        assert new_state["count"] == 100
        assert new_state["name"] == "test"

        # Check original state unchanged (immutability)
        assert state["count"] == 0
        assert new_state is not state

    def test_property_action_with_func(self):
        """PropertyAction can use FuncAction to transform property."""
        action = PropertyAction("count", FuncAction(lambda x: x + 1))
        state = {"count": 5}
        new_state = action.apply(state)

        assert new_state["count"] == 6
        assert state["count"] == 5  # Original unchanged


class TestModel:
    """Test Model observable container."""

    def test_model_emit_action(self):
        """Model.emit applies action and notifies subscribers."""
        model = Model({"count": 0})
        received = []

        def observer(state):
            received.append(state)

        model.subscribe(observer)
        model.emit(PropertyAction("count", ReplaceAction(42)))

        # Check subscriber received new state
        assert len(received) == 1
        assert received[0]["count"] == 42

    def test_model_state_immutability(self):
        """Model state updates are immutable."""
        model = Model({"value": 1})
        original_state = model.state

        model.emit(PropertyAction("value", FuncAction(lambda x: x + 1)))

        # Original state reference unchanged
        assert original_state["value"] == 1

        # Model state updated
        assert model.state["value"] == 2

        # Different object
        assert model.state is not original_state

    def test_model_multiple_subscribers(self):
        """Model notifies all subscribers."""
        model = Model({"count": 0})
        received1 = []
        received2 = []

        model.subscribe(lambda state: received1.append(state["count"]))
        model.subscribe(lambda state: received2.append(state["count"]))

        model.emit(PropertyAction("count", ReplaceAction(42)))

        assert received1 == [42]
        assert received2 == [42]

    def test_model_subscription_unsubscribe(self):
        """Subscription can be used to unsubscribe."""
        model = Model({"count": 0})
        received = []

        subscription = model.subscribe(lambda state: received.append(state["count"]))
        model.emit(PropertyAction("count", ReplaceAction(1)))

        subscription.unsubscribe()
        model.emit(PropertyAction("count", ReplaceAction(2)))

        # Only received first emission
        assert received == [1]

    def test_model_subscription_context_manager(self):
        """Subscription works as context manager."""
        model = Model({"count": 0})
        received = []

        with model.subscribe(lambda state: received.append(state["count"])):
            model.emit(PropertyAction("count", ReplaceAction(1)))

        # Auto-unsubscribed after context
        model.emit(PropertyAction("count", ReplaceAction(2)))

        # Only received first emission
        assert received == [1]


class TestObservers:
    """Test Observer implementations."""

    def test_property_observer(self):
        """PropertyObserver extracts dict property."""
        observer = PropertyObserver("cpu")
        received = []

        observer.subscribe(lambda value: received.append(value))
        observer({"cpu": 20})

        assert received == [20]

    def test_property_observer_multiple_subscribers(self):
        """PropertyObserver notifies all subscribers."""
        observer = PropertyObserver("value")
        received1 = []
        received2 = []

        observer.subscribe(lambda value: received1.append(value))
        observer.subscribe(lambda value: received2.append(value))
        observer({"value": 42})

        assert received1 == [42]
        assert received2 == [42]

    def test_changed_observer(self):
        """ChangedObserver filters duplicate values."""
        observer = ChangedObserver()
        received = []

        observer.subscribe(lambda value: received.append(value))

        observer(5)
        observer(5)  # Duplicate - should be filtered
        observer(10)
        observer(10)  # Duplicate - should be filtered
        observer(5)  # Different from last

        assert received == [5, 10, 5]

    def test_log_observer(self, capsys):
        """LogObserver prints to console."""
        observer = LogObserver(prefix="Test")
        observer(42)

        captured = capsys.readouterr()
        assert "Test: 42" in captured.out

    def test_log_observer_default_prefix(self, capsys):
        """LogObserver uses default prefix."""
        observer = LogObserver()
        observer("hello")

        captured = capsys.readouterr()
        assert "Log: hello" in captured.out

    def test_observer_chaining(self):
        """Observers chain with >> operator."""
        prop_obs = PropertyObserver("value")
        changed_obs = ChangedObserver()
        received = []

        # Chain: PropertyObserver >> ChangedObserver
        prop_obs >> changed_obs
        changed_obs.subscribe(lambda value: received.append(value))

        # Emit different states
        prop_obs({"value": 10})
        prop_obs({"value": 10})  # Duplicate - filtered
        prop_obs({"value": 20})

        assert received == [10, 20]

    def test_observer_triple_chain(self, capsys):
        """Observers can chain multiple times."""
        prop_obs = PropertyObserver("value")
        changed_obs = ChangedObserver()
        log_obs = LogObserver(prefix="Chain")

        # Chain: PropertyObserver >> ChangedObserver >> LogObserver
        prop_obs >> changed_obs >> log_obs

        prop_obs({"value": 10})
        prop_obs({"value": 10})  # Filtered
        prop_obs({"value": 20})

        captured = capsys.readouterr()
        assert "Chain: 10" in captured.out
        assert "Chain: 20" in captured.out


class TestShellSource:
    """Test ShellSource."""

    def test_shell_source_run(self):
        """ShellSource executes command and notifies subscribers."""
        settings = ShellSourceSettings(command="echo hello")
        shell = ShellSource(settings)
        received = []

        shell.subscribe(lambda result: received.append(result))
        result = shell.run()

        assert result == "hello"
        assert received == ["hello"]

    def test_shell_source_multiple_subscribers(self):
        """ShellSource notifies all subscribers."""
        settings = ShellSourceSettings(command="echo test")
        shell = ShellSource(settings)
        received1 = []
        received2 = []

        shell.subscribe(lambda result: received1.append(result))
        shell.subscribe(lambda result: received2.append(result))

        shell.run()

        assert received1 == ["test"]
        assert received2 == ["test"]

    def test_shell_source_command_with_output(self):
        """ShellSource captures command output."""
        settings = ShellSourceSettings(command="echo 'line1' && echo 'line2'")
        shell = ShellSource(settings)
        result = shell.run()

        # Output should contain both lines
        assert "line1" in result
        assert "line2" in result

    def test_shell_source_with_json_parser(self):
        """ShellSource applies JSON parser to output."""
        settings = ShellSourceSettings(
            command='echo \'{"value": 42}\'',
            parser="json"
        )
        shell = ShellSource(settings)
        received = []

        shell.subscribe(lambda result: received.append(result))
        result = shell.run()

        assert result == {"value": 42}
        assert received == [{"value": 42}]

    def test_shell_source_with_regex_parser(self):
        """ShellSource applies regex parser to extract values."""
        # Command outputs: "Temperature: 23.5°C"
        settings = ShellSourceSettings(
            command='echo "Temperature: 23.5°C"',
            parser={
                "type": "regex",
                "pattern": r"Temperature: ([\d.]+)",
                "group": 1
            }
        )
        shell = ShellSource(settings)
        received = []

        shell.subscribe(lambda result: received.append(result))
        result = shell.run()

        assert result == "23.5"
        assert received == ["23.5"]

    def test_shell_source_with_list_command(self):
        """ShellSource accepts list-style commands."""
        settings = ShellSourceSettings(command=["echo", "hello from list"])
        shell = ShellSource(settings)
        received = []

        shell.subscribe(lambda result: received.append(result))
        result = shell.run()

        assert result == "hello from list"
        assert received == ["hello from list"]

    def test_shell_source_with_list_command_multiple_args(self):
        """ShellSource handles list commands with multiple arguments."""
        settings = ShellSourceSettings(command=["echo", "-n", "no newline"])
        shell = ShellSource(settings)
        result = shell.run()

        assert result == "no newline"


class TestTailSource:
    """Test TailSource."""

    def test_tail_source_reads_file(self):
        """TailSource reads file tail and notifies subscribers."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("line 1\n")
            f.write("line 2\n")
            f.write("line 3\n")
            temp_path = f.name

        try:
            settings = TailSourceSettings(path=temp_path, lines=10)
            tail = TailSource(settings)
            received = []

            tail.subscribe(lambda content: received.append(content))
            result = tail.run()

            # Should read all lines
            assert "line 1" in result
            assert "line 2" in result
            assert "line 3" in result
            assert len(received) == 1
            assert received[0] == result

        finally:
            os.unlink(temp_path)

    def test_tail_source_caches_on_no_change(self):
        """TailSource returns cached value if file hasn't changed."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("initial content\n")
            temp_path = f.name

        try:
            settings = TailSourceSettings(path=temp_path, lines=10)
            tail = TailSource(settings)
            received = []

            tail.subscribe(lambda content: received.append(content))

            # First run - should notify
            result1 = tail.run()
            assert "initial content" in result1
            assert len(received) == 1

            # Second run without file modification - should NOT notify
            result2 = tail.run()
            assert result2 == result1
            assert len(received) == 1  # Still only 1 notification

        finally:
            os.unlink(temp_path)

    def test_tail_source_detects_file_changes(self):
        """TailSource detects file modifications and notifies."""
        import time

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("initial content\n")
            temp_path = f.name

        try:
            settings = TailSourceSettings(path=temp_path, lines=10)
            tail = TailSource(settings)
            received = []

            tail.subscribe(lambda content: received.append(content))

            # First run
            result1 = tail.run()
            assert "initial content" in result1
            assert len(received) == 1

            # Wait a bit to ensure different mtime
            time.sleep(0.01)

            # Modify the file
            with open(temp_path, 'a') as f:
                f.write("new content\n")

            # Second run - should detect change and notify
            result2 = tail.run()
            assert "new content" in result2
            assert len(received) == 2  # Two notifications now

        finally:
            os.unlink(temp_path)

    def test_tail_source_limits_lines(self):
        """TailSource respects line limit."""
        # Create a temporary file with many lines
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for i in range(100):
                f.write(f"line {i}\n")
            temp_path = f.name

        try:
            settings = TailSourceSettings(path=temp_path, lines=5)
            tail = TailSource(settings)

            result = tail.run()

            # Should contain last 5 lines
            assert "line 99" in result
            assert "line 98" in result
            assert "line 97" in result
            assert "line 96" in result
            assert "line 95" in result

            # Should not contain early lines
            assert "line 0" not in result
            assert "line 50" not in result

        finally:
            os.unlink(temp_path)


class TestScreenshotSource:
    """Test ScreenshotSource."""

    def test_screenshot_source_initialization(self):
        """ScreenshotSource initializes with correct settings."""
        # Full screen settings
        settings = ScreenshotSourceSettings()
        screenshot = ScreenshotSource(settings)

        assert screenshot.x is None
        assert screenshot.y is None
        assert screenshot.width is None
        assert screenshot.height is None
        assert screenshot.sudo is False
        assert screenshot.id == "screenshot"

    def test_screenshot_source_region_settings(self):
        """ScreenshotSource initializes with region settings."""
        settings = ScreenshotSourceSettings(
            x=100, y=200, width=800, height=600,
            sudo=False, id="custom_screenshot"
        )
        screenshot = ScreenshotSource(settings)

        assert screenshot.x == 100
        assert screenshot.y == 200
        assert screenshot.width == 800
        assert screenshot.height == 600
        assert screenshot.id == "custom_screenshot"

    def test_screenshot_source_subscribes(self):
        """ScreenshotSource allows subscriptions."""
        settings = ScreenshotSourceSettings()
        screenshot = ScreenshotSource(settings)
        received = []

        screenshot.subscribe(lambda ref: received.append(ref))

        # Just verify subscription works, don't actually run screencapture
        assert len(received) == 0  # No screenshot taken yet


class TestOSCSource:
    """Test OSCSource."""

    def test_osc_source_initialization(self):
        """OSCSource initializes with correct settings."""
        settings = OSCSourceSettings(
            port=9000,
            address="/test/value"
        )
        osc = OSCSource(settings)

        assert osc.port == 9000
        assert osc.address == "/test/value"
        assert osc.ip == "0.0.0.0"  # Default
        assert osc.value_index is None
        assert osc.server is None
        assert osc.server_thread is None

    def test_osc_source_custom_ip(self):
        """OSCSource accepts custom IP address."""
        settings = OSCSourceSettings(
            port=9000,
            address="/test/value",
            ip="127.0.0.1"
        )
        osc = OSCSource(settings)

        assert osc.ip == "127.0.0.1"

    def test_osc_source_with_value_index(self):
        """OSCSource can extract single value at index."""
        settings = OSCSourceSettings(
            port=9000,
            address="/test/value",
            value_index=0
        )
        osc = OSCSource(settings)

        assert osc.value_index == 0

    def test_osc_source_run_starts_server(self):
        """OSCSource.run() starts the server in background thread."""
        import time

        settings = OSCSourceSettings(
            port=9001,  # Use different port for each test
            address="/test/run"
        )
        osc = OSCSource(settings)

        try:
            # Server should not be running initially
            assert osc.server is None
            assert osc.server_thread is None

            # Start server
            osc.run()

            # Server should now be running
            assert osc.server is not None
            assert osc.server_thread is not None
            assert osc.server_thread.is_alive()

            # Give server a moment to fully initialize
            time.sleep(0.1)

        finally:
            osc.stop()

    def test_osc_source_receives_message_with_value_index(self):
        """OSCSource receives message and extracts value at index."""
        import time
        from pythonosc.udp_client import SimpleUDPClient

        settings = OSCSourceSettings(
            port=9002,
            address="/test/indexed",
            value_index=0  # Extract first value
        )
        osc = OSCSource(settings)
        received = []

        osc.subscribe(lambda value: received.append(value))

        try:
            # Start server
            osc.run()
            time.sleep(0.1)  # Give server time to start

            # Send OSC message
            client = SimpleUDPClient("127.0.0.1", 9002)
            client.send_message("/test/indexed", [42, 100, 200])

            # Give time for message to be received
            time.sleep(0.1)

            # Should have received the first value (index 0)
            assert len(received) == 1
            assert received[0] == 42

        finally:
            osc.stop()

    def test_osc_source_receives_message_without_value_index(self):
        """OSCSource receives message and returns all values as list."""
        import time
        from pythonosc.udp_client import SimpleUDPClient

        settings = OSCSourceSettings(
            port=9003,
            address="/test/array",
            value_index=None  # Return all values
        )
        osc = OSCSource(settings)
        received = []

        osc.subscribe(lambda value: received.append(value))

        try:
            # Start server
            osc.run()
            time.sleep(0.1)

            # Send OSC message with multiple values
            client = SimpleUDPClient("127.0.0.1", 9003)
            client.send_message("/test/array", [10, 20, 30])

            time.sleep(0.1)

            # Should have received all values as list
            assert len(received) == 1
            assert received[0] == [10, 20, 30]

        finally:
            osc.stop()

    def test_osc_source_multiple_subscribers(self):
        """OSCSource notifies all subscribers."""
        import time
        from pythonosc.udp_client import SimpleUDPClient

        settings = OSCSourceSettings(
            port=9004,
            address="/test/multi",
            value_index=0
        )
        osc = OSCSource(settings)
        received1 = []
        received2 = []

        osc.subscribe(lambda value: received1.append(value))
        osc.subscribe(lambda value: received2.append(value))

        try:
            osc.run()
            time.sleep(0.1)

            client = SimpleUDPClient("127.0.0.1", 9004)
            client.send_message("/test/multi", [99])

            time.sleep(0.1)

            # Both subscribers should receive the value
            assert received1 == [99]
            assert received2 == [99]

        finally:
            osc.stop()

    def test_osc_source_stop_shuts_down_server(self):
        """OSCSource.stop() shuts down the server."""
        import time

        settings = OSCSourceSettings(
            port=9005,
            address="/test/stop"
        )
        osc = OSCSource(settings)

        # Start server
        osc.run()
        time.sleep(0.1)

        assert osc.server is not None
        assert osc.server_thread is not None

        # Stop server
        osc.stop()
        time.sleep(0.1)

        # Server should be cleaned up
        assert osc.server is None
        assert osc.server_thread is None

    def test_osc_source_handles_missing_value_at_index(self):
        """OSCSource returns None if value_index is out of range."""
        import time
        from pythonosc.udp_client import SimpleUDPClient

        settings = OSCSourceSettings(
            port=9006,
            address="/test/missing",
            value_index=5  # Request index that won't exist
        )
        osc = OSCSource(settings)
        received = []

        osc.subscribe(lambda value: received.append(value))

        try:
            osc.run()
            time.sleep(0.1)

            # Send message with only 2 values
            client = SimpleUDPClient("127.0.0.1", 9006)
            client.send_message("/test/missing", [10, 20])

            time.sleep(0.1)

            # Should have received None (index out of range)
            assert len(received) == 1
            assert received[0] is None

        finally:
            osc.stop()

    def test_osc_source_run_idempotent(self, capsys):
        """Calling run() multiple times doesn't start multiple servers."""
        import time

        settings = OSCSourceSettings(
            port=9007,
            address="/test/idempotent"
        )
        osc = OSCSource(settings)

        try:
            osc.run()
            time.sleep(0.1)

            server1 = osc.server
            thread1 = osc.server_thread

            # Run again
            osc.run()

            # Should be same server
            assert osc.server is server1
            assert osc.server_thread is thread1

            # Should print message about already running
            captured = capsys.readouterr()
            assert "already running" in captured.out

        finally:
            osc.stop()


class TestSourceRegistry:
    """Test source registry and make_source."""

    def test_make_source_shell_from_dict(self):
        """make_source creates ShellSource from dict."""
        source, settings = make_source({
            "type": "shell",
            "command": "echo test"
        })

        assert isinstance(source, ShellSource)
        assert source.command == "echo test"
        assert settings["command"] == "echo test"

    def test_make_source_shell_with_parser(self):
        """make_source creates ShellSource with parser from dict."""
        source, settings = make_source({
            "type": "shell",
            "command": "echo '{\"value\": 42}'",
            "parser": "json"
        })

        assert isinstance(source, ShellSource)
        assert source.parser is not None
        result = source.run()
        assert result == {"value": 42}

    def test_make_source_tail_from_dict(self):
        """make_source creates TailSource from dict."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content\n")
            temp_path = f.name

        try:
            source, settings = make_source({
                "type": "tail",
                "path": temp_path,
                "lines": 50
            })

            assert isinstance(source, TailSource)
            assert source.path == temp_path
            assert source.lines == 50
        finally:
            os.unlink(temp_path)

    def test_make_source_screenshot_from_dict(self):
        """make_source creates ScreenshotSource from dict."""
        source, settings = make_source({
            "type": "screenshot",
            "x": 100,
            "y": 200,
            "width": 800,
            "height": 600,
            "id": "test_screenshot"
        })

        assert isinstance(source, ScreenshotSource)
        assert source.x == 100
        assert source.y == 200
        assert source.width == 800
        assert source.height == 600
        assert source.id == "test_screenshot"

    def test_make_source_from_string(self):
        """make_source creates source from type string."""
        # Note: This will fail without a 'command' field for shell
        # since it's required. Let's test with screenshot which has defaults.
        source, settings = make_source("screenshot")

        assert isinstance(source, ScreenshotSource)
        assert source.id == "screenshot"

    def test_make_source_osc_from_dict(self):
        """make_source creates OSCSource from dict."""
        source, settings = make_source({
            "type": "osc",
            "port": 8000,
            "address": "/test/value"
        })

        assert isinstance(source, OSCSource)
        assert source.port == 8000
        assert source.address == "/test/value"
        assert source.ip == "0.0.0.0"  # Default

    def test_make_source_osc_with_all_settings(self):
        """make_source creates OSCSource with all settings from dict."""
        source, settings = make_source({
            "type": "osc",
            "port": 9000,
            "address": "/control/volume",
            "ip": "127.0.0.1",
            "value_index": 0
        })

        assert isinstance(source, OSCSource)
        assert source.port == 9000
        assert source.address == "/control/volume"
        assert source.ip == "127.0.0.1"
        assert source.value_index == 0

    def test_make_source_settings_dataclass_construction(self):
        """make_source constructs settings dataclass from dict."""
        source, settings = make_source({
            "type": "shell",
            "command": "date",
            "sudo": True
        })

        # Verify the settings object was constructed properly
        assert isinstance(source, ShellSource)
        assert source.sudo is True
        assert source.command == "date"


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_target_example(self, capsys):
        """
        Test the target example from the plan:
        - Shell source runs 'date'
        - Result wrapped in PropertyAction and emitted to model
        - PropertyObserver extracts date value
        - ChangedObserver filters duplicates
        - LogObserver prints to console
        """
        # Model with one field
        model = Model({'date': None})

        # Shell source
        shell = ShellSource(ShellSourceSettings(command='date'))

        # Connect: shell -> PropertyAction -> model
        shell.subscribe(lambda result: model.emit(
            PropertyAction("date", ReplaceAction(result))
        ))

        # Watch model: PropertyObserver >> ChangedObserver >> LogObserver
        prop_obs = PropertyObserver("date")
        changed_obs = ChangedObserver()
        log_obs = LogObserver()

        prop_obs >> changed_obs >> log_obs
        model.subscribe(prop_obs)

        # Run it
        shell.run()

        # Verify state updated
        assert model.state['date'] is not None
        assert len(model.state['date']) > 0

        # Verify logged to console
        captured = capsys.readouterr()
        assert "Log:" in captured.out
        assert model.state['date'] in captured.out

    def test_model_with_shell_multiple_updates(self, capsys):
        """Test multiple shell updates to model."""
        model = Model({'counter': 0})

        # Manually trigger updates
        def update_counter(value):
            current = model.state.get('counter', 0)
            model.emit(PropertyAction('counter', ReplaceAction(current + 1)))

        prop_obs = PropertyObserver('counter')
        log_obs = LogObserver(prefix="Counter")

        prop_obs >> log_obs
        model.subscribe(prop_obs)

        # Trigger multiple updates
        update_counter(None)
        update_counter(None)
        update_counter(None)

        assert model.state['counter'] == 3

        captured = capsys.readouterr()
        assert "Counter: 1" in captured.out
        assert "Counter: 2" in captured.out
        assert "Counter: 3" in captured.out

    def test_full_pipeline_with_transformation(self):
        """Test complete pipeline with value transformation."""
        model = Model({'value': 0})
        received_values = []

        # Observer chain that transforms and collects values
        prop_obs = PropertyObserver('value')
        changed_obs = ChangedObserver()

        prop_obs >> changed_obs
        changed_obs.subscribe(lambda v: received_values.append(v))
        model.subscribe(prop_obs)

        # Emit various actions
        model.emit(PropertyAction('value', ReplaceAction(10)))
        model.emit(PropertyAction('value', ReplaceAction(10)))  # Duplicate
        model.emit(PropertyAction('value', FuncAction(lambda x: x * 2)))
        model.emit(PropertyAction('value', FuncAction(lambda x: x + 5)))

        assert received_values == [10, 20, 25]
        assert model.state['value'] == 25
