"""Main installer logic for Frame install command."""

import getpass
import shutil
import typer
import yaml
import ansible_runner
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
    """Verify ansible-playbook is available, exit with helpful message if not."""
    if shutil.which("ansible-playbook") is None:
        typer.echo("❌ Error: ansible-playbook not found", err=True)
        typer.echo("", err=True)
        typer.echo("Frame requires Ansible to be installed. Install it with:", err=True)
        typer.echo("  brew install ansible     # macOS with Homebrew", err=True)
        typer.echo("  pip install ansible      # or via pip", err=True)
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
            if "path" not in entry:
                typer.echo(f"❌ Error: Entry {i} (install_pkg) missing 'path' field", err=True)
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
    state_entries: List[Dict[str, Any]],
    verbose: bool,
    check: bool = False,
    become_password: Optional[str] = None,
):
    """Run ansible and display live step-by-step progress.

    Streams results as they happen. Each step prints when it starts,
    sub-tasks print as they complete. Failures show full error details.
    """
    current_step = [-1]
    step_has_failed = set()
    step_has_changed = set()
    step_names = {step_label(e) for e in state_entries}
    total_steps = len(state_entries)

    def on_event(event):
        event_type = event.get("event", "")
        data = event.get("event_data", {})

        # Detect step boundaries — each include_tasks fires this
        if event_type == "playbook_on_task_start":
            task_name = data.get("task", "")
            if task_name in step_names:
                current_step[0] += 1
                idx = current_step[0]
                label = step_label(state_entries[idx])
                typer.echo(f"  [{idx + 1}/{total_steps}] {label}")
            return

        # Track results
        if event_type in ("runner_on_ok", "runner_on_failed", "runner_on_skipped", "runner_item_on_ok", "runner_item_on_failed", "runner_item_on_skipped"):
            idx = current_step[0]
            if idx < 0 or idx >= len(state_entries):
                return

            task_name = data.get("task", "")
            res = data.get("res", {})

            # Append item label for loop tasks
            if "item" in res:
                item = res["item"]
                if isinstance(item, str):
                    task_name = f"{task_name} ({item})"

            is_failed = event_type in ("runner_on_failed", "runner_item_on_failed")
            is_changed = res.get("changed", False)

            if is_failed:
                step_has_failed.add(idx)
                status_mark = typer.style("[!]", fg="red")
            elif is_changed:
                step_has_changed.add(idx)
                status_mark = typer.style("[~]", fg="green")
            else:
                status_mark = typer.style("[x]", fg="green")

            # Verbose: print every sub-task
            if verbose:
                typer.echo(f"      {status_mark} {task_name}")

            # Always show failure details with full context
            if is_failed:
                if not verbose:
                    typer.echo(typer.style(f"      [!] {task_name}", fg="red"))

                # Show all useful error fields
                msg = res.get("msg", "")
                stderr = res.get("stderr", "").strip()
                stdout = res.get("stdout", "").strip()
                cmd = res.get("cmd", "")
                rc = res.get("rc")

                if msg:
                    typer.echo(typer.style(f"          Error: {msg}", fg="red"))
                if cmd:
                    if isinstance(cmd, list):
                        cmd = " ".join(cmd)
                    typer.echo(f"          Command: {cmd}")
                if rc is not None:
                    typer.echo(f"          Exit code: {rc}")
                if stdout:
                    typer.echo(f"          stdout: {stdout[:500]}")
                if stderr:
                    typer.echo(typer.style(f"          stderr: {stderr[:500]}", fg="red"))

                # Show task path for debugging
                task_path = data.get("task_path", "")
                if task_path:
                    typer.echo(f"          Task: {task_path}")

    typer.echo()

    # Pass become password via environment variable
    envvars = {}
    if become_password:
        envvars["ANSIBLE_BECOME_PASS"] = become_password

    result = ansible_runner.run(
        private_data_dir=str(ansible_dir),
        playbook="site.yml",
        cmdline=cmdline or None,
        quiet=True,
        event_handler=on_event,
        envvars=envvars if envvars else None,
    )

    # Summary
    typer.echo()
    ran = current_step[0] + 1
    ok_count = ran - len(step_has_failed)
    failed_count = len(step_has_failed)
    skipped_count = total_steps - ran

    if failed_count == 0 and skipped_count == 0:
        typer.echo(typer.style(f"  All {ok_count} steps completed successfully", fg="green"))
    else:
        parts = []
        if ok_count > 0:
            parts.append(typer.style(f"{ok_count} ok", fg="green"))
        if failed_count:
            parts.append(typer.style(f"{failed_count} failed", fg="red"))
        if skipped_count:
            parts.append(f"{skipped_count} skipped")
        typer.echo("  " + " · ".join(parts))

    return result


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

        # Prompt for sudo password if requested
        become_password = None
        if ask_become_pass:
            become_password = getpass.getpass("BECOME password: ")

        if verbose:
            typer.echo(f"   Working directory: {ansible_dir}")
            typer.echo(f"   Inventory: {inventory_dir / 'hosts'}")
            typer.echo("   Inventory contents:")
            typer.echo((inventory_dir / "hosts").read_text())

        result = _run_with_status(ansible_dir, cmdline, state_entries, verbose, check=check, become_password=become_password)

        if result.status == "successful":
            typer.echo()
            typer.echo("✅ Done!")
        elif result.status == "failed":
            typer.echo()
            if not verbose:
                typer.echo("Run with --verbose for detailed error information")
            raise typer.Exit(1)
