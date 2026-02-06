# Source Registry System

The source registry system allows you to create source instances from dictionary/JSON/YAML configurations, similar to how `values.py` works with `TypeRegistry`.

## Overview

- **Registry**: `sources = TypeRegistry[SourceBase]("source")`
- **Factory function**: `make_source(config: Dict | str) -> (source, settings)`
- **Auto-registration**: Sources register themselves via `__init_subclass__`

## How It Works

### 1. SourceBase Class

All sources inherit from `SourceBase` with `name` and `settings` parameters:

```python
class ShellSource(SourceBase, name="shell", settings=ShellSourceSettings):
    def __init__(self, settings: ShellSourceSettings):
        # Initialize from settings dataclass
        ...
```

The `__init_subclass__` method automatically:
- Registers the class in the registry under the given name
- Sets the `settings_type` class attribute for dataclass construction

### 2. TypeRegistry Enhancement

Updated `TypeRegistry.make()` to support settings dataclasses:

```python
# Check if class has a settings_type attribute (for dataclass settings)
if hasattr(cls, 'settings_type'):
    settings_type = cls.settings_type
    # Remove 'type' key before constructing settings dataclass
    settings_dict = {k: v for k, v in settings.items() if k != 'type'}
    settings_obj = settings_type(**settings_dict)
    return cls(settings_obj), settings
```

If a class provides `settings_type`, the registry:
1. Constructs the settings dataclass from the dict
2. Passes the settings object to the class constructor

Otherwise, it falls back to passing the dict directly (backward compatible).

### 3. Usage Patterns

#### From Dict

```python
from frame.action_observable import make_source

# Create ShellSource from dict
source, _ = make_source({
    "type": "shell",
    "command": "date",
    "parser": "json"
})
result = source.run()
```

#### From String (with defaults)

```python
# Simple type name (uses defaults)
source, _ = make_source("screenshot")
```

#### From YAML Config

```yaml
sources:
  cpu_monitor:
    type: shell
    command: ps aux | head -1
    parser: string

  log_tail:
    type: tail
    path: /var/log/app.log
    lines: 100

  screen_capture:
    type: screenshot
    x: 0
    y: 0
    width: 1920
    height: 1080
```

```python
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

sources = {
    name: make_source(settings)[0]
    for name, settings in config['sources'].items()
}
```

## Registered Sources

| Type | Settings Class | Required Fields | Optional Fields |
|------|---------------|-----------------|-----------------|
| `shell` | `ShellSourceSettings` | `command` (str or list) | `parser`, `sudo` |
| `tail` | `TailSourceSettings` | `path` | `lines` (default: 100) |
| `screenshot` | `ScreenshotSourceSettings` | - | `x`, `y`, `width`, `height`, `sudo`, `id` |

### ShellSource Command Formats

ShellSource accepts commands in two formats:

**String format** (shell mode):
```python
{"type": "shell", "command": "echo hello && date"}
```

**List format** (exec mode - safer for untrusted input):
```python
{"type": "shell", "command": ["echo", "hello"]}
```

Both formats support the `sudo` option and use `run_command` from `frame.shell` for proper async execution and sudo password handling.

## Benefits

1. **Easy Configuration**: Create sources from JSON/YAML files
2. **Type Safety**: Settings dataclasses provide validation
3. **Extensibility**: New sources auto-register on definition
4. **Backward Compatible**: Works with both dataclasses and dict-based settings

## Example

See [examples/source_registry_example.py](../examples/source_registry_example.py) for complete working examples.

## Tests

All registry functionality is tested in `tests/test_action_observable.py::TestSourceRegistry` (6 tests, all passing).
