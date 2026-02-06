# Config System Simplification

## Summary

Simplified the configuration syntax by removing the `@` prefix requirement for all references. The system now uses plain string or list values to reference model fields and effects.

## Changes

### Before (with @ prefix)
```yaml
sources:
  my_source:
    target: "@field_name"  # @ prefix required

model:
  field_name:
    effect: "@logger"  # @ prefix required

effects:
  logger:
    source: "@field_name"  # @ prefix required
```

### After (simplified)
```yaml
sources:
  my_source:
    target: "field_name"  # Plain string

model:
  field_name:
    effect: "logger"  # Plain string

effects:
  logger:
    source: "field_name"  # Plain string
```

## New Features

### 1. Target Field (Sources)
- **String**: `target: "field"` - connects to single model field
- **List**: `target: ["field1", "field2"]` - connects to multiple fields
- **Cannot be object** - inline definitions only allowed in model section

```yaml
sources:
  multi_target:
    type: shell
    command: "date"
    target: ["timestamp", "last_update"]  # Updates both fields
```

### 2. Effect Field (Model)
- **String**: `effect: "logger"` - references named effect
- **Dict**: `effect: {type: "file_write", ...}` - inline definition

```yaml
model:
  value:
    effect: "shared_logger"  # References effects.shared_logger
```

### 3. Source Field (Effects)
- **String**: `source: "field"` - subscribes to single model field
- **List**: `source: ["field1", "field2"]` - subscribes to multiple fields
- **Cannot be object** - inline definitions only in model section

```yaml
effects:
  multi_source:
    type: file_write
    path: /tmp/log.txt
    template: "{{ field1 }}, {{ field2 }}"
    source: ["field1", "field2"]  # Triggered by either field
```

## Benefits

1. **Simpler syntax** - No special characters needed
2. **More intuitive** - Plain strings are clearly references
3. **More flexible** - List support for multiple targets/sources
4. **Type distinction** - String = reference, Dict = inline (clear without @)

## Files Updated

### Core Implementation
- ✅ `src/frame/config.py` - Parser updated to handle strings/lists without @
  - Sources can have `target` as string or list
  - Model `effect` can be string (reference) or dict (inline)
  - Effects `source` can be string or list

### Tests
- ✅ `tests/test_config.py` - All 17 tests updated and passing
  - Removed @ from all references
  - Tests verify string and list support

### Examples
- ✅ `examples/example_config_new.yaml` - Comprehensive YAML updated
  - All @ prefixes removed
  - Comments updated to reflect new syntax
  - Demonstrates string and list references

- ✅ `examples/load_yaml_example.py` - Loads updated YAML successfully

### Documentation
- ✅ `docs/config_system.md` - Complete documentation updated
  - All examples updated to new syntax
  - Connection rules clarified
  - String vs Dict distinction explained

## Validation

All tests pass:
```bash
$ uv run pytest tests/
92 passed in 0.17s
```

Config tests specifically:
```bash
$ uv run pytest tests/test_config.py -v
17 passed in 0.06s
```

YAML example loads successfully:
```bash
$ uv run python examples/load_yaml_example.py
✓ Loaded config from example_config_new.yaml
✓ 7 sources, 16 effects, 19 model fields
```

## Migration Guide

For existing configs, simply remove @ prefixes:

```bash
# Quick migration with sed
sed -i 's/target: "@/target: "/g' config.yaml
sed -i 's/effect: "@/effect: "/g' config.yaml
sed -i 's/source: "@/source: "/g' config.yaml
```

Or manually:
1. Sources: `target: "@field"` → `target: "field"`
2. Model: `effect: "@name"` → `effect: "name"`
3. Effects: `source: "@field"` → `source: "field"`

## Backward Compatibility

⚠️ **Breaking change** - Old configs with @ prefix will need to be updated. The @ prefix is no longer recognized or required.
