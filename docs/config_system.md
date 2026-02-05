# Configuration System

The Configuration System provides declarative YAML/dict-based setup for complete reactive systems.

## Overview

Define your entire reactive architecture in a single config with three sections:
- **sources**: Data producers (inputs)
- **model**: State dictionary (reactive store)
- **effects**: Side effects (outputs)

## Quick Example

```python
from frame.config import load_config

config = {
    "model": {
        "temperature": {
            "default": 20,
            "source": {"type": "shell", "command": "sensors"},
            "effect": {"type": "file_write", "path": "/tmp/temp.txt", "template": "{{ temperature }}"}
        }
    }
}

model = load_config(config)
```

## Config Structure

### Model Section

The model section defines your reactive state:

```yaml
model:
  field_name:
    default: initial_value
    source: ...        # Optional inline source
    effect: ...        # Optional inline effect or @reference
```

**Simple values:**
```python
model:
  counter: 0
  name: "MyApp"
  enabled: True
```

**With type/default:**
```python
model:
  temperature:
    default: 20
```

**With inline source:**
```python
model:
  timestamp:
    default: None
    source:
      type: shell
      command: date
```

**With inline effect:**
```python
model:
  counter:
    default: 0
    effect:
      type: file_write
      path: /tmp/log.txt
      template: "Count: {{ counter }}"
```

**With string reference to named effect:**
```python
model:
  value:
    default: 0
    effect: "logger"  # References effects.logger
```

### Sources Section

The sources section defines data producers:

```yaml
sources:
  source_name:
    type: shell
    command: date
    target: field_name  # String or list of model field names
```

**Target options:**
- String `"field_name"`: Connects to single model field
- List `["field1", "field2"]`: Connects to multiple model fields
- Cannot be an object (inline definitions only allowed in model section)

**Example:**
```python
sources:
  date_source:
    type: shell
    command: date
    target: "timestamp"  # Connects to model.timestamp
```

### Effects Section

The effects section defines side effects:

```yaml
effects:
  effect_name:
    type: file_write
    path: /tmp/log.txt
    template: "{{ value }}"
    source: "field_name"  # Subscribe to model field changes
```

**Source option:**
- String `"field_name"`: Subscribes to single model field changes
- List `["field1", "field2"]`: Subscribes to multiple model fields
- **Cannot** contain inline source objects (use model inline source instead)

**Example:**
```python
effects:
  logger:
    type: file_write
    path: /tmp/log.txt
    template: "Status: {{ status }}"
    source: "status"  # Subscribes to model.status changes
```

## Connection Rules

### String References

Use plain strings to reference items across sections (no @ prefix needed):

```python
config = {
    "sources": {
        "my_source": {
            "type": "shell",
            "command": "date",
            "target": "timestamp"  # → model.timestamp
        }
    },
    "model": {
        "timestamp": {
            "default": None,
            "effect": "logger"  # → effects.logger
        }
    },
    "effects": {
        "logger": {
            "type": "file_write",
            "path": "/tmp/log.txt",
            "template": "{{ timestamp }}",
            "source": "timestamp"  # ← model.timestamp
        }
    }
}
```

### Inline Definitions

Simplify configs with inline sources/effects in model:

```python
config = {
    "model": {
        "temperature": {
            "source": {"type": "shell", "command": "sensors"},  # Inline source
            "effect": {"type": "file_write", ...}                # Inline effect
        }
    }
}
```

Inline definitions are automatically added to catalogs as:
- `fieldName(source)` for inline sources
- `fieldName(effect)` for inline effects

### Conflict Rules

These combinations are **errors**:

❌ Inline source with `target` field:
```python
model:
  value:
    source:
      type: shell
      command: date
      target: other_field  # ERROR: conflicts with value being implicit target
```

❌ Inline effect with `source` field:
```python
model:
  value:
    effect:
      type: shell
      command: echo
      source: "other"  # ERROR: conflicts with value being implicit source
```

❌ Effect with inline source object:
```python
effects:
  my_effect:
    type: shell
    command: echo
    source: {"type": "shell", ...}  # ERROR: effects section can't contain objects
```

## Usage Patterns

### Pattern 1: Minimal Model-Only Config

Perfect for simple reactive state:

```python
config = {
    "model": {
        "counter": {
            "default": 0,
            "effect": {
                "type": "file_write",
                "path": "/tmp/count.txt",
                "template": "{{ counter }}"
            }
        }
    }
}

model = load_config(config)
model.emit(PropertyAction("counter", ReplaceAction(42)))
```

### Pattern 2: Complete Three-Section Config

For complex systems:

```python
config = {
    "sources": {
        "sensor": {
            "type": "shell",
            "command": "sensors",
            "target": "temperature"
        }
    },
    "model": {
        "temperature": {"default": 0},
        "alerts": {"default": []}
    },
    "effects": {
        "logger": {
            "type": "file_write",
            "path": "/var/log/temp.log",
            "template": "{{ temperature }}°C\n",
            "append": True,
            "source": "temperature"
        }
    }
}

model = load_config(config)
# source.run() would trigger the pipeline
```

### Pattern 3: Mixed Inline and References

Combine approaches for clarity:

```python
config = {
    "model": {
        "cpu": {
            "source": {"type": "shell", "command": "top -l 1"},  # Inline
            "effect": "cpu_logger"  # Reference
        },
        "memory": {
            "source": {"type": "shell", "command": "vm_stat"},  # Inline
            "effect": "mem_logger"  # Reference
        }
    },
    "effects": {
        "cpu_logger": {
            "type": "file_write",
            "path": "/tmp/cpu.log",
            "template": "CPU: {{ cpu }}"
        },
        "mem_logger": {
            "type": "file_write",
            "path": "/tmp/mem.log",
            "template": "MEM: {{ memory }}"
        }
    }
}

model = load_config(config)
```

## API Reference

### `load_config(config: Dict[str, Any]) -> Model`

Load reactive system from config dict.

**Args:**
- `config`: Dict with 'sources', 'model', and/or 'effects' sections

**Returns:**
- Configured `Model` instance with all connections set up

**Example:**
```python
from frame.config import load_config

config = {"model": {"value": 0}}
model = load_config(config)
```

### `ReactiveConfig(config: Dict[str, Any])`

Configuration parser and builder.

**Attributes:**
- `sources_catalog`: Dict of source name → source instance
- `effects_catalog`: Dict of effect name → effect instance
- `model_state`: Initial model state dict
- `model`: The created Model instance

**Methods:**
- `build() -> Model`: Build and connect the reactive system

**Example:**
```python
from frame.config import ReactiveConfig

config = {"model": {"value": 0}}
reactive_config = ReactiveConfig(config)
model = reactive_config.build()

# Access catalogs
print(reactive_config.sources_catalog)
print(reactive_config.effects_catalog)
```

### `ConfigError`

Exception raised for invalid configurations.

**Common errors:**
- Missing model field for source target
- Missing effect for string reference
- Inline source with conflicting target
- Inline effect with conflicting source
- Effect with inline source object

## YAML Integration

Works seamlessly with YAML configs:

```yaml
# config.yaml
sources:
  timer:
    type: shell
    command: date
    target: "timestamp"

model:
  timestamp:
    default: null

effects:
  logger:
    type: file_write
    path: /tmp/log.txt
    template: "{{ timestamp }}\n"
    append: true
    source: "timestamp"
```

```python
import yaml
from frame.config import load_config

with open('config.yaml') as f:
    config = yaml.safe_load(f)

model = load_config(config)
```

## Benefits

1. **Declarative**: Define what you want, not how to wire it
2. **Concise**: Inline definitions reduce boilerplate
3. **Type-Safe**: Uses existing registry systems with validation
4. **Flexible**: Mix inline and references as needed
5. **Clear**: string references make connections explicit
6. **YAML-Friendly**: Perfect for configuration files

## See Also

- [Source Registry](source_registry.md) - Available source types
- [Effects](effects.md) - Available effect types
- [Examples](../examples/config_example.py) - Complete examples
