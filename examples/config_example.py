"""
Example demonstrating the configuration deserialization system.

Shows how to define complete reactive systems using YAML-style config dicts with:
- Inline sources and effects in model
- @ references for connections
- Three-section configs (sources, model, effects)
"""

from frame.config import load_config
from frame.action_observable import PropertyAction, ReplaceAction
import tempfile
import os

print("=== Configuration System Examples ===\n")

# Example 1: Minimal config - model with inline source and effect
print("Example 1: Minimal model-only config with inline definitions")
print("-" * 60)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

config = {
    "model": {
        "temperature": {
            "default": 20,
            "source": {
                "type": "shell",
                "command": "echo '25'"
            },
            "effect": {
                "type": "file_write",
                "path": temp_path,
                "template": "Temperature: {{ temperature }}°C\n"
            }
        }
    }
}

model = load_config(config)
print(f"Initial temperature: {model.state['temperature']}")

# Manually update (in real use, source.run() would update it)
model.emit(PropertyAction("temperature", ReplaceAction(25)))

with open(temp_path) as f:
    print(f"Effect output: {f.read().strip()}")

os.unlink(temp_path)
print()

# Example 2: Config with @ references
print("Example 2: Model with @ reference to named effect")
print("-" * 60)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    log_path = f.name

config = {
    "model": {
        "counter": {
            "default": 0,
            "effect": "@logger"  # Reference to effects section
        }
    },
    "effects": {
        "logger": {
            "type": "file_write",
            "path": log_path,
            "template": "Counter: {{ counter }}\n",
            "append": True
        }
    }
}

model = load_config(config)
print(f"Initial counter: {model.state['counter']}")

# Trigger multiple updates
for i in [1, 5, 10]:
    model.emit(PropertyAction("counter", ReplaceAction(i)))
    print(f"Updated counter to {i}")

print("\nLog file contents:")
with open(log_path) as f:
    print(f.read())

os.unlink(log_path)

# Example 3: Three-section config
print("Example 3: Complete config with sources, model, and effects sections")
print("-" * 60)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    output_path = f.name

config = {
    "sources": {
        "date_source": {
            "type": "shell",
            "command": "date",
            "target": "@timestamp"  # @ reference to model field
        }
    },
    "model": {
        "timestamp": {"default": None},
        "status": {"default": "idle"}
    },
    "effects": {
        "log_timestamp": {
            "type": "file_write",
            "path": output_path,
            "template": "Last update: {{ timestamp }}\n",
            "source": "@timestamp"  # Subscribe to timestamp changes
        }
    }
}

model = load_config(config)
print(f"Initial state: {model.state}")

# Manually trigger (in real use, source.run() would do this)
model.emit(PropertyAction("timestamp", ReplaceAction("2024-01-15 10:30:00")))

with open(output_path) as f:
    print(f"Effect output: {f.read().strip()}")

os.unlink(output_path)
print()

# Example 4: Multiple fields with different configurations
print("Example 4: Multiple model fields with various connection patterns")
print("-" * 60)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='_a.txt') as f:
    file_a = f.name
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='_b.txt') as f:
    file_b = f.name

config = {
    "model": {
        "value_a": {
            "default": 0,
            # Inline effect
            "effect": {
                "type": "file_write",
                "path": file_a,
                "template": "A: {{ value_a }}"
            }
        },
        "value_b": {
            "default": 0,
            # Reference to named effect
            "effect": "@shared_logger"
        }
    },
    "effects": {
        "shared_logger": {
            "type": "file_write",
            "path": file_b,
            "template": "B: {{ value_b }}"
        }
    }
}

model = load_config(config)
print(f"Initial state: {model.state}")

# Update both values
model.emit(PropertyAction("value_a", ReplaceAction(42)))
model.emit(PropertyAction("value_b", ReplaceAction(99)))

print("\nFile A (inline effect):")
with open(file_a) as f:
    print(f"  {f.read()}")

print("File B (referenced effect):")
with open(file_b) as f:
    print(f"  {f.read()}")

os.unlink(file_a)
os.unlink(file_b)

# Example 5: Simple values in model
print("\nExample 5: Model with simple (non-dict) values")
print("-" * 60)

config = {
    "model": {
        "counter": 0,
        "name": "MyApp",
        "enabled": True,
        "tags": ["prod", "v1.0"]
    }
}

model = load_config(config)
print(f"Model state: {model.state}")
print(f"  counter: {model.state['counter']}")
print(f"  name: {model.state['name']}")
print(f"  enabled: {model.state['enabled']}")
print(f"  tags: {model.state['tags']}")

print("\n=== Config system enables declarative reactive programming! ===")
