import os
import shutil
import subprocess
import webbrowser
import typer
import uvicorn
from pathlib import Path
from typing import Optional

server_app = typer.Typer(help="Manage the Frame server as a background service")

# --- Constants ---

SERVICE_NAME = "com.frame.server"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOG_PATH = Path.home() / "Library" / "Logs" / "frame.log"
DEFAULT_APP_PATH = Path("/Applications/Frame.app")


def _get_plist_path() -> Path:
    return PLIST_DIR / f"{SERVICE_NAME}.plist"


def _generate_plist(host: str, port: int, log_path: Path, config_path: Optional[Path] = None, sudo_password: Optional[str] = None, app_path: Optional[Path] = None) -> str:
    if app_path:
        executable = app_path / "Contents" / "MacOS" / "Frame"
        if not executable.exists():
            typer.echo(f"Error: {executable} not found. Run 'frame package' first.", err=True)
            raise typer.Exit(1)
        frame_path = str(executable)
    else:
        frame_path = shutil.which("frame")
        if not frame_path:
            typer.echo("Error: frame not found on PATH", err=True)
            raise typer.Exit(1)

    args = [frame_path, "run-server", "--host", host, "--port", str(port)]
    if config_path:
        args.extend(["--config", str(config_path)])
    if sudo_password:
        args.extend(["--sudo-password", sudo_password])

    args_xml = "\n".join(f"      <string>{arg}</string>" for arg in args)
    log = str(log_path)
    cwd = os.getcwd()

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{SERVICE_NAME}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>WorkingDirectory</key>
  <string>{cwd}</string>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>
</dict>
</plist>
"""


def _is_loaded() -> tuple[bool, Optional[int]]:
    """Check if the service is loaded. Returns (loaded, pid)."""
    try:
        result = subprocess.run(
            ["launchctl", "list", SERVICE_NAME],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3 and parts[2] == SERVICE_NAME:
                    pid = int(parts[0]) if parts[0] != "-" else None
                    return True, pid
            return True, None
        return False, None
    except FileNotFoundError:
        return False, None


def _stop_service() -> bool:
    """Unload the service and remove the plist. Returns True if it was running."""
    plist_path = _get_plist_path()
    was_loaded, _ = _is_loaded()
    # Always attempt unload if plist exists (covers stale plists from previous boots)
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
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
    sudo_password: Optional[str] = typer.Option(None, "--sudo-password", help="Password for sudo commands (sets SUDO_PASSWORD env var)"),
):
    """Run the FastAPI server in the foreground (used by launchd)."""
    if sudo_password:
        os.environ["SUDO_PASSWORD"] = sudo_password
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
        timeout_graceful_shutdown=3,
    )


# --- Subcommands ---


@server_app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    log_path: Path = typer.Option(DEFAULT_LOG_PATH, "--log-path", help="Log file path"),
    config: Optional[Path] = typer.Option(None, help="Path to config yaml"),
    open: bool = typer.Option(False, "--open", help="Open in browser after starting"),
    sudo_password: Optional[str] = typer.Option(None, "--sudo-password", help="Password for sudo commands"),
    app: Optional[Path] = typer.Option(None, "--app", help="Run via Frame.app bundle for TCC permissions (default: /Applications/Frame.app)"),
):
    """Start the server as a background service via launchd."""
    # Always stop and clean up any existing service before starting
    _stop_service()

    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()

    plist_content = _generate_plist(host, port, log_path, config, sudo_password, app_path=app)
    plist_path = _get_plist_path()
    plist_path.write_text(plist_content)

    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if result.returncode != 0:
        typer.echo(f"Failed to load service: {result.stderr.strip()}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Server started on {host}:{port}")
    if config:
        typer.echo(f"  Config: {config}")
    typer.echo(f"  Log: {log_path}")
    typer.echo(f"  Plist: {plist_path}")

    if open:
        _open_browser(host, port)


@server_app.command()
def stop():
    """Stop the background server."""
    was_running = _stop_service()
    if was_running:
        typer.echo("Server stopped.")
    else:
        typer.echo("Server was not running.")



@server_app.command("status")
def server_status():
    """Show server status."""
    loaded, pid = _is_loaded()
    plist_path = _get_plist_path()

    if loaded:
        typer.echo(f"Server: running (PID {pid})" if pid else "Server: running")
    else:
        typer.echo("Server: stopped")

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
