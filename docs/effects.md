# Effects System

The Effects system provides **outputs** for the reactive architecture - side effects that are triggered by observable state changes.

## Overview

**Effects** are the opposite of **Sources**:
- **Sources**: Inputs - produce data and notify subscribers
- **Effects**: Outputs - consume data and perform side effects

Effects work as **observables** (callables) that can subscribe to Model changes, Observer chains, or any other observable in the system.

## Core Concepts

### Effects are Callables

All effects implement `__call__(value: Any) -> None`:

```python
effect = FileWriteEffect(
    FileWriteEffectSettings(path="/tmp/log.txt", template="Value: {{ x }}")
)

# Call directly
effect({"x": 42})

# Or subscribe to model
model.subscribe(effect)
```

### Settings Dataclasses

Each effect has a typed settings dataclass:

```python
@dataclass
class FileWriteEffectSettings:
    path: str
    template: str
    append: bool = False
    renderer: Optional[str | Dict[str, Any]] = None
```

### Optional Renderer

Effects can have an optional `renderer` that processes input **before** the effect executes:

```python
effect = ShellEffect(
    ShellEffectSettings(
        command="echo {message}",
        renderer="string"  # Converts input to string
    )
)
```

Renderers typically:
- Convert structured objects to strings
- Transform strings to different formats
- Pre-process data before the effect uses it

## Available Effects

| Effect | Purpose | Settings |
|--------|---------|----------|
| `ShellEffect` | Execute shell commands | `command`, `sudo`, `renderer` |
| `FileWriteEffect` | Write files with Jinja2 templates | `path`, `template`, `append`, `renderer` |
| `OSCEffect` | Send OSC messages | `address`, `port`, `path`, `renderer` |
| `NotificationEffect` | Send notifications | `message`, `targets`, `renderer` |
| `SequenceEffect` | Execute multiple effects in order | `effects`, `renderer` |

## Usage Patterns

### 1. Direct Effect Execution

```python
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/output.txt",
        template="Message: {{ msg }}"
    )
)

effect({"msg": "Hello"})
```

### 2. Effect Triggered by Model

```python
model = Model({"temperature": 20})

effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/temp.txt",
        template="Temp: {{ temperature }}°C"
    )
)

model.subscribe(effect)
model.emit(PropertyAction("temperature", ReplaceAction(25)))
```

### 3. Effect with Observer Chain

```python
model = Model({"cpu": 10, "memory": 50})

effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/cpu.txt",
        template="CPU: {{ value }}%"
    )
)

# Extract CPU, filter changes, trigger effect
prop_obs = PropertyObserver("cpu")
changed_obs = ChangedObserver()

def wrap_effect(value):
    effect({"value": value})

prop_obs >> changed_obs
changed_obs.subscribe(wrap_effect)
model.subscribe(prop_obs)
```

### 4. Multiple Effects on Same Model

```python
model = Model({"status": "idle"})

# Effect 1: Log to file
log_effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/log.txt",
        template="[LOG] {{ status }}\n",
        append=True
    )
)

# Effect 2: Print to console
console_effect = ShellEffect(
    ShellEffectSettings(command='echo "Status: {{ status }}"')
)

# Both subscribe
model.subscribe(log_effect)
model.subscribe(console_effect)
```

### 5. Complete Reactive Pipeline

```python
# Source -> Model -> Effect
source = ShellSource(ShellSourceSettings(command="date"))
model = Model({"timestamp": ""})
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/log.txt",
        template="Time: {{ timestamp }}\n"
    )
)

# Connect pipeline
source.subscribe(lambda result: model.emit(
    PropertyAction("timestamp", ReplaceAction(result))
))
model.subscribe(effect)

# Run
source.run()
```

## Effect Registry

Effects use the same registry pattern as Sources:

### From Dict

```python
effect, _ = make_effect({
    "type": "file_write",
    "path": "/tmp/out.txt",
    "template": "Value: {{ x }}"
})
```

### From YAML

```yaml
effects:
  log_writer:
    type: file_write
    path: /var/log/app.log
    template: "{{ timestamp }}: {{ message }}"
    append: true

  notifier:
    type: notification
    message: "Alert: {{ alert_msg }}"
    targets:
      - type: console
```

```python
import yaml

with open('config.yaml') as f:
    config = yaml.safe_load(f)

effects = {
    name: make_effect(settings)[0]
    for name, settings in config['effects'].items()
}
```

## ShellEffect

Executes shell commands with optional templating:

```python
# Simple command
effect = ShellEffect(
    ShellEffectSettings(command="echo hello")
)

# With Jinja2 template
effect = ShellEffect(
    ShellEffectSettings(command='echo "{{ message }}"')
)
effect({"message": "Hello World"})

# List-style command (safer)
effect = ShellEffect(
    ShellEffectSettings(command=["echo", "hello"])
)

# With sudo
effect = ShellEffect(
    ShellEffectSettings(
        command="systemctl restart service",
        sudo=True
    )
)
```

## FileWriteEffect

Writes files using Jinja2 templates:

```python
# Basic write
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/output.txt",
        template="Value: {{ x }}"
    )
)
effect({"x": 42})

# Append mode
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/log.txt",
        template="{{ timestamp }}: {{ msg }}\n",
        append=True
    )
)

# Non-dict values use 'value' key
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/tmp/out.txt",
        template="Number: {{ value }}"
    )
)
effect(42)  # Renders as {"value": 42}
```

## SequenceEffect

Chains multiple effects to execute in order:

```python
effect = SequenceEffect(
    SequenceEffectSettings(
        effects=[
            {
                "type": "file_write",
                "path": "/tmp/data.txt",
                "template": "{{ data }}"
            },
            {
                "type": "shell",
                "command": "cat /tmp/data.txt"
            }
        ]
    )
)

effect({"data": "Hello"})
# 1. Writes "Hello" to file
# 2. Prints file contents
```

## Benefits

1. **Reactive**: Effects trigger automatically on state changes
2. **Composable**: Chain with observers for filtering, transformation
3. **Type-Safe**: Settings dataclasses provide validation
4. **YAML-Friendly**: Easy to configure from files
5. **Testable**: Effects are simple callables

## Architecture

```
┌─────────┐         ┌───────┐         ┌────────────┐         ┌────────┐
│ Source  │────────>│ Model │────────>│ Observer   │────────>│ Effect │
│ (Input) │         │ State │         │ (Filter)   │         │(Output)│
└─────────┘         └───────┘         └────────────┘         └────────┘
    ▲                   │                                          │
    │                   └──────────────────────────────────────────┘
    │                            Direct subscription
    │
  run()                        Effects = System Outputs
```

## Example: Complete System

```python
# Model
model = Model({"cpu": 0, "memory": 0, "alerts": []})

# Sources (inputs)
cpu_source = ShellSource(ShellSourceSettings(
    command="ps aux | head -1",
    parser="string"
))

# Connect source to model
cpu_source.subscribe(lambda result: model.emit(
    PropertyAction("cpu", ReplaceAction(parse_cpu(result)))
))

# Effects (outputs)
log_effect = FileWriteEffect(
    FileWriteEffectSettings(
        path="/var/log/monitor.log",
        template="{{ timestamp }}: CPU={{ cpu }}%\n",
        append=True
    )
)

alert_effect = NotificationEffect(
    NotificationEffectSettings(
        message="HIGH CPU: {{ cpu }}%",
        targets=[{"type": "console"}]
    )
)

# Observer chain with filtering
cpu_obs = PropertyObserver("cpu")
high_cpu = ChangedObserver()  # Only on change

# High CPU alert (>80%)
def check_high_cpu(value):
    if value > 80:
        alert_effect({"cpu": value})

cpu_obs >> high_cpu
high_cpu.subscribe(check_high_cpu)
model.subscribe(cpu_obs)

# Log all changes
model.subscribe(log_effect)

# Run
cpu_source.run()
```

## See Also

- [Source Registry](source_registry.md) - Inputs
- [Action Observable](../src/frame/action_observable.py) - Core system
- [Examples](../examples/effects_example.py) - Complete examples
