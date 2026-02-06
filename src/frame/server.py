import os
import shutil
import subprocess
import webbrowser
import typer
import uvicorn
from pathlib import Path
from typing import List, Optional

server_app = typer.Typer(help="Manage the Frame server as a background service")

# --- Constants ---

DEFAULT_SERVICE_NAME = "com.frame.server"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOG_PATH = Path.home() / "Library" / "Logs" / "frame.log"


def _get_plist_path(label: str = DEFAULT_SERVICE_NAME) -> Path:
    return PLIST_DIR / f"{label}.plist"


def _generate_plist(
    host: str,
    port: int,
    log_path: Path,
    config_path: Optional[Path] = None,
    label: str = DEFAULT_SERVICE_NAME,
    stderr_path: Optional[Path] = None,
    run_at_load: bool = True,
    environment: Optional[dict[str, str]] = None,
) -> str:
    uv_path = shutil.which("uv")
    if not uv_path:
        typer.echo("Error: uv not found on PATH", err=True)
        raise typer.Exit(1)

    args = [uv_path, "run", "frame", "run-server", "--host", host, "--port", str(port)]
    if config_path:
        args.extend(["--config", str(config_path)])

    args_xml = "\n".join(f"      <string>{arg}</string>" for arg in args)
    stdout_log = str(log_path)
    stderr_log = str(stderr_path) if stderr_path else stdout_log
    cwd = os.getcwd()
    run_at_load_str = "true" if run_at_load else "false"

    # Build environment section if provided
    env_xml = ""
    if environment:
        env_entries = "\n".join(
            f"      <key>{k}</key>\n      <string>{v}</string>"
            for k, v in environment.items()
        )
        env_xml = f"""
  <key>EnvironmentVariables</key>
  <dict>
{env_entries}
  </dict>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>WorkingDirectory</key>
  <string>{cwd}</string>
  <key>StandardOutPath</key>
  <string>{stdout_log}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_log}</string>
  <key>RunAtLoad</key>
  <{run_at_load_str}/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>{env_xml}
</dict>
</plist>
"""


def _is_loaded(label: str = DEFAULT_SERVICE_NAME) -> tuple[bool, Optional[int]]:
    """Check if the service is loaded. Returns (loaded, pid)."""
    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3 and parts[2] == label:
                    pid = int(parts[0]) if parts[0] != "-" else None
                    return True, pid
            return True, None
        return False, None
    except FileNotFoundError:
        return False, None


def _stop_service(label: str = DEFAULT_SERVICE_NAME) -> bool:
    """Unload the service and remove the plist. Returns True if it was running."""
    plist_path = _get_plist_path(label)
    was_loaded, _ = _is_loaded(label)
    if was_loaded:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    if plist_path.exists():
        plist_path.unlink()
    return was_loaded


# --- Foreground command (registered on parent app via cli.py) ---

def _open_browser(host: str, port: int):
    url = f"http://{'localhost' if host == '0.0.0.0' else host}:{port}"
    webbrowser.open(url)


def run_server(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config yaml"),
    open: bool = typer.Option(False, "--open", help="Open in browser after starting"),
):
    """Run the FastAPI server in the foreground (used by launchd)."""
    if config:
        os.environ["FRAME_CONFIG"] = str(config)
        typer.echo(f"Config: {config}")
    if open:
        _open_browser(host, port)
    uvicorn.run(
        "frame.main:app",
        host=host,
        port=port,
        reload=True,
        reload_includes=["*.yaml", "*.py"],
        reload_dirs=["examples", "src/frame"],
    )


# --- Subcommands ---

@server_app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    log_path: Path = typer.Option(DEFAULT_LOG_PATH, "--log-path", help="Log file path"),
    config: Optional[Path] = typer.Option(None, help="Path to config yaml"),
    label: str = typer.Option(DEFAULT_SERVICE_NAME, "--label", help="Service label for launchd"),
    env: Optional[List[str]] = typer.Option(None, "--env", "-e", help="Environment variables (KEY=VALUE)"),
    open: bool = typer.Option(False, "--open", help="Open in browser after starting"),
):
    """Start the server as a background service via launchd."""
    loaded, _ = _is_loaded(label)
    if loaded:
        typer.echo("Server already running, restarting...")
        _stop_service(label)

    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    # Parse environment variables from KEY=VALUE format
    environment = None
    if env:
        environment = {}
        for item in env:
            if '=' in item:
                key, value = item.split('=', 1)
                environment[key] = value
            else:
                typer.echo(f"Warning: ignoring invalid env format: {item} (expected KEY=VALUE)", err=True)

    plist_content = _generate_plist(host, port, log_path, config, label=label, environment=environment)
    plist_path = _get_plist_path(label)
    plist_path.write_text(plist_content)

    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"Failed to load service: {result.stderr.strip()}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Server started on {host}:{port}")
    if config:
        typer.echo(f"  Config: {config}")
    typer.echo(f"  Label: {label}")
    typer.echo(f"  Log: {log_path}")
    typer.echo(f"  Plist: {plist_path}")

    if open:
        _open_browser(host, port)


@server_app.command()
def stop(
    label: str = typer.Option(DEFAULT_SERVICE_NAME, "--label", help="Service label"),
):
    """Stop the background server."""
    was_running = _stop_service(label)
    if was_running:
        typer.echo("Server stopped.")
    else:
        typer.echo("Server was not running.")


@server_app.command()
def restart(
    label: str = typer.Option(DEFAULT_SERVICE_NAME, "--label", help="Service label"),
):
    """Restart the background server (unload + load existing plist)."""
    plist_path = _get_plist_path(label)
    if not plist_path.exists():
        typer.echo("No plist found. Use 'frame server start' first.", err=True)
        raise typer.Exit(1)

    loaded, _ = _is_loaded(label)
    if loaded:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    typer.echo("Server restarted.")


@server_app.command("status")
def server_status(
    label: str = typer.Option(DEFAULT_SERVICE_NAME, "--label", help="Service label"),
):
    """Show server status."""
    loaded, pid = _is_loaded(label)
    plist_path = _get_plist_path(label)

    if loaded:
        typer.echo(f"Server: running (PID {pid})" if pid else "Server: running")
    else:
        typer.echo("Server: stopped")

    typer.echo(f"  Label: {label}")
    if plist_path.exists():
        typer.echo(f"  Plist: {plist_path}")
    typer.echo(f"  Default log: {DEFAULT_LOG_PATH}")


@server_app.command("log")
def server_log(
    path: bool = typer.Option(False, "--path", help="Just print the log file path"),
    log_path: Path = typer.Option(DEFAULT_LOG_PATH, "--log-path", help="Log file path"),
):
    """Stream or locate the server log file."""
    if path:
        typer.echo(str(log_path))
        return

    if not log_path.exists():
        typer.echo(f"Log file not found: {log_path}", err=True)
        typer.echo("Is the server running? Start it with: frame server start")
        raise typer.Exit(1)

    os.execvp("tail", ["tail", "-f", str(log_path)])
