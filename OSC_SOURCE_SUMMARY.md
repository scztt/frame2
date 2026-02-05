# OSCSource Implementation Summary

## Overview

Successfully implemented and tested **OSCSource** - a data source that listens for OSC (Open Sound Control) messages on a UDP port and notifies subscribers when messages arrive.

## Implementation Details

### Files Modified

1. **[src/frame/new/sources.py](src/frame/new/sources.py)** (lines 330-449)
   - Added `OSCSourceSettings` dataclass
   - Added `OSCSource` class with full OSC server functionality

2. **[src/frame/action_observable.py](src/frame/action_observable.py)** (line 344)
   - Re-exported `OSCSource` and `OSCSourceSettings` for easy access

3. **[tests/test_action_observable.py](tests/test_action_observable.py)** (lines 498-758)
   - Added comprehensive `TestOSCSource` test class with 10 tests
   - Added registry integration tests

4. **[examples/osc_source_example.py](examples/osc_source_example.py)** (new file)
   - Created standalone example with 3 usage patterns
   - Includes test message sender

5. **[examples/example_config_new.yaml](examples/example_config_new.yaml)** (updated)
   - Added OSC source example to comprehensive config

## Features

### OSCSourceSettings

```python
@dataclass
class OSCSourceSettings:
    port: int                          # Required: UDP port to listen on
    address: str                       # Required: OSC address pattern (e.g., "/control/volume")
    ip: str = "0.0.0.0"               # Optional: IP to bind (default: all interfaces)
    value_index: Optional[int] = None  # Optional: Extract single value at index
```

### Functionality

- **Background Server**: Runs `BlockingOSCUDPServer` in daemon thread
- **Value Extraction**:
  - `value_index=0`: Extract first value from message
  - `value_index=None`: Return all values as list
- **Multiple Subscribers**: Supports multiple callback subscriptions
- **Graceful Shutdown**: `stop()` method cleanly shuts down server
- **Idempotent**: Calling `run()` multiple times safe

## Usage Examples

### Basic Example (Config)

```yaml
sources:
  volume_control:
    type: osc
    port: 8000
    address: "/control/volume"
    value_index: 0  # Extract first value
    target: "volume"

model:
  volume:
    default: 0.5
    effect:
      type: file_write
      path: /tmp/volume.txt
      template: "Volume: {{ volume }}"
```

### Basic Example (Python)

```python
from frame.action_observable import (
    Model, PropertyAction, ReplaceAction,
    OSCSource, OSCSourceSettings
)

# Create model
model = Model({'volume': 0.5})

# Create OSC source
osc = OSCSource(OSCSourceSettings(
    port=8000,
    address="/control/volume",
    value_index=0
))

# Connect
osc.subscribe(lambda value: model.emit(
    PropertyAction("volume", ReplaceAction(value))
))

# Start listening
osc.run()
```

### Send Test Message

```python
from pythonosc.udp_client import SimpleUDPClient

client = SimpleUDPClient("127.0.0.1", 8000)
client.send_message("/control/volume", [0.75])
```

## Test Coverage

All **104 tests pass**, including 10 new OSC-specific tests:

### OSCSource Tests (10 tests)

1. ✅ `test_osc_source_initialization` - Settings initialization
2. ✅ `test_osc_source_custom_ip` - Custom IP binding
3. ✅ `test_osc_source_with_value_index` - Value index setting
4. ✅ `test_osc_source_run_starts_server` - Server startup
5. ✅ `test_osc_source_receives_message_with_value_index` - Extract single value
6. ✅ `test_osc_source_receives_message_without_value_index` - Receive array
7. ✅ `test_osc_source_multiple_subscribers` - Multiple callbacks
8. ✅ `test_osc_source_stop_shuts_down_server` - Graceful shutdown
9. ✅ `test_osc_source_handles_missing_value_at_index` - Index out of range
10. ✅ `test_osc_source_run_idempotent` - Multiple run() calls safe

### Registry Tests (2 tests)

11. ✅ `test_make_source_osc_from_dict` - Create from config dict
12. ✅ `test_make_source_osc_with_all_settings` - All settings from dict

## Dependencies

- **pythonosc** - Already in project dependencies
- Used for both server (`BlockingOSCUDPServer`) and client (`SimpleUDPClient`)

## Integration

The OSCSource follows the same pattern as other sources:

1. **Settings Dataclass**: Type-safe configuration
2. **SourceBase Subclass**: Auto-registers with `sources` registry
3. **run() Method**: Starts the source (in this case, server)
4. **subscribe() Method**: Register callbacks for received data
5. **make_source() Support**: Can be created from config dict/YAML

## Common Use Cases

1. **Hardware Controllers**: MIDI controllers, faders, buttons
2. **Mobile Apps**: TouchOSC, Lemur control apps
3. **Creative Coding**: Processing, Max/MSP, Pure Data integration
4. **Multimedia**: Live video/audio parameter control
5. **Installations**: Interactive art installations

## Next Steps

The OSCSource is production-ready and fully tested. Potential future enhancements:

- OSC pattern matching (e.g., `/control/*`)
- Multiple address subscriptions per source
- OSC bundle support
- Type conversion hints (int, float, string)

## Example Files

- **[examples/osc_source_example.py](examples/osc_source_example.py)** - 3 standalone examples
- **[examples/example_config_new.yaml](examples/example_config_new.yaml)** - YAML config example

Run examples:
```bash
# Start OSC listener
uv run python examples/osc_source_example.py 1

# Send test messages (in another terminal)
uv run python examples/osc_source_example.py send
```

## Test Results

```bash
$ uv run pytest tests/test_action_observable.py::TestOSCSource -v
================================ 10 passed in 4.13s =================================

$ uv run pytest tests/ -v
================================ 104 passed in 4.21s ================================
```

## Conclusion

OSCSource provides a robust, well-tested way to integrate OSC control into the Frame2 reactive system. It follows established patterns, has comprehensive test coverage, and includes practical examples for immediate use.
