# Homebrew and Launchctl Handlers

## Summary

Added two new handler types for package management and service management:
- **homebrew** - Install packages via Homebrew
- **launchctl** - Manage user launchd services with simplified plist generation

## Homebrew Handler

Installs packages using `community.general.homebrew` ansible module.

### Parameters

```yaml
- type: homebrew
  packages:          # Required: List of package names
    - git
    - node
    - ffmpeg
  state: present     # Optional: present (default), latest, absent
  update_homebrew: false  # Optional: Update homebrew first (default: false)
```

### Features

- Simple list of package names
- Idempotent (won't reinstall if already present)
- Parallel installation via ansible
- State control (present/latest/absent)

### Example

```yaml
- type: homebrew
  packages:
    - git
    - python
    - ffmpeg
    - imagemagick
  state: latest
```

### Testing

```bash
uv run frame install /tmp/test_frame_install/state_homebrew_test.yaml
# ✅ Installed 3 Homebrew package(s): jq, wget, tree
```

## Launchctl Handler

Manages user launchd services with automatic plist generation from template.

### Parameters

```yaml
- type: launchctl
  name: com.example.myservice      # Required: Service label/name
  program: /usr/local/bin/myapp    # Required: Path to executable

  # Optional parameters
  args:                            # Command arguments
    - --port
    - "8080"
  working_directory: /path/to/dir  # Working directory
  stdout_path: /tmp/service.log    # Stdout log path
  stderr_path: /tmp/service.err    # Stderr log path
  environment:                     # Environment variables
    NODE_ENV: production
    PORT: "3000"
  run_at_load: true                # Start on load (default: true)
  keep_alive: true                 # Restart if crashes (default: true)
  loaded: true                     # Load the service (default: true)
  started: true                    # Start the service (default: true)
```

### Features

- **Simplified plist generation** - No need to write XML manually
- **Jinja2 template** - Plist generated from parameters
- **Full launchd support** - All common plist keys supported:
  - Label, Program, ProgramArguments
  - WorkingDirectory
  - StandardOutPath, StandardErrorPath
  - RunAtLoad, KeepAlive
  - EnvironmentVariables
- **Automatic management** - Unloads/reloads on updates
- **User-level services** - Installs to ~/Library/LaunchAgents

### Generated Plist Structure

The handler generates a proper macOS plist file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.myservice</string>
  <key>Program</key>
  <string>/usr/local/bin/myapp</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/myapp</string>
    <string>--port</string>
    <string>8080</string>
  </array>
  <!-- ... other keys ... -->
</dict>
</plist>
```

### Example

```yaml
- type: launchctl
  name: com.example.artworkserver
  program: /usr/local/bin/node
  args:
    - /Users/artist/server.js
    - --port
    - "3000"
  working_directory: /Users/artist/artwork
  stdout_path: /tmp/artwork.log
  stderr_path: /tmp/artwork.err
  environment:
    NODE_ENV: production
  run_at_load: true
  keep_alive: true
  loaded: true
  started: true
```

### Testing

```bash
uv run frame install /tmp/test_frame_install/state_launchctl_test.yaml
# ✅ Service com.example.testservice (loaded, started)

# Verify service is running
launchctl list | grep com.example.testservice
# 31360	0	com.example.testservice

# Check logs
tail /tmp/testservice.log
# Test service running
# Test service running
```

### Service Management

The handler automatically:
1. Creates ~/Library/LaunchAgents directory if needed
2. Generates plist file from template
3. Unloads existing service (if present)
4. Loads new service configuration
5. Starts service if `started: true`

## Implementation Details

### Code Structure

Both handlers follow the registry pattern:

**generators.py:**
- `generate_homebrew_handler()` - Generates homebrew playbook
- `generate_launchctl_handler()` - Generates launchctl playbook with embedded plist template
- Added to `HANDLER_GENERATORS` registry

**installer.py:**
- Validation for required fields (`packages`, `name`, `program`)
- Summary formatting showing package count/names and service status

### Technical Notes

**Homebrew:**
- Uses `community.general.homebrew` module (already in collection)
- Loop over packages with labeled output
- State management (present/latest/absent)

**Launchctl:**
- Pure Ansible implementation (no external roles needed)
- Embedded Jinja2 template for plist generation
- Uses `copy` module with inline content
- Uses `command` module for launchctl operations
- Conditional loading/starting based on parameters

## All Handler Types

Frame now supports 4 handler types:

1. **install_app** - Copy .app bundles to target location
2. **defaults** - Configure macOS system preferences
3. **homebrew** - Install packages via Homebrew
4. **launchctl** - Manage user launchd services

## Comprehensive Example

See [examples/state_comprehensive.yaml](examples/state_comprehensive.yaml) for example using all types together.

## Testing

All handlers tested and working:

```bash
# Homebrew
✅ Installed 3 Homebrew package(s): jq, wget, tree

# Launchctl
✅ Service com.example.testservice (loaded, started)
✅ Plist generated correctly
✅ Service running (verified with launchctl list)
✅ Logs working (verified in /tmp/testservice.log)
```

## Next Steps

Potential additional handlers:
- `dmg_install` - Mount DMG and install contents
- `pkg_install` - Install .pkg files
- `copy_file` - Copy individual files with permissions
- `run_command` - Execute arbitrary shell commands
- `git_clone` - Clone git repositories
