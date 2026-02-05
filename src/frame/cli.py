import typer
from pathlib import Path

from frame.install import install as run_install
from frame.server import server_app, run_server

app_cli = typer.Typer()
app_cli.add_typer(server_app, name="server")
app_cli.command("run-server")(run_server)


@app_cli.command()
def install(
    state_file: Path = typer.Argument(..., help="Path to state.yaml file"),
    sudo: bool = typer.Option(False, "--sudo", help="Run with sudo privileges"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    artifacts_only: bool = typer.Option(False, "--artifacts-only", help="Download artifacts only, skip installation"),
):
    """
    Install applications and configure system based on state.yaml file.

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
        path:
          url: https://example.com/App.dmg
          sha256: abc123...

    \b
      - type: download
        url: https://example.com/file.zip
        sha256: def456...
    """
    run_install(state_file=state_file, sudo=sudo, verbose=verbose, artifacts_only=artifacts_only)


if __name__ == "__main__":
    app_cli()
