"""Integration test fixtures for Frame install handlers."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Generator

import pytest
import yaml


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="frame_test_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_resources(temp_dir: Path) -> Path:
    """Create a resources directory with test files."""
    resources = temp_dir / "resources"
    resources.mkdir()

    # Create some test files
    (resources / "test_file.txt").write_text("Hello, World!")
    (resources / "test_script.sh").write_text("#!/bin/bash\necho 'test'\n")
    (resources / "test_script.sh").chmod(0o755)

    # Create a subdirectory with files
    subdir = resources / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("Nested file")

    return resources


@pytest.fixture
def state_file_factory(temp_dir: Path) -> Callable:
    """Factory to create state files for testing."""

    def create_state_file(
        steps: list,
        config: dict | None = None,
        filename: str = "state.yml"
    ) -> Path:
        state = {"steps": steps}
        if config:
            state["config"] = config

        state_path = temp_dir / filename
        state_path.write_text(yaml.dump(state, default_flow_style=False))
        return state_path

    return create_state_file


@pytest.fixture
def run_install() -> Callable:
    """Run frame install and return the result."""

    def _run(
        state_file: Path,
        check: bool = False,
        verbose: bool = False,
        expect_success: bool = True,
    ) -> subprocess.CompletedProcess:
        cmd = ["uv", "run", "frame", "install", str(state_file)]
        if check:
            cmd.append("--check")
        if verbose:
            cmd.append("--verbose")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,  # Project root
        )

        if expect_success and result.returncode != 0:
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")

        if expect_success:
            assert result.returncode == 0, f"Install failed: {result.stderr}"

        return result

    return _run


@pytest.fixture
def launchctl_test_dir(temp_dir: Path) -> Path:
    """Create a temp directory for launchctl plists (avoids polluting ~/Library)."""
    plist_dir = temp_dir / "LaunchAgents"
    plist_dir.mkdir()
    return plist_dir


@pytest.fixture
def skip_if_no_homebrew():
    """Skip test if Homebrew is not installed."""
    if shutil.which("brew") is None:
        pytest.skip("Homebrew not installed")


@pytest.fixture
def skip_if_no_node():
    """Skip test if Node.js is not installed."""
    if shutil.which("node") is None:
        pytest.skip("Node.js not installed")


@pytest.fixture
def skip_if_no_displayplacer():
    """Skip test if displayplacer is not installed."""
    if shutil.which("displayplacer") is None:
        pytest.skip("displayplacer not installed")


@pytest.fixture
def skip_if_ci():
    """Skip test if running in CI (for tests requiring hardware/GUI)."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        pytest.skip("Skipping in CI environment")


def assert_file_exists(path: Path, msg: str = "") -> None:
    """Assert that a file exists."""
    assert path.exists(), f"File does not exist: {path}. {msg}"


def assert_file_contains(path: Path, content: str, msg: str = "") -> None:
    """Assert that a file contains specific content."""
    assert path.exists(), f"File does not exist: {path}"
    actual = path.read_text()
    assert content in actual, f"Expected '{content}' in {path}. Got: {actual[:200]}. {msg}"


def assert_file_mode(path: Path, mode: int, msg: str = "") -> None:
    """Assert that a file has specific permissions."""
    assert path.exists(), f"File does not exist: {path}"
    actual = path.stat().st_mode & 0o777
    assert actual == mode, f"Expected mode {oct(mode)}, got {oct(actual)}. {msg}"


def assert_plist_key(plist_path: Path, key: str, expected_value) -> None:
    """Assert that a plist file contains a specific key/value."""
    import plistlib
    assert plist_path.exists(), f"Plist does not exist: {plist_path}"
    with open(plist_path, "rb") as f:
        plist = plistlib.load(f)
    assert key in plist, f"Key '{key}' not in plist"
    assert plist[key] == expected_value, f"Expected {key}={expected_value}, got {plist[key]}"
