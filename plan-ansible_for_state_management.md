# Frame Installer — Architecture & Implementation Plan

This document summarizes the agreed approach for building a **simple, artist-friendly installation system** powered by Ansible, plus a checklist of work required to implement it.

The intent is to keep artist-facing configuration simple while still producing reproducible, debuggable machine setups.

---

# Core Idea

Artists describe what should be installed using **simple YAML**.

A tool called `frame` then:

1. Converts simple YAML into an executable install plan
2. Vendors dependencies
3. Packages artifacts and installers
4. Runs Ansible locally to configure the machine

Ansible acts purely as the execution engine.

---

# Desired User Experience

Artist prepares installation:

```
frame package ./InstallationConfig --output ./handover
```

Gallery technician installs:

```
cd handover/installer
sudo ansible-playbook site.yml
```

No Ansible knowledge required.

---

# System Components

## 1. Frame CLI (Python)

Responsibilities:

• Read artist YAML config
• Generate Ansible execution plan
• Vendor Ansible dependencies
• Collect artifacts/installers
• Package handover folder
• Run Ansible playbooks

Primary commands:

```
frame package
frame hydrate
frame install
```

---

## 2. Artwork Bundle (handover folder)

Example structure:

```
Installation/
  installer/
    site.yml
    ansible.cfg
    inventory.ini
    types/
    platform/
  artwork.yml
  machine.local.yml
  plan.yml
  requirements.yml
  vendor/
    roles/
    collections/
  artifacts/
  apps/
  files/
```

This folder can run offline.

---

## 3. Generic Ansible Engine

A single generic `site.yml` executes steps described in `plan.yml`.

It does **not** know about specific applications.

Execution is driven entirely by step handlers.

---

# Plan-driven Execution Model

Artist YAML → Frame → plan.yml → Ansible execution.

Example plan:

```yaml
steps:
  - name: Install SuperCollider
    type: install_app
    path: apps/SuperCollider.app
```

Ansible dispatches each step to a handler based on `type`.

---

# Handler-Based Task Macros

Handlers live in:

```
installer/types/<type>.yml
```

Example:

```
types/install_app.yml
```

Contains:

• ensure /Applications exists
• copy app bundle
• remove quarantine

Handlers act as reusable macros.

---

# Platform Abstraction Strategy

One outward-facing type maps to platform-specific implementations.

Example:

```
type: user_service
```

Dispatcher:

```
include_tasks platform/darwin/user_service.yml
include_tasks platform/linux/user_service.yml
```

macOS uses `launchd`, Linux uses systemd.

Config stays platform-neutral.

---

# Dependency Handling

Dependencies are declared via Ansible role metadata or requirements files.

Example:

```
dependencies:
  - role: app_vscode
```

Dependencies are vendored during packaging.

Install runs offline.

---

# Artifact Strategy

Artifacts include:

• application installers
• media assets
• plugins
• configuration files

Hydrated via:

```
ansible-playbook --tags artifact
```

or via Frame downloads.

Artifacts ship with bundle.

---

# Execution Flow Summary

```
artist config
    ↓
frame package
    ↓
plan.yml generated
    ↓
dependencies vendored
    ↓
artifacts cached
    ↓
bundle shipped
    ↓
frame install
    ↓
ansible-playbook site.yml
```

---

# Implementation Checklist

## Phase 1 — Core Execution ✅ COMPLETED (Proof of Concept)

- [x] Generic site.yml dispatcher
- [x] Step loop execution
- [x] Handler include mechanism
- [x] Bundle-relative path handling

**Implementation Details:**
- `frame install` command added to [cli.py](src/frame/cli.py)
- Generates ansible playbook structure in temporary directory
- Uses ansible-runner for execution
- Automatic sudo detection based on target path
- Status reporting with typer CLI

**Files:**
- `src/frame/cli.py` - CLI command and playbook generation
- `examples/state_example.yaml` - Example configuration

## Phase 2 — Step Handlers

Implement core handlers:

- [x] install_app - **COMPLETED** (copies .app bundles with smart sudo detection)
- [x] defaults (was defaults_write) - **COMPLETED** (macOS system preferences via osx_defaults)
- [x] homebrew - **COMPLETED** (package installation via community.general.homebrew)
- [x] launchctl (was user_service) - **COMPLETED** (user launchd services with plist generation)
- [ ] pkg_install
- [ ] dmg_install
- [ ] copy_file
- [ ] run_command

## Phase 3 — Platform Adapters

- [x] macOS launchd services - **COMPLETED** (launchctl handler with plist template)
- [ ] Linux systemd services
- [ ] platform detection logic

## Phase 4 — Frame CLI

- [ ] Config parser
- [ ] Plan generator
- [ ] Artifact resolver
- [ ] Dependency vendor step
- [ ] Bundle packager
- [ ] Ansible execution wrapper

## Phase 5 — Packaging & Offline Support

- [ ] requirements.yml generation
- [ ] ansible-galaxy vendoring
- [ ] vendor directory layout
- [ ] ansible.cfg path configuration

## Phase 6 — Debug & Dev UX

- [ ] Dry-run mode
- [ ] Verbose logging
- [ ] Artifact verification
- [ ] Syntax check wrapper

---

# Engineering Principles

• Config stays simple
• Ansible remains debuggable
• Packaging produces reproducible installs
• Platform differences are abstracted
• Third-party extensions are supported
• Offline installs work reliably

---

# Long-Term Evolution Path

Possible future additions:

• dependency graph resolution
• version locking
• update/repair commands
• install rollback
• cluster installs
• Windows support

---

# Final Mental Model

```
Simple YAML → Frame → Plan → Ansible → Machine Setup
```

Artists write intent.

Frame compiles execution.

Ansible performs installation.

---

# Implementation Status

## Proof of Concept - COMPLETED ✅

A working proof-of-concept has been implemented. See [ANSIBLE_INSTALL_POC.md](ANSIBLE_INSTALL_POC.md) for details.

**What Works:**
- `frame install` command with state.yaml
- `install_app` type handler (copies .app bundles)
- Smart sudo detection based on target path
- Multiple app installations in sequence
- Verbose output mode
- Status reporting and error handling
- Uses ansible's built-in `copy` module

**Test Command:**
```bash
uv run frame install examples/state_example.yaml
```

**Next Steps:**
- Add more type handlers (pkg_install, dmg_install, user_service, etc.)
- Implement `frame package` for offline bundles
- Add platform-specific handlers (launchd vs systemd)

---

End of architecture summary.

