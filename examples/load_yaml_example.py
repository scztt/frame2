"""
Load and demonstrate the comprehensive YAML config example.

This script loads example_config_new.yaml and demonstrates:
- Config parsing from YAML
- Model state initialization
- Source/effect catalog creation
- Triggering state changes manually
"""

import yaml
from pathlib import Path
from frame.config import ReactiveConfig
from frame.action_observable import PropertyAction, ReplaceAction

print("=" * 80)
print("Loading Comprehensive YAML Configuration")
print("=" * 80)

# Load YAML config
yaml_path = Path(__file__).parent / "example_config_new.yaml"
with open(yaml_path) as f:
    config = yaml.safe_load(f)

print(f"\n✓ Loaded config from {yaml_path.name}")

# Build reactive system
print("\nBuilding reactive system...")
reactive_config = ReactiveConfig(config)
model = reactive_config.build()

print("\n" + "=" * 80)
print("Configuration Analysis")
print("=" * 80)

# Show catalogs
print(f"\n📦 Sources Catalog ({len(reactive_config.sources_catalog)} sources):")
for name in reactive_config.sources_catalog.keys():
    print(f"  • {name}")

print(f"\n📦 Effects Catalog ({len(reactive_config.effects_catalog)} effects):")
for name in reactive_config.effects_catalog.keys():
    print(f"  • {name}")

# Show model state
print(f"\n📦 Model State ({len(model.state)} fields):")
for key, value in model.state.items():
    value_repr = repr(value)
    if len(value_repr) > 50:
        value_repr = value_repr[:47] + "..."
    print(f"  • {key}: {value_repr}")

print("\n" + "=" * 80)
print("Configuration Features Demonstrated")
print("=" * 80)

# Count different features
simple_values = sum(1 for v in model.state.values() if not isinstance(v, dict))
inline_sources = len([k for k in reactive_config.sources_catalog.keys() if "(source)" in k])
inline_effects = len([k for k in reactive_config.effects_catalog.keys() if "(effect)" in k])
named_sources = len(reactive_config.sources_catalog) - inline_sources
named_effects = len(reactive_config.effects_catalog) - inline_effects

print("\n✨ Features Used:")
print(f"  • Simple model values: {simple_values}")
print(f"  • Inline sources: {inline_sources}")
print(f"  • Named sources: {named_sources}")
print(f"  • Inline effects: {inline_effects}")
print(f"  • Named effects: {named_effects}")

print("\n" + "=" * 80)
print("Testing State Updates")
print("=" * 80)

# Manually trigger some state changes to show effects work
print("\n🔄 Updating model.error_count from 0 to 5...")
model.emit(PropertyAction("error_count", ReplaceAction(5)))
print("   ✓ Effect triggered (check output above)")

print("\n🔄 Updating model.temperature from 20.5 to 25.3...")
model.emit(PropertyAction("temperature", ReplaceAction(25.3)))
print("   ✓ Effect triggered (check output above)")

print("\n🔄 Updating model.memory_status from 'normal' to 'warning'...")
model.emit(PropertyAction("memory_status", ReplaceAction("warning")))
print("   ✓ Effect triggered (check /tmp/memory.log)")

print("\n" + "=" * 80)
print("Summary")
print("=" * 80)

print(
    """
✅ Successfully loaded comprehensive YAML config with:

1. Three Sections:
   - sources: External data sources
   - model: Reactive state dictionary
   - effects: Side effect handlers

2. Connection Patterns:
   - @ references: Link components across sections
   - Inline definitions: Define sources/effects within model
   - Plain targets: Auto-create model fields from sources

3. Features Demonstrated:
   - Shell sources (string and list commands)
   - Tail sources (log file monitoring)
   - Screenshot sources (screen capture)
   - File write effects (with templates)
   - Shell effects (command execution)
   - Sequence effects (multi-stage pipelines)
   - Notification effects (user alerts)
   - OSC effects (network messaging)
   - Format renderers (Python .format())
   - Template renderers (Jinja2 templates)

4. Data Types:
   - Simple values (strings, numbers, booleans, lists)
   - Complex nested structures (dicts)
   - Null/default values

The config system enables fully declarative reactive programming!
"""
)

print("\n" + "=" * 80)
print("Next Steps")
print("=" * 80)

print(
    """
To see the full reactive system in action:

1. Run sources to populate model:
   reactive_config.sources_catalog['cpu_monitor'].run()

2. Manually update model fields:
   model.emit(PropertyAction('field_name', ReplaceAction(new_value)))

3. Effects automatically trigger on state changes!

Check /tmp/ for generated log files and outputs.
"""
)
