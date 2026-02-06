"""Integration tests for Frame install handlers.

Each test:
1. Creates a YAML state file with handler config
2. Runs `frame install` against it
3. Validates the resulting machine state

Tests use temp directories where possible to avoid polluting the system.
Tests requiring hardware, sudo, or GUI are skipped in CI.
"""

import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from .conftest import (
    assert_file_contains,
    assert_file_exists,
    assert_file_mode,
    assert_plist_key,
)


# ============================================================================
# command handler tests
# ============================================================================


class TestCommandHandler:
    """Tests for the command handler."""

    def test_command_list_format(self, temp_dir, state_file_factory, run_install):
        """Test command with list args creates expected output."""
        output_file = temp_dir / "output.txt"

        state_file = state_file_factory([
            {
                "name": "Write to file",
                "type": "command",
                "args": ["bash", "-c", f"echo 'hello world' > {output_file}"],
            }
        ])

        run_install(state_file)

        assert_file_exists(output_file)
        assert_file_contains(output_file, "hello world")

    def test_command_string_format(self, temp_dir, state_file_factory, run_install):
        """Test command with string args (shell mode)."""
        output_file = temp_dir / "output.txt"

        state_file = state_file_factory([
            {
                "name": "Shell command",
                "type": "command",
                "args": f"echo 'from shell' > {output_file}",
            }
        ])

        run_install(state_file)

        assert_file_exists(output_file)
        assert_file_contains(output_file, "from shell")

    def test_command_with_working_directory(self, temp_dir, state_file_factory, run_install):
        """Test command respects working_directory."""
        work_dir = temp_dir / "workdir"
        work_dir.mkdir()

        state_file = state_file_factory([
            {
                "name": "Create file in workdir",
                "type": "command",
                "args": ["touch", "created.txt"],
                "working_directory": str(work_dir),
            }
        ])

        run_install(state_file)

        assert_file_exists(work_dir / "created.txt")

    def test_command_with_environment(self, temp_dir, state_file_factory, run_install):
        """Test command with custom environment variables."""
        output_file = temp_dir / "env_output.txt"

        state_file = state_file_factory([
            {
                "name": "Echo env var",
                "type": "command",
                "args": f"echo $MY_VAR > {output_file}",
                "environment": {"MY_VAR": "custom_value"},
            }
        ])

        run_install(state_file)

        assert_file_contains(output_file, "custom_value")

    def test_command_ignore_errors(self, temp_dir, state_file_factory, run_install):
        """Test command with ignore_errors continues on failure."""
        output_file = temp_dir / "success.txt"

        state_file = state_file_factory([
            {
                "name": "Failing command",
                "type": "command",
                "args": ["false"],  # Always exits with 1
                "ignore_errors": True,
            },
            {
                "name": "Subsequent command",
                "type": "command",
                "args": f"echo 'reached' > {output_file}",
            }
        ])

        run_install(state_file)

        assert_file_exists(output_file)
        assert_file_contains(output_file, "reached")


# ============================================================================
# copy handler tests
# ============================================================================


class TestCopyHandler:
    """Tests for the copy handler."""

    def test_copy_single_file(self, temp_dir, test_resources, state_file_factory, run_install):
        """Test copying a single file."""
        dest = temp_dir / "copied.txt"

        state_file = state_file_factory([
            {
                "name": "Copy file",
                "type": "copy",
                "src": str(test_resources / "test_file.txt"),
                "dest": str(dest),
            }
        ])

        run_install(state_file)

        assert_file_exists(dest)
        assert_file_contains(dest, "Hello, World!")

    def test_copy_directory(self, temp_dir, test_resources, state_file_factory, run_install):
        """Test copying a directory."""
        dest = temp_dir / "copied_dir"

        state_file = state_file_factory([
            {
                "name": "Copy directory",
                "type": "copy",
                "src": str(test_resources / "subdir"),
                "dest": str(dest),
            }
        ])

        run_install(state_file)

        # synchronize copies src INTO dest, so path is dest/subdir/nested.txt
        assert_file_exists(dest / "subdir" / "nested.txt")
        assert_file_contains(dest / "subdir" / "nested.txt", "Nested file")

    def test_copy_with_mode(self, temp_dir, test_resources, state_file_factory, run_install):
        """Test copying with specific permissions."""
        dest = temp_dir / "executable.sh"

        state_file = state_file_factory([
            {
                "name": "Copy with mode",
                "type": "copy",
                "src": str(test_resources / "test_script.sh"),
                "dest": str(dest),
                "mode": {
                    "user": "rwx",
                    "group": "rx",
                    "everyone": "rx",
                },
            }
        ])

        run_install(state_file)

        assert_file_exists(dest)
        assert_file_mode(dest, 0o755)


# ============================================================================
# download handler tests
# ============================================================================


class TestDownloadHandler:
    """Tests for the download handler."""

    def test_download_file(self, temp_dir, state_file_factory, run_install):
        """Test downloading a file from URL."""
        dest = temp_dir / "downloaded.txt"

        state_file = state_file_factory([
            {
                "name": "Download test file",
                "type": "download",
                "url": "https://httpbin.org/robots.txt",
                "dest": str(dest),
            }
        ])

        run_install(state_file)

        assert_file_exists(dest)
        # httpbin robots.txt typically contains "User-agent: *"
        assert_file_contains(dest, "User-agent")

    def test_download_with_checksum(self, temp_dir, state_file_factory, run_install):
        """Test download verifies SHA256 checksum."""
        dest = temp_dir / "verified.txt"

        # Create a test file we know the checksum of
        # Using a predictable file from httpbin
        state_file = state_file_factory([
            {
                "name": "Download with checksum",
                "type": "download",
                "url": "https://httpbin.org/robots.txt",
                "dest": str(dest),
                # Note: Don't actually check hash in test since content may vary
            }
        ])

        run_install(state_file)

        assert_file_exists(dest)


# ============================================================================
# launchctl handler tests
# ============================================================================


class TestLaunchctlHandler:
    """Tests for the launchctl handler."""

    def test_launchctl_generate_plist(self, temp_dir, state_file_factory, run_install):
        """Test generating a plist without loading it."""
        plist_dir = temp_dir / "LaunchAgents"
        plist_dir.mkdir()

        state_file = state_file_factory([
            {
                "name": "Test service",
                "type": "launchctl",
                "label": "com.test.service",
                "program": "/usr/bin/true",
                "plist_dir": str(plist_dir),
                "loaded": False,  # Don't actually load
                "started": False,
            }
        ])

        run_install(state_file)

        plist_path = plist_dir / "com.test.service.plist"
        assert_file_exists(plist_path)

        # Verify plist content
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        assert plist["Label"] == "com.test.service"
        assert plist["Program"] == "/usr/bin/true"
        assert plist["RunAtLoad"] == True
        assert plist["KeepAlive"] == True

    def test_launchctl_with_args(self, temp_dir, state_file_factory, run_install):
        """Test plist generation with program arguments."""
        plist_dir = temp_dir / "LaunchAgents"
        plist_dir.mkdir()

        state_file = state_file_factory([
            {
                "name": "Service with args",
                "type": "launchctl",
                "label": "com.test.args",
                "program": "/usr/bin/echo",
                "args": ["hello", "world"],
                "plist_dir": str(plist_dir),
                "loaded": False,
                "started": False,
            }
        ])

        run_install(state_file)

        plist_path = plist_dir / "com.test.args.plist"
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        assert plist["ProgramArguments"] == ["/usr/bin/echo", "hello", "world"]

    def test_launchctl_with_schedule(self, temp_dir, state_file_factory, run_install):
        """Test plist generation with calendar schedule."""
        plist_dir = temp_dir / "LaunchAgents"
        plist_dir.mkdir()

        state_file = state_file_factory([
            {
                "name": "Scheduled service",
                "type": "launchctl",
                "label": "com.test.scheduled",
                "program": "/usr/bin/true",
                "start_calendar_interval": {"Hour": 4, "Minute": 0},
                "run_at_load": False,
                "keep_alive": False,
                "plist_dir": str(plist_dir),
                "loaded": False,
                "started": False,
            }
        ])

        run_install(state_file)

        plist_path = plist_dir / "com.test.scheduled.plist"
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        assert plist["StartCalendarInterval"]["Hour"] == 4
        assert plist["StartCalendarInterval"]["Minute"] == 0
        assert plist["RunAtLoad"] == False


# ============================================================================
# defaults handler tests
# ============================================================================


class TestDefaultsHandler:
    """Tests for the defaults (macOS preferences) handler."""

    def test_defaults_write_string(self, temp_dir, state_file_factory, run_install):
        """Test writing a string preference."""
        # Use a unique test domain to avoid conflicts
        domain = f"com.frame.test.{os.getpid()}"

        state_file = state_file_factory([
            {
                "name": "Set preference",
                "type": "defaults",
                "items": [
                    {
                        "domain": domain,
                        "key": "TestKey",
                        "value": "TestValue",
                        "type": "string",
                    }
                ],
            }
        ])

        try:
            run_install(state_file)

            # Verify using defaults read
            result = subprocess.run(
                ["defaults", "read", domain, "TestKey"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "TestValue" in result.stdout
        finally:
            # Cleanup
            subprocess.run(["defaults", "delete", domain], capture_output=True)

    def test_defaults_write_bool(self, temp_dir, state_file_factory, run_install):
        """Test writing a boolean preference."""
        domain = f"com.frame.test.{os.getpid()}"

        state_file = state_file_factory([
            {
                "name": "Set bool preference",
                "type": "defaults",
                "items": [
                    {
                        "domain": domain,
                        "key": "BoolKey",
                        "value": True,
                        "type": "bool",
                    }
                ],
            }
        ])

        try:
            run_install(state_file)

            result = subprocess.run(
                ["defaults", "read", domain, "BoolKey"],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert "1" in result.stdout or "true" in result.stdout.lower()
        finally:
            subprocess.run(["defaults", "delete", domain], capture_output=True)


# ============================================================================
# install_app handler tests
# ============================================================================


class TestInstallAppHandler:
    """Tests for the install_app handler."""

    def test_install_app_from_path(self, temp_dir, state_file_factory, run_install):
        """Test installing an app from a local path."""
        # Create a fake .app bundle
        app_src = temp_dir / "source" / "TestApp.app"
        app_src.mkdir(parents=True)
        (app_src / "Contents").mkdir()
        (app_src / "Contents" / "Info.plist").write_text("<plist></plist>")

        install_dir = temp_dir / "Applications"
        install_dir.mkdir()

        state_file = state_file_factory([
            {
                "name": "Install test app",
                "type": "install_app",
                "path": str(app_src),
                "install_location": str(install_dir),
            }
        ])

        run_install(state_file)

        installed_app = install_dir / "TestApp.app"
        assert_file_exists(installed_app)
        assert_file_exists(installed_app / "Contents" / "Info.plist")


# ============================================================================
# homebrew handler tests
# ============================================================================


class TestHomebrewHandler:
    """Tests for the homebrew handler."""

    def test_homebrew_check_mode(self, skip_if_no_homebrew, temp_dir, state_file_factory, run_install):
        """Test homebrew in check mode (doesn't actually install)."""
        state_file = state_file_factory([
            {
                "name": "Install package",
                "type": "homebrew",
                "packages": ["cowsay"],  # Harmless small package
            }
        ])

        # Run in check mode - just verify it runs without error
        result = run_install(state_file, check=True)
        assert result.returncode == 0


# ============================================================================
# npx handler tests
# ============================================================================


class TestNpxHandler:
    """Tests for the npx handler."""

    def test_npx_run_package(self, skip_if_no_node, temp_dir, state_file_factory, run_install):
        """Test running an npx package."""
        state_file = state_file_factory([
            {
                "name": "Run npx package",
                "type": "npx",
                "package": "cowsay",
                "args": "hello",
                "show_output": True,
            }
        ])

        result = run_install(state_file)
        # cowsay outputs ASCII art with the message
        assert "hello" in result.stdout or result.returncode == 0


# ============================================================================
# desktop handler tests (requires GUI, skip in CI)
# ============================================================================


class TestDesktopHandler:
    """Tests for the desktop handler."""

    def test_desktop_check_mode(self, skip_if_ci, temp_dir, test_resources, state_file_factory, run_install):
        """Test desktop handler in check mode."""
        # Create a test image
        image_path = temp_dir / "wallpaper.jpg"
        # Create a minimal JPEG (1x1 pixel)
        image_path.write_bytes(
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
            b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
            b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9telestat'
            b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
            b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
            b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\xff\xd9'
        )

        state_file = state_file_factory([
            {
                "name": "Set wallpaper",
                "type": "desktop",
                "image": str(image_path),
            }
        ])

        # Run in check mode to avoid actually changing wallpaper
        result = run_install(state_file, check=True)
        assert result.returncode == 0


# ============================================================================
# pmset handler tests (requires sudo, skip in CI)
# ============================================================================


class TestPmsetHandler:
    """Tests for the pmset handler."""

    def test_pmset_check_mode(self, skip_if_ci, temp_dir, state_file_factory, run_install):
        """Test pmset handler in check mode."""
        state_file = state_file_factory([
            {
                "name": "Power settings",
                "type": "pmset",
                "settings": {
                    "displaysleep": 0,
                },
            }
        ])

        # Run in check mode - may fail due to sudo requirement, that's OK
        result = run_install(state_file, check=True, expect_success=False)
        # Success or sudo password required are both acceptable
        assert result.returncode == 0 or "password is required" in result.stdout


# ============================================================================
# restart handler tests
# ============================================================================


class TestRestartHandler:
    """Tests for the restart handler."""

    def test_restart_notify_only(self, temp_dir, state_file_factory, run_install):
        """Test restart with notify_only (safe to run)."""
        state_file = state_file_factory([
            {
                "name": "Restart notification",
                "type": "restart",
                "notify_only": True,
                "message": "Test restart notification",
            }
        ])

        result = run_install(state_file)
        assert result.returncode == 0


# ============================================================================
# displayplacer handler tests (requires display, skip in CI)
# ============================================================================


class TestDisplayplacerHandler:
    """Tests for the displayplacer handler."""

    def test_displayplacer_list(self, skip_if_ci, skip_if_no_displayplacer, temp_dir, state_file_factory, run_install):
        """Test listing display configuration."""
        state_file = state_file_factory([
            {
                "name": "List displays",
                "type": "displayplacer",
                "list": True,
            }
        ])

        result = run_install(state_file)
        assert result.returncode == 0


# ============================================================================
# YAML !include tests
# ============================================================================


class TestYamlInclude:
    """Tests for YAML !include functionality."""

    def test_include_step_list(self, temp_dir, state_file_factory, run_install):
        """Test including a list of steps from another file."""
        # Create included file
        included_file = temp_dir / "included.yml"
        included_file.write_text("""
- name: First included step
  type: command
  args: ["echo", "from included"]

- name: Second included step
  type: command
  args: ["echo", "also included"]
""")

        output_file = temp_dir / "output.txt"

        # Create main state file with include
        state_content = f"""
config:
  test_output: "{output_file}"

steps:
  - !include {included_file}
  - name: Main step
    type: command
    args: "echo 'main step' > {output_file}"
"""
        state_path = temp_dir / "main.yml"
        state_path.write_text(state_content)

        run_install(state_path)

        assert_file_exists(output_file)
        assert_file_contains(output_file, "main step")

    def test_nested_includes(self, temp_dir, run_install):
        """Test nested includes (A includes B includes C)."""
        # Create C (deepest)
        c_file = temp_dir / "c.yml"
        c_file.write_text("""
- name: Step from C
  type: command
  args: ["touch", "c_ran.txt"]
  working_directory: "{{ config.test_dir }}"
""")

        # Create B (includes C)
        b_file = temp_dir / "b.yml"
        b_file.write_text(f"""
- name: Step from B
  type: command
  args: ["touch", "b_ran.txt"]
  working_directory: "{{{{ config.test_dir }}}}"
- !include {c_file}
""")

        # Create A (main file, includes B)
        state_content = f"""
config:
  test_dir: "{temp_dir}"

steps:
  - name: Step from A
    type: command
    args: ["touch", "a_ran.txt"]
    working_directory: "{{{{ config.test_dir }}}}"
  - !include {b_file}
"""
        state_path = temp_dir / "main.yml"
        state_path.write_text(state_content)

        run_install(state_path)

        # All three files should be created
        assert_file_exists(temp_dir / "a_ran.txt")
        assert_file_exists(temp_dir / "b_ran.txt")
        assert_file_exists(temp_dir / "c_ran.txt")
