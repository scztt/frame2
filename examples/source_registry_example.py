"""
Example demonstrating the source registry system.

Shows how to create sources from dict/JSON configs using make_source,
similar to how values.py works with TypeRegistry.
"""

from frame.action_observable import make_source

# Example 1: Create ShellSource from dict (string command)
print("=== Example 1: ShellSource from dict (string command) ===")
shell_config = {"type": "shell", "command": "echo 'Hello from registry!'"}
shell, _ = make_source(shell_config)
result = shell.run()
print(f"Result: {result}\n")

# Example 1b: ShellSource with list command
print("=== Example 1b: ShellSource with list command ===")
list_config = {"type": "shell", "command": ["echo", "-n", "Hello from list!"]}
list_shell, _ = make_source(list_config)
result = list_shell.run()
print(f"Result: {result}\n")

# Example 2: ShellSource with JSON parser
print("=== Example 2: ShellSource with JSON parser ===")
json_config = {"type": "shell", "command": 'echo \'{"status": "ok", "count": 42}\'', "parser": "json"}
json_shell, _ = make_source(json_config)
result = json_shell.run()
print(f"Parsed result: {result}")
print(f"Count value: {result['count']}\n")

# Example 3: ScreenshotSource from dict
print("=== Example 3: ScreenshotSource from dict ===")
screenshot_config = {"type": "screenshot", "x": 0, "y": 0, "width": 800, "height": 600, "id": "example_screenshot"}
screenshot, _ = make_source(screenshot_config)
print(f"Screenshot source created: {screenshot.id}")
print(f"Region: {screenshot.width}x{screenshot.height} at ({screenshot.x}, {screenshot.y})\n")

# Example 4: Multiple sources from config list
print("=== Example 4: Multiple sources from config ===")
configs = [{"type": "shell", "command": "date"}, {"type": "shell", "command": "whoami"}, {"type": "screenshot", "id": "main_screen"}]

sources = [make_source(config)[0] for config in configs]
print(f"Created {len(sources)} sources:")
for i, source in enumerate(sources):
    print(f"  {i+1}. {source.__class__.__name__}")

# Example 5: This is how it would work with YAML
print("\n=== Example 5: Simulating YAML config ===")
yaml_like_config = """
sources:
  - type: shell
    command: uptime
  - type: shell
    command: df -h /
    parser: string
  - type: tail
    path: /var/log/system.log
    lines: 50
"""

# In practice, you'd parse YAML and pass the dicts to make_source
print("YAML config would be parsed into dicts and passed to make_source()")
print("This allows easy configuration from config files!")
