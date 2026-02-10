import typer
from pathlib import Path

from frame.install import install as run_install
from frame.server import server_app, run_server
from frame.package import package as package_cmd

app_cli = typer.Typer()
app_cli.add_typer(server_app, name="server")
app_cli.command("run-server")(run_server)
app_cli.command("package")(package_cmd)


@app_cli.command()
def install(
    state_file: Path = typer.Argument(..., help="Path to state.yaml file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    artifacts_only: bool = typer.Option(False, "--artifacts-only", help="Download artifacts only, skip installation"),
    check: bool = typer.Option(False, "--check", help="Dry run — show what would change without making changes"),
    diff: bool = typer.Option(False, "--diff", help="Show file diffs (useful with --check)"),
    list_tasks: bool = typer.Option(False, "--list-tasks", help="List all tasks without executing"),
    ask_become_pass: bool = typer.Option(False, "-K", "--ask-become-pass", help="Prompt for sudo password (for steps that need privilege escalation)"),
    host: str = typer.Option(None, "--host", "-H", help="Remote host to run on (user@hostname). Uses SSH."),
):
    """
    Install applications and configure system based on state.yaml file.

    Privilege escalation (sudo) is handled per-task via the 'sudo' field in step
    definitions or automatically based on target paths (e.g. /Applications).

    \b
    Remote execution:
      frame install state.yaml --host user@192.168.1.50
      frame install state.yaml -H admin@server.local -K

    State file can be a flat list (legacy) or a dict with config and steps:

    \b
    config:
      resources_dir: ./resources

    \b
    steps:
      - type: install_app
        path: SuperCollider.app

    \b
      - type: install_app
        remote:
          url: https://example.com/App.dmg
          sha256: abc123...

    \b
      - type: download
        url: https://example.com/file.zip
        sha256: def456...
    """
    run_install(
        state_file=state_file,
        verbose=verbose,
        artifacts_only=artifacts_only,
        check=check,
        diff=diff,
        list_tasks=list_tasks,
        ask_become_pass=ask_become_pass,
        host=host,
    )


if __name__ == "__main__":
    app_cli()
