"""Main installer logic for Frame install command."""

import typer
import yaml
import ansible_runner
from pathlib import Path
import tempfile
from typing import List, Dict, Any

from .generators import (
    get_static_site_yml,
    generate_plan_yml,
    generate_ansible_cfg,
    generate_inventory,
    get_handler_generator,
    get_handler_dependencies,
)


def validate_state_entries(state_entries: List[Dict[str, Any]]) -> None:
    """Validate state file entries and raise typer.Exit on errors."""
    for i, entry in enumerate(state_entries):
        if not isinstance(entry, dict):
            typer.echo(f"❌ Error: Entry {i} is not a dictionary", err=True)
            raise typer.Exit(1)
        if 'type' not in entry:
            typer.echo(f"❌ Error: Entry {i} missing 'type' field", err=True)
            raise typer.Exit(1)

        # Type-specific validation
        entry_type = entry['type']

        if entry_type == 'install_app':
            has_path = 'path' in entry
            has_remote = 'remote' in entry
            if not has_path and not has_remote:
                typer.echo(f"❌ Error: Entry {i} (install_app) missing 'path' or 'remote' field", err=True)
                raise typer.Exit(1)
            if has_remote:
                if not isinstance(entry['remote'], dict):
                    typer.echo(f"❌ Error: Entry {i} (install_app) 'remote' must be a dict with 'url'", err=True)
                    raise typer.Exit(1)
                if 'url' not in entry['remote']:
                    typer.echo(f"❌ Error: Entry {i} (install_app) remote missing 'url' field", err=True)
                    raise typer.Exit(1)

        elif entry_type == 'defaults':
            if 'items' not in entry:
                typer.echo(f"❌ Error: Entry {i} (defaults) missing 'items' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry['items'], list):
                typer.echo(f"❌ Error: Entry {i} (defaults) 'items' must be a list", err=True)
                raise typer.Exit(1)

        elif entry_type == 'homebrew':
            if 'packages' not in entry:
                typer.echo(f"❌ Error: Entry {i} (homebrew) missing 'packages' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry['packages'], list):
                typer.echo(f"❌ Error: Entry {i} (homebrew) 'packages' must be a list", err=True)
                raise typer.Exit(1)

        elif entry_type == 'launchctl':
            if 'name' not in entry:
                typer.echo(f"❌ Error: Entry {i} (launchctl) missing 'name' field", err=True)
                raise typer.Exit(1)
            if 'program' not in entry:
                typer.echo(f"❌ Error: Entry {i} (launchctl) missing 'program' field", err=True)
                raise typer.Exit(1)

        elif entry_type == 'copy':
            if 'src' not in entry:
                typer.echo(f"❌ Error: Entry {i} (copy) missing 'src' field", err=True)
                raise typer.Exit(1)
            if 'dest' not in entry:
                typer.echo(f"❌ Error: Entry {i} (copy) missing 'dest' field", err=True)
                raise typer.Exit(1)

        elif entry_type == 'command':
            if 'args' not in entry:
                typer.echo(f"❌ Error: Entry {i} (command) missing 'args' field", err=True)
                raise typer.Exit(1)

        elif entry_type == 'install_pkg':
            if 'path' not in entry:
                typer.echo(f"❌ Error: Entry {i} (install_pkg) missing 'path' field", err=True)
                raise typer.Exit(1)

        elif entry_type == 'systemsetup':
            if 'items' not in entry:
                typer.echo(f"❌ Error: Entry {i} (systemsetup) missing 'items' field", err=True)
                raise typer.Exit(1)
            if not isinstance(entry['items'], dict):
                typer.echo(f"❌ Error: Entry {i} (systemsetup) 'items' must be a dictionary", err=True)
                raise typer.Exit(1)

        elif entry_type == 'npx':
            if 'package' not in entry:
                typer.echo(f"❌ Error: Entry {i} (npx) missing 'package' field", err=True)
                raise typer.Exit(1)

        elif entry_type == 'audio':
            has_config = any(k in entry for k in ('output', 'input', 'system', 'volume', 'aggregate'))
            if not has_config:
                typer.echo(f"❌ Error: Entry {i} (audio) must specify at least one of: output, input, system, volume, aggregate", err=True)
                raise typer.Exit(1)

        elif entry_type == 'download':
            if 'url' not in entry:
                typer.echo(f"❌ Error: Entry {i} (download) missing 'url' field", err=True)
                raise typer.Exit(1)


def get_required_handlers(state_entries: List[Dict[str, Any]]) -> set:
    """Extract unique handler types needed from state entries, including dependencies."""
    handlers = {entry['type'] for entry in state_entries}
    # Resolve dependencies declared in handler metadata
    for handler in list(handlers):
        deps = get_handler_dependencies(handler)
        handlers.update(deps)
    return handlers


def format_summary_line(entry: Dict[str, Any], index: int) -> str:
    """Format a single summary line for an entry."""
    entry_type = entry['type']

    if entry_type == 'install_app':
        if 'remote' in entry:
            app_name = entry['remote']['url'].split('/')[-1]
        else:
            app_name = Path(entry['path']).name
        location = entry.get('install_location', '/Applications')
        return f"  {index}. Installed {app_name} → {location}"

    elif entry_type == 'defaults':
        count = len(entry.get('items', []))
        return f"  {index}. Applied {count} macOS defaults setting(s)"

    elif entry_type == 'homebrew':
        count = len(entry.get('packages', []))
        packages = ', '.join(entry.get('packages', [])[:3])
        if len(entry.get('packages', [])) > 3:
            packages += '...'
        return f"  {index}. Installed {count} Homebrew package(s): {packages}"

    elif entry_type == 'launchctl':
        service_name = entry.get('name', 'unknown')
        loaded = entry.get('loaded', True)
        started = entry.get('started', True)
        status = []
        if loaded:
            status.append('loaded')
        if started:
            status.append('started')
        status_str = ', '.join(status) if status else 'configured'
        return f"  {index}. Service {service_name} ({status_str})"

    elif entry_type == 'systemsetup':
        count = len(entry.get('items', {}))
        return f"  {index}. Configured {count} system setting(s)"

    elif entry_type == 'npx':
        package = entry.get('package', 'unknown')
        return f"  {index}. Ran npx {package}"

    elif entry_type == 'audio':
        parts = []
        if 'output' in entry:
            parts.append(f"output={entry['output']}")
        if 'input' in entry:
            parts.append(f"input={entry['input']}")
        if 'system' in entry:
            parts.append(f"system={entry['system']}")
        if 'volume' in entry:
            parts.append(f"{len(entry['volume'])} volume(s)")
        if 'aggregate' in entry:
            parts.append(f"{len(entry['aggregate'])} aggregate(s)")
        return f"  {index}. Audio: {', '.join(parts)}"

    elif entry_type == 'download':
        url = entry.get('url', 'unknown')
        return f"  {index}. Downloaded {url.split('/')[-1]}"

    else:
        return f"  {index}. Executed {entry_type}"


def install(
    state_file: Path,
    sudo: bool = False,
    verbose: bool = False,
    artifacts_only: bool = False,
) -> None:
    """
    Execute installation based on state.yaml file.

    This is the main installer function that:
    1. Reads and validates state.yaml
    2. Generates ansible playbooks (site.yml, plan.yml, handlers)
    3. Executes via ansible-runner
    4. Reports results
    """
    typer.echo("📦 Frame Installer")
    typer.echo(f"Reading state from: {state_file}")

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

    # Resolve resources_dir to absolute path relative to state file
    resources_dir = config.get('resources_dir', './resources')
    config['resources_dir'] = str((state_file.resolve().parent / resources_dir).resolve())

    typer.echo(f"Found {len(state_entries)} installation step(s)")
    if artifacts_only:
        typer.echo("Mode: artifacts only (download without install)")

    # Validate entries
    validate_state_entries(state_entries)

    # Get required handlers
    required_handlers = get_required_handlers(state_entries)

    # Create temporary ansible directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        ansible_dir = Path(tmpdir) / "ansible"
        ansible_dir.mkdir()

        types_dir = ansible_dir / "types"
        types_dir.mkdir()

        typer.echo("⚙️  Generating ansible playbooks...")

        # Generate static site.yml (canonical dispatcher)
        (ansible_dir / "site.yml").write_text(get_static_site_yml())

        # Generate plan.yml with actual steps and config
        (ansible_dir / "plan.yml").write_text(generate_plan_yml(state_entries, config))

        # Generate config files
        (ansible_dir / "ansible.cfg").write_text(generate_ansible_cfg())
        (ansible_dir / "inventory.ini").write_text(generate_inventory())

        # Generate required type handlers
        for handler_type in required_handlers:
            try:
                handler_generator = get_handler_generator(handler_type)
                handler_content = handler_generator()
                (types_dir / f"{handler_type}.yml").write_text(handler_content)
            except ValueError as e:
                typer.echo(f"❌ Error: {e}", err=True)
                raise typer.Exit(1)

        # Set tag filtering for artifacts-only mode
        if artifacts_only:
            env_dir = ansible_dir / "env"
            env_dir.mkdir(exist_ok=True)
            (env_dir / "cmdline").write_text("--tags artifact")

        typer.echo("🚀 Executing installation...")
        if verbose:
            typer.echo(f"   Working directory: {ansible_dir}")

        # Run ansible playbook using ansible-runner
        result = ansible_runner.run(
            private_data_dir=str(ansible_dir),
            playbook="site.yml",
            verbosity=2 if verbose else 0,
            quiet=not verbose,
        )

        # Report results
        typer.echo()
        if result.status == "successful":
            typer.echo("✅ Installation completed successfully!")
            typer.echo()

            # Show summary
            typer.echo("Summary:")
            for i, entry in enumerate(state_entries, 1):
                typer.echo(format_summary_line(entry, i))

        elif result.status == "failed":
            typer.echo("❌ Installation failed!", err=True)
            typer.echo()

            if verbose or result.stats:
                typer.echo("Error details:")
                if result.stats and 'failures' in result.stats.get('localhost', {}):
                    typer.echo(f"  Failed tasks: {result.stats['localhost']['failures']}")

            typer.echo()
            typer.echo("Run with --verbose for detailed error information")
            raise typer.Exit(1)

        else:
            typer.echo(f"⚠️  Installation ended with status: {result.status}", err=True)
            raise typer.Exit(1)
