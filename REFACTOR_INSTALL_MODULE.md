# Install Module Refactoring + Defaults Type

## Summary

Refactored the install system into a clean module structure and added the `defaults` type for macOS system preferences.

## Changes

### 1. Code Organization

**Before:** All install code in `src/frame/cli.py` (~250 lines)

**After:** Clean module structure:
```
src/frame/install/
├── __init__.py          # Module exports
├── installer.py         # Main install logic
└── generators.py        # Ansible playbook generators
```

**Benefits:**
- Separation of concerns
- Easier to maintain and extend
- Clean CLI file (only 51 lines now)

### 2. Static vs Generated Files

**Key architectural change:**
- **site.yml** - Now static/canonical (not generated)
- **plan.yml** - Generated from state.yaml (contains actual steps)

This follows the plan document's architecture where site.yml is generic and plan.yml contains the installation plan.

### 3. New `defaults` Type ✅

Added handler for macOS system preferences using `community.general.osx_defaults`.

**State file format:**
```yaml
- type: defaults
  items:
    - domain: com.apple.Safari
      key: IncludeInternalDebugMenu
      type: bool
      value: true

    - domain: NSGlobalDomain
      key: AppleShowAllExtensions
      type: bool
      value: true
```

**Features:**
- Pure Ansible implementation (no Python code needed)
- Iterates over items list
- Supports all osx_defaults parameters (domain, key, type, value, state)
- Proper error handling and reporting

**Technical details:**
- Uses `step['items']` bracket notation to avoid collision with dict.items() method
- Leverages existing community.general collection
- Loop control with labeled output for readability

## Files

### Created
- [src/frame/install/__init__.py](src/frame/install/__init__.py) - Module exports
- [src/frame/install/installer.py](src/frame/install/installer.py) - Main installation logic
- [src/frame/install/generators.py](src/frame/install/generators.py) - Playbook generators
- [examples/state_with_defaults.yaml](examples/state_with_defaults.yaml) - Example with both types

### Modified
- [src/frame/cli.py](src/frame/cli.py) - Simplified to import from install module

### Structure

**generators.py** includes:
- `get_static_site_yml()` - Returns canonical site.yml (loads plan.yml)
- `generate_plan_yml()` - Converts state entries to plan.yml
- `generate_ansible_cfg()` - Ansible config
- `generate_inventory()` - Localhost inventory
- `generate_install_app_handler()` - install_app type handler
- `generate_defaults_handler()` - defaults type handler (NEW)
- `HANDLER_GENERATORS` - Registry mapping type → generator function
- `get_handler_generator()` - Registry lookup

**installer.py** includes:
- `validate_state_entries()` - Validates state file with type-specific checks
- `get_required_handlers()` - Extracts unique types needed
- `format_summary_line()` - Formats output for each type
- `install()` - Main installer function

## Testing

### Test 1: install_app only
```bash
uv run frame install /tmp/test_frame_install/state_test.yaml
# ✅ Installed TestApp.app → /tmp/test_frame_install/installed
```

### Test 2: defaults only
```bash
uv run frame install /tmp/test_frame_install/state_defaults_test.yaml
# ✅ Applied 1 macOS defaults setting(s)
```

### Test 3: Both types
```bash
uv run frame install examples/state_with_defaults.yaml
# ✅ Applied 3 macOS defaults setting(s)
# ✅ Installed TestApp.app → /tmp/test_frame_install/installed
```

All tests pass! ✅

## Handler Registry Pattern

The refactored code uses a registry pattern for handlers:

```python
HANDLER_GENERATORS = {
    "install_app": generate_install_app_handler,
    "defaults": generate_defaults_handler,
}
```

**Benefits:**
1. Easy to add new types (just add to registry)
2. Only generates handlers actually needed
3. Clear error message for unknown types
4. Extensible for future handler types

## Next Steps

Ready to add more handlers:
- `pkg_install` - brew/apt/yum packages
- `dmg_install` - Mount and install from DMG
- `user_service` - launchd/systemd services
- `copy_file` - Copy individual files
- `run_command` - Execute arbitrary commands

All follow the same pattern:
1. Add generator function to `generators.py`
2. Register in `HANDLER_GENERATORS`
3. Add validation in `validate_state_entries()`
4. Add summary format in `format_summary_line()`
