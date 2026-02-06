"""
Example demonstrating the Effects system.

Shows how Effects work as outputs in the reactive system:
- Effects are triggered by Model state changes
- Effects can be chained with Observers
- Multiple effects can react to the same state
- Effects are configured from dicts (YAML-friendly)
"""

from frame.action_observable import (
    Model, PropertyAction, ReplaceAction,
    PropertyObserver, ChangedObserver,
    ShellSource, ShellSourceSettings,
    FileWriteEffect, FileWriteEffectSettings,
    ShellEffect, ShellEffectSettings,
    SequenceEffect, SequenceEffectSettings,
    make_effect
)
import tempfile
import os

print("=== Effects Example ===\n")

# Example 1: Basic effect triggered by model
print("Example 1: Effect triggered by model state change")
print("-" * 50)

model = Model({"temperature": 20})

# Create a file to write to
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

# Create effect that writes temperature to file
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path=temp_path,
        template="Current temperature: {{ temperature }}°C\n"
    )
)

# Subscribe effect to model
model.subscribe(effect)

# Update temperature - triggers effect
model.emit(PropertyAction("temperature", ReplaceAction(25)))

# Check what was written
with open(temp_path) as f:
    print(f"File content: {f.read().strip()}")

os.unlink(temp_path)
print()

# Example 2: Effect with PropertyObserver lens
print("Example 2: Effect with PropertyObserver lens")
print("-" * 50)

model = Model({"cpu": 10, "memory": 50, "disk": 80})

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

# Effect that only cares about CPU
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path=temp_path,
        template="CPU: {{ value }}%\n"
    )
)

# PropertyObserver extracts just CPU value
cpu_observer = PropertyObserver("cpu")

# Wrap effect to convert single value to dict
def wrap_for_effect(value):
    effect({"value": value})

cpu_observer.subscribe(wrap_for_effect)
model.subscribe(cpu_observer)

# Update CPU - triggers effect
model.emit(PropertyAction("cpu", ReplaceAction(75)))

with open(temp_path) as f:
    print(f"File content: {f.read().strip()}")

os.unlink(temp_path)
print()

# Example 3: Multiple effects on same model
print("Example 3: Multiple effects on same state change")
print("-" * 50)

model = Model({"status": "idle"})

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    log_path = f.name

# Effect 1: Write to file
file_effect = FileWriteEffect(
    FileWriteEffectSettings(
        path=log_path,
        template="[LOG] Status changed to: {{ status }}\n",
        append=True
    )
)

# Effect 2: Print to console (using shell echo)
console_effect = ShellEffect(
    ShellEffectSettings(
        command='echo "Status: {{ status }}"'
    )
)

# Both subscribe to model
model.subscribe(file_effect)
model.subscribe(console_effect)

# Update status - triggers both effects
print("Updating status to 'active'...")
model.emit(PropertyAction("status", ReplaceAction("active")))

print("Updating status to 'busy'...")
model.emit(PropertyAction("status", ReplaceAction("busy")))

print("\nLog file contents:")
with open(log_path) as f:
    print(f.read())

os.unlink(log_path)

# Example 4: Effect with ChangedObserver (debouncing)
print("Example 4: Effect with ChangedObserver (only on change)")
print("-" * 50)

model = Model({"counter": 0})

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

effect = FileWriteEffect(
    FileWriteEffectSettings(
        path=temp_path,
        template="Counter: {{ value }}\n",
        append=True
    )
)

# Chain: PropertyObserver -> ChangedObserver -> Effect
prop_obs = PropertyObserver("counter")
changed_obs = ChangedObserver()

def wrap_effect(value):
    effect({"value": value})

prop_obs >> changed_obs
changed_obs.subscribe(wrap_effect)
model.subscribe(prop_obs)

# Multiple updates
print("Emitting: 5, 5, 5, 10, 10, 15")
model.emit(PropertyAction("counter", ReplaceAction(5)))
model.emit(PropertyAction("counter", ReplaceAction(5)))  # Duplicate - filtered
model.emit(PropertyAction("counter", ReplaceAction(5)))  # Duplicate - filtered
model.emit(PropertyAction("counter", ReplaceAction(10)))
model.emit(PropertyAction("counter", ReplaceAction(10)))  # Duplicate - filtered
model.emit(PropertyAction("counter", ReplaceAction(15)))

print("\nFile shows only unique values:")
with open(temp_path) as f:
    print(f.read())

os.unlink(temp_path)

# Example 5: SequenceEffect (multiple effects in order)
print("Example 5: SequenceEffect (chain multiple effects)")
print("-" * 50)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

# Sequence: write to file, then display it
sequence = SequenceEffect(
    SequenceEffectSettings(
        effects=[
            {
                "type": "file_write",
                "path": temp_path,
                "template": "Message: {{ msg }}\n"
            },
            {
                "type": "shell",
                "command": f"cat {temp_path}"
            }
        ]
    )
)

print("Executing sequence effect:")
sequence({"msg": "Hello from SequenceEffect!"})

os.unlink(temp_path)
print()

# Example 6: Effects from dict config (YAML-friendly)
print("Example 6: Creating effects from dict config")
print("-" * 50)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    temp_path = f.name

# This dict could come from YAML
effect_config = {
    "type": "file_write",
    "path": temp_path,
    "template": "Config-based effect: {{ data }}"
}

effect, _ = make_effect(effect_config)
effect({"data": "Works!"})

with open(temp_path) as f:
    print(f"File content: {f.read()}")

os.unlink(temp_path)
print()

# Example 7: Complete reactive pipeline
print("Example 7: Complete reactive pipeline (Source -> Model -> Effect)")
print("-" * 50)

with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
    log_path = f.name

# Create model
model = Model({"command_output": ""})

# Create source (shell command)
source = ShellSource(ShellSourceSettings(command="date"))

# Connect source to model
source.subscribe(lambda result: model.emit(
    PropertyAction("command_output", ReplaceAction(result))
))

# Create effect that logs to file
effect = FileWriteEffect(
    FileWriteEffectSettings(
        path=log_path,
        template="Command executed at: {{ command_output }}\n"
    )
)

# Connect model to effect
model.subscribe(effect)

# Run the pipeline
print("Running: date command -> model -> file effect")
source.run()

with open(log_path) as f:
    print(f"Log content: {f.read()}")

os.unlink(log_path)

print("\n=== Effects work as outputs in the reactive system! ===")
