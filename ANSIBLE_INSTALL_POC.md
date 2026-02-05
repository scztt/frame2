# Ansible-Based State Management - Proof of Concept

## Overview

Implemented a working proof-of-concept for the `frame install` command that uses Ansible to manage application installations based on a declarative YAML state file.

## Implementation Summary

### Files Modified

1. **[pyproject.toml](pyproject.toml)** - Added dependencies:
   - `ansible-runner>=2.4.0` - Python interface to Ansible
   - `pyyaml>=6.0.2` - YAML parsing
   - Added CLI entry point: `frame = "frame.cli:app_cli"`

2. **[src/frame/cli.py](src/frame/cli.py)** - Implemented complete install system:
   - `install` command with typer CLI
   - Ansible playbook generation (site.yml, types/*.yml)
   - Smart sudo detection based on target path
   - Status reporting and error handling

3. **[examples/state_example.yaml](examples/state_example.yaml)** - Example configuration

### Features Implemented

#### CLI Command

```bash
frame install <state_file> [--verbose] [--sudo]
```

**Options:**
- `--verbose, -v` - Show detailed ansible output
- `--sudo` - Reserved for future use (currently auto-detected)

#### State File Format

```yaml
- type: install_app
  path: SuperCollider.app              # Required: path to .app bundle
  install_location: /Applications      # Optional: defaults to /Applications
```

#### Smart Sudo Detection

The handler automatically determines if sudo is needed based on target path:
- **Requires sudo**: `/Applications`, `/Library`, `/usr`, `/opt`
- **No sudo**: `/tmp`, `~/`, user directories

This allows testing without sudo while still supporting system-wide installs.

#### Type Handler: install_app

Located in generated `types/install_app.yml`, this handler:
1. Resolves source path and target location
2. Extracts app name from path
3. Checks if target requires sudo privileges
4. Creates target directory (with/without sudo as needed)
5. Removes existing app if present
6. Copies .app bundle using ansible's `copy` module
7. Removes macOS quarantine attribute (if on Darwin)
8. Reports successful installation

**Key Implementation Detail:**
Uses `dest: "{{ target_location }}"` (without app name) so ansible's copy module automatically creates the app subdirectory with correct structure.

## Architecture

### Execution Flow

```
state.yaml
    ↓
frame install command
    ↓
Generate ansible playbooks (tmpdir)
    ├── site.yml (main dispatcher)
    ├── ansible.cfg (local config)
    ├── inventory.ini (localhost)
    └── types/
        └── install_app.yml (handler)
    ↓
Execute via ansible-runner
    ↓
Report status & summary
```

### Generated Playbook Structure

**site.yml** - Main playbook that loops over steps and includes type handlers:
```yaml
- name: Frame Installation
  hosts: localhost
  tasks:
    - include_tasks: "types/{{ item.type }}.yml"
      loop: "{{ steps }}"
```

**types/install_app.yml** - Conditional tasks based on sudo requirements:
- Separate tasks for sudo/non-sudo operations
- Smart path-based detection
- Idempotent (removes existing before copy)

## Testing

### Test 1: Single App Install

```bash
# Create test state
cat > /tmp/test_state.yaml <<EOF
- type: install_app
  path: /path/to/MyApp.app
  install_location: /tmp/test_install
EOF

# Run install
frame install /tmp/test_state.yaml

# Result:
# ✅ Installation completed successfully!
# Summary:
#   1. Installed MyApp.app → /tmp/test_install
```

### Test 2: Multiple Apps

```bash
# State with multiple apps
- type: install_app
  path: TestApp.app
  install_location: /tmp/apps

- type: install_app
  path: AnotherApp.app
  install_location: /tmp/apps

# Both apps installed successfully in sequence
```

### Test 3: Verbose Output

```bash
frame install state.yaml --verbose

# Shows full ansible playbook execution:
# - Task-by-task execution
# - Fact gathering
# - Variable resolution
# - Task results (changed/ok/skipped)
# - Play recap
```

## Status

✅ **Phase 1 Complete** - Core Execution
- Generic site.yml dispatcher
- Step loop execution
- Handler include mechanism
- Bundle-relative path handling

✅ **install_app Handler Complete**
- Copies .app bundles
- Smart sudo detection
- macOS quarantine removal
- Error handling

## Next Steps

From [plan-ansible_for_state_management.md](plan-ansible_for_state_management.md):

### Additional Type Handlers
- `pkg_install` - Install via brew/apt/yum
- `dmg_install` - Mount DMG and install contents
- `user_service` - Install launchd/systemd services
- `copy_file` - Copy individual files
- `run_command` - Execute arbitrary commands
- `defaults_write` - macOS defaults system

### Packaging Commands
- `frame package` - Vendor dependencies and create offline bundle
- `frame hydrate` - Download artifacts for bundle

### Platform Support
- Linux systemd service handler
- Cross-platform detection and dispatch
- Windows support (future)

## Dependencies

**Runtime:**
- Python 3.13+
- ansible-core (installed separately via brew/pip)
- ansible-runner (installed via uv/pip)

**Python Packages:**
- typer - CLI framework
- pyyaml - YAML parsing
- ansible-runner - Ansible Python API

## Design Principles Followed

✅ Config stays simple (plain YAML list)
✅ Ansible remains debuggable (generated playbooks in tmpdir)
✅ Platform differences abstracted (smart sudo detection)
✅ Offline installs supported (all files self-contained in tmpdir)

## Usage Example

```bash
# Install dependencies
uv sync

# Create state file
cat > my_installation.yaml <<EOF
- type: install_app
  path: ./SuperCollider.app
  install_location: /Applications
EOF

# Run installation
uv run frame install my_installation.yaml

# With verbose output
uv run frame install my_installation.yaml --verbose
```

## Notes

- Uses temporary directory for ansible playbooks (cleaned up automatically)
- All paths can be relative or absolute
- Idempotent - can run multiple times safely
- Status reporting via typer's echo functions
- Error handling with exit codes

## Files

- Implementation: [src/frame/cli.py](src/frame/cli.py)
- Dependencies: [pyproject.toml](pyproject.toml)
- Example: [examples/state_example.yaml](examples/state_example.yaml)
- Plan: [plan-ansible_for_state_management.md](plan-ansible_for_state_management.md)
