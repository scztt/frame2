"""Main installer logic for Frame install command."""

import getpass
import os
import shutil
import sys
import typer
import yaml
from pathlib import Path
import tempfile
from typing import List, Dict, Any, Optional

from .generators import (
    generate_site_yml,
    generate_ansible_cfg,
    generate_inventory,
    load_handler,
    get_handler_dependencies,
    step_label,
)


def check_ansible_installed() -> None:
    """Verify ansible-playbook is available, exit with helpful message if not.

    Also ensures the venv's bin directory (where ansible-playbook is installed
    alongside frame) is on PATH so ansible-runner can find it.
    """
    # The venv bin dir where frame (and ansible-playbook) live
    # Don't resolve() — sys.executable may be a symlink in the venv
    # pointing to the system Python, but scripts live in the venv's bin/
    venv_bin = str(Path(sys.executable).parent)
    if venv_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")

    if shutil.which("ansible-playbook") is None:
        typer.echo("❌ Error: ansible-playbook not found", err=True)
        typer.echo("", err=True)
        typer.echo(f"  Python:   {sys.executable}", err=True)
        typer.echo(f"  Venv bin: {venv_bin}", err=True)
        typer.echo(f"  PATH:     {os.environ.get('PATH', '')}", err=True)
        # Check if ansible-playbook exists in venv but isn't executable
        venv_ap = Path(venv_bin) / "ansible-playbook"
        typer.echo(f"  ansible-playbook in venv: {'YES' if venv_ap.exists() else 'NO'}", err=True)
        if not venv_ap.exists():
            # Show what ansible-related files ARE in the venv
            ansible_files = [f.name for f in Path(venv_bin).iterdir() if "ansible" in f.name.lower()]
            typer.echo(f"  ansible files in venv: {ansible_files or 'none'}", err=True)
        typer.echo("", err=True)
        typer.echo("Ansible is bundled with Frame. Try reinstalling:", err=True)
        typer.echo(f"  {venv_bin}/pip install ansible", err=True)
        raise typer.Exit(1)


def validate_state_entries(state_entries: List[Dict[str, Any]]) -> None:
    """Validate state file entries and raise typer.Exit on errors."""
    for i, entry in enumerate(state_entries):
        if not isinstance(entry, dict):
            typer.echo(f"❌ Error: Entry {i} is not a dictionary", err=True)
            raise typer.Exit(1)
        if "type" not in entry:
            typer.echo(f"❌ Error: Entry {i} missing 'type' field", err=True)
            raise typer.Exit(1)

        # Type-specific validation
        entry_type = entry["type"]

        if entry_type == "install_app":
            has_path = "path" in entry
            has_remote = "remote" in entry
            if not has_path and not has_remote:
                typer.echo(f"❌ Error: Entry {i} (install_app) missing 'path' or 'remote' field", err=True)
                raise typer.Exit(1)
            if has_remote:
                if not isinstance(entry["remote"], dict):
                    typer.echo(f"❌ Error: Entry {i} (install_app) 'remote' must be a dict with 'url'", err=True)
                    raise typer.Exit(1)
                if "url" not in entry["remote"]:
                    typer.echo(f"❌ Error: Entry {i} (install_app) remote missing 'url' field", err=True)
                    raise typer.Exit(1)

        elif entry_type == "defaults":
            if "items" not in entry:
                typer.echo(f"❌ Error: Entry {i} (defaults) missing 'items' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry["items"], list):
                typer.echo(f"❌ Error: Entry {i} (defaults) 'items' must be a list", err=True)
                raise typer.Exit(1)

        elif entry_type == "homebrew":
            if "packages" not in entry:
                typer.echo(f"❌ Error: Entry {i} (homebrew) missing 'packages' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry["packages"], list):
                typer.echo(f"❌ Error: Entry {i} (homebrew) 'packages' must be a list", err=True)
                raise typer.Exit(1)

        elif entry_type == "launchctl":
            has_src = "src" in entry
            has_program = "program" in entry
            if not has_src and not has_program:
                typer.echo(f"❌ Error: Entry {i} (launchctl) missing 'src' or 'program' field", err=True)
                raise typer.Exit(1)
            if not has_src and "label" not in entry:
                typer.echo(f"❌ Error: Entry {i} (launchctl) missing 'label' field (required without 'src')", err=True)
                raise typer.Exit(1)

        elif entry_type == "copy":
            if "src" not in entry:
                typer.echo(f"❌ Error: Entry {i} (copy) missing 'src' field", err=True)
                raise typer.Exit(1)
            if "dest" not in entry:
                typer.echo(f"❌ Error: Entry {i} (copy) missing 'dest' field", err=True)
                raise typer.Exit(1)

        elif entry_type == "command":
            if "args" not in entry:
                typer.echo(f"❌ Error: Entry {i} (command) missing 'args' field", err=True)
                raise typer.Exit(1)

        elif entry_type == "install_pkg":
            has_path = "path" in entry
            has_remote = "remote" in entry
            if not has_path and not has_remote:
                typer.echo(f"❌ Error: Entry {i} (install_pkg) missing 'path' or 'remote' field", err=True)
                raise typer.Exit(1)
            if has_remote:
                if not isinstance(entry["remote"], dict):
                    typer.echo(f"❌ Error: Entry {i} (install_pkg) 'remote' must be a dict with 'url'", err=True)
                    raise typer.Exit(1)
                if "url" not in entry["remote"]:
                    typer.echo(f"❌ Error: Entry {i} (install_pkg) remote missing 'url' field", err=True)
                    raise typer.Exit(1)

        elif entry_type == "systemsetup":
            if "items" not in entry:
                typer.echo(f"❌ Error: Entry {i} (systemsetup) missing 'items' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry["items"], dict):
                typer.echo(f"❌ Error: Entry {i} (systemsetup) 'items' must be a dictionary", err=True)
                raise typer.Exit(1)

        elif entry_type == "npx":
            if "package" not in entry:
                typer.echo(f"❌ Error: Entry {i} (npx) missing 'package' field", err=True)
                raise typer.Exit(1)

        elif entry_type == "audio":
            has_config = any(k in entry for k in ("output", "input", "system", "volume", "aggregate"))
            if not has_config:
                typer.echo(f"❌ Error: Entry {i} (audio) must specify at least one of: output, input, system, volume, aggregate", err=True)
                raise typer.Exit(1)

        elif entry_type == "download":
            if "url" not in entry:
                typer.echo(f"❌ Error: Entry {i} (download) missing 'url' field", err=True)
                raise typer.Exit(1)
            if "dest" not in entry:
                typer.echo(f"❌ Error: Entry {i} (download) missing 'dest' field", err=True)
                raise typer.Exit(1)

        elif entry_type == "pause":
            if "prompt" not in entry:
                typer.echo(f"❌ Error: Entry {i} (pause) missing 'prompt' field", err=True)
                raise typer.Exit(1)


def get_required_handlers(state_entries: List[Dict[str, Any]]) -> set:
    """Extract unique handler types needed from state entries, including dependencies."""
    handlers = {entry["type"] for entry in state_entries}
    # Resolve dependencies declared in handler metadata
    for handler in list(handlers):
        deps = get_handler_dependencies(handler)
        handlers.update(deps)
    return handlers


def _run_with_status(
    ansible_dir: Path,
    cmdline: str,
    check: bool = False,
    become_password: Optional[str] = None,
):
    """Run ansible with direct terminal passthrough.

    Uses ansible-runner in subprocess mode with stdin/stdout/stderr wired
    to the terminal, so interactive prompts (like ansible.builtin.pause)
    work natively. Ansible handles its own output formatting.
    """
    from ansible_runner.config.runner import RunnerConfig
    from ansible_runner import Runner

    typer.echo()

    envvars = {}
    if become_password:
        envvars["ANSIBLE_BECOME_PASS"] = become_password

    rc = RunnerConfig(
        private_data_dir=str(ansible_dir),
        playbook="site.yml",
        cmdline=cmdline or None,
        envvars=envvars if envvars else None,
    )
    rc.prepare()

    # Switch to subprocess mode and set fd attrs directly —
    # Runner checks runner_mode (runner.py:214) then hasattr (runner.py:215)
    rc.runner_mode = 'subprocess'
    rc.input_fd = sys.stdin
    rc.output_fd = sys.stdout
    rc.error_fd = sys.stderr

    runner = Runner(rc)
    runner.run()
    return runner


def install(
    state_file: Path,
    verbose: bool = False,
    artifacts_only: bool = False,
    check: bool = False,
    diff: bool = False,
    list_tasks: bool = False,
    ask_become_pass: bool = False,
    host: Optional[str] = None,
) -> None:
    """
    Execute installation based on state.yaml file.

    This is the main installer function that:
    1. Reads and validates state.yaml
    2. Generates ansible playbooks (site.yml, plan.yml, handlers)
    3. Executes via ansible-runner
    4. Reports results
    """
    # Check ansible is available before doing anything else
    check_ansible_installed()

    typer.echo("📦 Frame Installer")
    typer.echo(f"Reading state from: {state_file}")
    if host:
        typer.echo(f"Target: {host} (remote via SSH)")

    # Read state.yaml
    if not state_file.exists():
        typer.echo(f"❌ Error: State file not found: {state_file}", err=True)
        raise typer.Exit(1)

    try:
        with open(state_file) as f:
            raw = yaml.safe_load(f)
    except Exception as e:
        typer.echo(f"❌ Error reading state file: {e}", err=True)
        raise typer.Exit(1)

    # Support both list (legacy) and dict (new) formats
    if isinstance(raw, list):
        state_entries = raw
        config = {}
    elif isinstance(raw, dict):
        config = raw.get("config", {})
        state_entries = raw.get("steps", [])
    else:
        typer.echo("❌ Error: State file must contain a list or a dict with 'steps'", err=True)
        raise typer.Exit(1)

    if not isinstance(state_entries, list):
        typer.echo("❌ Error: Steps must be a list of entries", err=True)
        raise typer.Exit(1)

    # Set resources_dir default to state file's directory (absolute)
    # User-specified values are passed through as-is
    if "resources_dir" not in config:
        config["resources_dir"] = str(state_file.resolve().parent)

    typer.echo(f"Found {len(state_entries)} installation step(s)")
    if artifacts_only:
        typer.echo("Mode: artifacts only (download without install)")
    if check:
        typer.echo("Mode: dry run (--check)")

    # Validate entries
    validate_state_entries(state_entries)

    # Get required handlers
    required_handlers = get_required_handlers(state_entries)

    # Create temporary ansible directory structure
    # ansible-runner expects: project/ for playbooks, inventory/ for hosts
    with tempfile.TemporaryDirectory() as tmpdir:
        ansible_dir = Path(tmpdir) / "ansible"
        ansible_dir.mkdir()

        # project/ contains playbooks and task files
        project_dir = ansible_dir / "project"
        project_dir.mkdir()

        types_dir = project_dir / "types"
        types_dir.mkdir()

        # inventory/ contains host definitions
        inventory_dir = ansible_dir / "inventory"
        inventory_dir.mkdir()

        # Prompt for sudo password if requested (before generating playbooks
        # so it's available as {{ config.become_password }} in templates)
        become_password = None
        if ask_become_pass:
            become_password = getpass.getpass("Enter your password (for sudo): ")
            config["sudo_password"] = become_password

        typer.echo("⚙️  Generating ansible playbooks...")

        # Generate site.yml with one include_tasks per step
        (project_dir / "site.yml").write_text(generate_site_yml(state_entries, config, host=host))

        # Generate config files
        (project_dir / "ansible.cfg").write_text(generate_ansible_cfg())
        (inventory_dir / "hosts").write_text(generate_inventory(host=host))

        # Generate required type handlers
        for handler_type in required_handlers:
            try:
                handler_content = load_handler(handler_type)
                (types_dir / f"{handler_type}.yml").write_text(handler_content)
            except FileNotFoundError:
                typer.echo(f"❌ Error: Unknown handler type: {handler_type}", err=True)
                raise typer.Exit(1)

        # List tasks mode: just show the plan and return
        if list_tasks:
            typer.echo()
            for i, entry in enumerate(state_entries, 1):
                typer.echo(f"  [ ] {i}. {step_label(entry)}")
            typer.echo()
            return

        # Build cmdline args for ansible
        cmdline_parts = []
        if artifacts_only:
            cmdline_parts.append("--tags artifact")
        if check:
            cmdline_parts.append("--check")
        if diff:
            cmdline_parts.append("--diff")
        cmdline = " ".join(cmdline_parts) if cmdline_parts else ""

        if verbose:
            typer.echo(f"   Working directory: {ansible_dir}")
            typer.echo(f"   Inventory: {inventory_dir / 'hosts'}")
            typer.echo("   Inventory contents:")
            typer.echo((inventory_dir / "hosts").read_text())

        result = _run_with_status(ansible_dir, cmdline, check=check, become_password=become_password)

        if result.status == "successful":
            typer.echo()
            typer.echo("✅ Done!")
        elif result.status == "failed":
            typer.echo()
            if not verbose:
                typer.echo("Run with --verbose for detailed error information")
            raise typer.Exit(1)
