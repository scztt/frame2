# Frame Handler Templates

This directory contains Ansible playbook templates for Frame installation handlers.

## Overview

Each `.yml` file in this directory defines a handler type that can be used in Frame state files. Handlers are Ansible task lists that execute when their type is referenced in a state.yaml file.

## Available Handlers

- **install_app.yml** - Copy .app bundles to target location
- **defaults.yml** - Configure macOS system preferences
- **homebrew.yml** - Install packages via Homebrew
- **launchctl.yml** - Manage user launchd services

## Handler Structure

Each handler receives a `step` variable containing the entry from the state file:

```yaml
---
- name: "Handler description"
  block:
    - name: Task 1
      ansible.module:
        param: "{{ step.field_name }}"

    - name: Task 2
      another.module:
        param: "{{ step.another_field }}"

    - name: Report completion
      debug:
        msg: "Handler completed successfully"
```

### Available Variables

- `step` - The current state entry (dict with type and parameters)
- `plan.steps` - All state entries (available in site.yml context)
- `ansible_env` - Ansible environment variables
- `ansible_os_family` - OS family (Darwin, Debian, RedHat, etc.)

## Creating a New Handler

### 1. Create Handler File

Create a new `.yml` file in this directory with your handler name:

```bash
src/frame/install/templates/handlers/my_handler.yml
```

### 2. Define Handler Tasks

Write your Ansible tasks using the `step` variable:

```yaml
---
# Handler for my_handler type
# Description of what this handler does

- name: "My handler: {{ step.name }}"
  block:
    - name: Validate parameters
      assert:
        that:
          - step.required_field is defined
        fail_msg: "my_handler requires 'required_field' parameter"

    - name: Execute main task
      command: "do-something {{ step.required_field }}"

    - name: Report result
      debug:
        msg: "Completed my_handler for {{ step.name }}"
```

### 3. Register Handler (Optional)

For dynamic loading, add to `generators.py`:

```python
def generate_my_handler() -> str:
    """Load the my_handler template."""
    return load_handler("my_handler")

HANDLER_GENERATORS["my_handler"] = generate_my_handler
```

Or use dynamic registration:

```python
from frame.install.generators import register_handler_from_file

register_handler_from_file("my_handler")
```

### 4. Add Validation (Optional)

Add validation in `installer.py`:

```python
elif entry_type == 'my_handler':
    if 'required_field' not in entry:
        typer.echo(f"❌ Error: Entry {i} (my_handler) missing 'required_field'", err=True)
        raise typer.Exit(1)
```

### 5. Add Summary Formatting (Optional)

Add summary formatting in `installer.py`:

```python
elif entry_type == 'my_handler':
    return f"  {index}. My handler completed for {entry.get('name')}"
```

## State File Usage

Once created, handlers can be used in state files:

```yaml
# state.yaml
- type: my_handler
  required_field: "value"
  optional_field: "another value"
```

## Best Practices

### 1. Use Blocks for Organization

```yaml
- name: "Handler name"
  block:
    - name: Task 1
      ...
    - name: Task 2
      ...
```

### 2. Validate Required Parameters

```yaml
- name: Validate parameters
  assert:
    that:
      - step.required_field is defined
    fail_msg: "Missing required_field"
```

### 3. Provide Defaults

```yaml
- name: Set defaults
  set_fact:
    install_location: "{{ step.location | default('/usr/local') }}"
```

### 4. Use Conditional Execution

```yaml
- name: Task
  command: "do-something"
  when: step.enabled | default(true)
```

### 5. Handle Platform Differences

```yaml
- name: macOS specific task
  command: "mac-command"
  when: ansible_os_family == "Darwin"

- name: Linux specific task
  command: "linux-command"
  when: ansible_os_family in ["Debian", "RedHat"]
```

### 6. Report Progress

```yaml
- name: Report completion
  debug:
    msg: "Completed task for {{ step.name }}"
```

### 7. Use Loop Control for Lists

```yaml
- name: Process items
  command: "process {{ item }}"
  loop: "{{ step['items'] }}"  # Use bracket notation for 'items' key
  loop_control:
    label: "{{ item.name }}"
```

### 8. Handle Failures Gracefully

```yaml
- name: Try to do something
  command: "might-fail"
  failed_when: false
  register: result

- name: Check result
  debug:
    msg: "Warning: Command failed"
  when: result.rc != 0
```

## Common Patterns

### File Operations

```yaml
- name: Ensure directory exists
  file:
    path: "{{ step.directory }}"
    state: directory
    mode: '0755'

- name: Copy file
  copy:
    src: "{{ step.source }}"
    dest: "{{ step.destination }}"
    mode: preserve
```

### Package Installation

```yaml
- name: Install package
  community.general.homebrew:
    name: "{{ step.package }}"
    state: present
```

### Service Management

```yaml
- name: Start service
  command: "launchctl start {{ step.name }}"
  when: step.started | default(true)
```

### Template Generation

```yaml
- name: Generate config file
  copy:
    dest: "{{ step.config_path }}"
    content: |
      # Config for {{ step.name }}
      setting1={{ step.setting1 }}
      setting2={{ step.setting2 }}
```

## Testing Handlers

Create a test state file:

```yaml
# test_my_handler.yaml
- type: my_handler
  required_field: "test_value"
  optional_field: "test"
```

Test with:

```bash
frame install test_my_handler.yaml --verbose
```

## Examples

See existing handlers in this directory for complete examples:
- `install_app.yml` - File operations, conditional sudo
- `defaults.yml` - List iteration, ansible module usage
- `homebrew.yml` - Simple package installation
- `launchctl.yml` - Complex template generation, service management

## Third-Party Distribution

To distribute your handler:

1. **Single File**: Share the `.yml` file
   - Users place it in `src/frame/install/templates/handlers/`

2. **Package**: Create a Python package that registers handlers
   ```python
   # myhandlers/__init__.py
   from frame.install.generators import register_handler_from_file

   def install():
       register_handler_from_file("my_handler")
   ```

3. **Git Repository**: Users can clone your handlers repo
   ```bash
   git clone https://github.com/user/frame-handlers.git
   cp frame-handlers/*.yml src/frame/install/templates/handlers/
   ```

## Resources

- [Ansible Modules](https://docs.ansible.com/ansible/latest/collections/index_module.html)
- [Jinja2 Templates](https://jinja.palletsprojects.com/)
- [Frame Documentation](../../../../README.md)
