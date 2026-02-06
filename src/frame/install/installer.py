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


# Validation schemas for handler types
# Each schema defines: required fields, one-of requirements, type constraints, nested validation
HANDLER_SCHEMAS: Dict[str, Dict[str, Any]] = {
    'install_app': {
        'one_of': ['path', 'remote'],
        'nested': {'remote': {'required': ['url'], 'type': dict}},
    },
    'defaults': {'required': ['items'], 'types': {'items': list}},
    'homebrew': {'required': ['packages'], 'types': {'packages': list}},
    'launchctl': {
        'one_of': ['src', 'program'],
        'conditional': {'program': {'required': ['label']}},  # label required if using program
    },
    'copy': {'required': ['src', 'dest']},
    'command': {'required': ['args']},
    'install_pkg': {'required': ['path']},
    'systemsetup': {'required': ['items'], 'types': {'items': dict}},
    'npx': {'required': ['package']},
    'audio': {'any_of': ['output', 'input', 'system', 'volume', 'aggregate']},
    'download': {'required': ['url', 'dest']},
    'desktop': {},  # image path is optional (can clear)
    'pmset': {'required': ['settings'], 'types': {'settings': dict}},
    'displayplacer': {'any_of': ['resolution', 'config', 'list']},
    'restart': {},  # no required fields
}


def _validate_entry(i: int, entry: Dict[str, Any], schema: Dict[str, Any]) -> Optional[str]:
    """Validate a single entry against its schema. Returns error message or None."""
    entry_type = entry['type']

    # Check required fields
    for field in schema.get('required', []):
        if field not in entry:
            return f"Entry {i} ({entry_type}) missing '{field}' field"

    # Check one-of requirements (at least one must be present)
    one_of = schema.get('one_of', [])
    if one_of and not any(f in entry for f in one_of):
        return f"Entry {i} ({entry_type}) missing one of: {', '.join(one_of)}"

    # Check any-of requirements (at least one must be present)
    any_of = schema.get('any_of', [])
    if any_of and not any(f in entry for f in any_of):
        return f"Entry {i} ({entry_type}) must specify at least one of: {', '.join(any_of)}"

    # Check type constraints
    for field, expected_type in schema.get('types', {}).items():
        if field in entry and not isinstance(entry[field], expected_type):
            return f"Entry {i} ({entry_type}) '{field}' must be a {expected_type.__name__}"

    # Check nested validation
    for field, nested_schema in schema.get('nested', {}).items():
        if field in entry:
            value = entry[field]
            expected = nested_schema.get('type')
            if expected and not isinstance(value, expected):
                return f"Entry {i} ({entry_type}) '{field}' must be a {expected.__name__}"
            for req in nested_schema.get('required', []):
                if req not in value:
                    return f"Entry {i} ({entry_type}) {field} missing '{req}' field"

    # Check conditional requirements (field X requires field Y)
    for field, cond_schema in schema.get('conditional', {}).items():
        if field in entry:
            for req in cond_schema.get('required', []):
                if req not in entry:
                    return f"Entry {i} ({entry_type}) missing '{req}' field (required with '{field}')"

    return None


def validate_state_entries(state_entries: List[Dict[str, Any]]) -> None:
    """Validate state file entries against handler schemas."""
    for i, entry in enumerate(state_entries):
        if not isinstance(entry, dict):
            typer.echo(f"❌ Error: Entry {i} is not a dictionary", err=True)
            raise typer.Exit(1)
        if 'type' not in entry:
            typer.echo(f"❌ Error: Entry {i} missing 'type' field", err=True)
            raise typer.Exit(1)

        entry_type = entry['type']
        schema = HANDLER_SCHEMAS.get(entry_type, {})
        error = _validate_entry(i, entry, schema)
        if error:
            typer.echo(f"❌ Error: {error}", err=True)
            raise typer.Exit(1)


def get_required_handlers(state_entries: List[Dict[str, Any]]) -> set:
    """Extract unique handler types needed from state entries, including transitive dependencies."""
    handlers = {entry['type'] for entry in state_entries}

    # Recursively resolve dependencies
    def resolve_deps(handler: str, visited: set) -> set:
        if handler in visited:
            return set()
        visited.add(handler)
        deps = set(get_handler_dependencies(handler))
        for dep in list(deps):
            deps.update(resolve_deps(dep, visited))
        return deps

    visited: set = set()
    for handler in list(handlers):
        handlers.update(resolve_deps(handler, visited))

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
        event_type = event.get('event', '')
        data = event.get('event_data', {})

        # Detect step boundaries — each include_tasks fires this
        if event_type == 'playbook_on_task_start':
            task_name = data.get('task', '')
            if task_name in step_names:
                current_step[0] += 1
                idx = current_step[0]
                label = step_label(state_entries[idx])
                typer.echo(f"  [{idx + 1}/{total_steps}] {label}")
            return

        # Track results
        if event_type in ('runner_on_ok', 'runner_on_failed', 'runner_on_skipped',
                          'runner_item_on_ok', 'runner_item_on_failed', 'runner_item_on_skipped'):
            idx = current_step[0]
            if idx < 0 or idx >= len(state_entries):
                return

            task_name = data.get('task', '')
            res = data.get('res', {})

            # Append item label for loop tasks
            if 'item' in res:
                item = res['item']
                if isinstance(item, str):
                    task_name = f"{task_name} ({item})"

            is_failed = event_type in ('runner_on_failed', 'runner_item_on_failed')
            is_changed = res.get('changed', False)

            if is_failed:
                step_has_failed.add(idx)
                status_mark = typer.style('[!]', fg='red')
            elif is_changed:
                step_has_changed.add(idx)
                status_mark = typer.style('[~]', fg='green')
            else:
                status_mark = typer.style('[x]', fg='green')

            # Verbose: print every sub-task
            if verbose:
                typer.echo(f"      {status_mark} {task_name}")

            # Always show failure details with full context
            if is_failed:
                if not verbose:
                    typer.echo(typer.style(f"      [!] {task_name}", fg='red'))

                # Show all useful error fields
                msg = res.get('msg', '')
                stderr = res.get('stderr', '').strip()
                stdout = res.get('stdout', '').strip()
                cmd = res.get('cmd', '')
                rc = res.get('rc')

                if msg:
                    typer.echo(typer.style(f"          Error: {msg}", fg='red'))
                if cmd:
                    if isinstance(cmd, list):
                        cmd = ' '.join(cmd)
                    typer.echo(f"          Command: {cmd}")
                if rc is not None:
                    typer.echo(f"          Exit code: {rc}")
                if stdout:
                    typer.echo(f"          stdout: {stdout[:500]}")
                if stderr:
                    typer.echo(typer.style(f"          stderr: {stderr[:500]}", fg='red'))

                # Show task path for debugging
                task_path = data.get('task_path', '')
                if task_path:
                    typer.echo(f"          Task: {task_path}")

    typer.echo()

    # Pass become password via environment variable
    envvars = {}
    if become_password:
        envvars['ANSIBLE_BECOME_PASS'] = become_password

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
        typer.echo(typer.style(f"  All {ok_count} steps completed successfully", fg='green'))
    else:
        parts = []
        if ok_count > 0:
            parts.append(typer.style(f"{ok_count} ok", fg='green'))
        if failed_count:
            parts.append(typer.style(f"{failed_count} failed", fg='red'))
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
        config = raw.get('config', {})
        state_entries = raw.get('steps', [])
    else:
        typer.echo("❌ Error: State file must contain a list or a dict with 'steps'", err=True)
        raise typer.Exit(1)

    if not isinstance(state_entries, list):
        typer.echo("❌ Error: Steps must be a list of entries", err=True)
        raise typer.Exit(1)

    # Set resources_dir default to state file's directory (absolute)
    # User-specified values are passed through as-is
    if 'resources_dir' not in config:
        config['resources_dir'] = str(state_file.resolve().parent)

    # Always provide cwd - the directory from which `frame install` was invoked
    # Useful for referencing the current project/venv context
    config['cwd'] = str(Path.cwd().resolve())

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
            typer.echo((inventory_dir / 'hosts').read_text())

        result = _run_with_status(
            ansible_dir, cmdline, state_entries, verbose,
            check=check, become_password=become_password
        )

        if result.status == "successful":
            typer.echo()
            typer.echo("✅ Done!")
        elif result.status == "failed":
            typer.echo()
            if not verbose:
                typer.echo("Run with --verbose for detailed error information")
            raise typer.Exit(1)
