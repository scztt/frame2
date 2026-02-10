"""Build a macOS .app bundle for Frame.

On macOS Tahoe+, screen recording and disk access permissions require the
calling binary to live inside an app bundle.  This command creates a minimal
Frame.app whose executable is a thin shell wrapper that execs the real
``frame`` binary, so you can grant Frame.app the necessary TCC permissions.

Usage:
    frame package                           # -> /Applications/Frame.app
    frame package --dest ~/Desktop          # -> ~/Desktop/Frame.app
    frame package --sign                    # ad-hoc codesign after creation
"""

import os
import shutil
import subprocess
import stat
import typer
from pathlib import Path
from typing import Optional

BUNDLE_NAME = "Frame"
BUNDLE_ID = "com.frame.server"
BUNDLE_VERSION = "1.0"

ICON_FILE = "Frame.icns"

INFO_PLIST = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{BUNDLE_NAME}</string>
  <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
  <key>CFBundleVersion</key><string>{BUNDLE_VERSION}</string>
  <key>CFBundleShortVersionString</key><string>{BUNDLE_VERSION}</string>
  <key>CFBundleExecutable</key><string>{BUNDLE_NAME}</string>
  <key>CFBundleIconFile</key><string>{ICON_FILE}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSBackgroundOnly</key><true/>
</dict>
</plist>
"""


def _find_frame_binary() -> str:
    """Resolve the real frame binary path."""
    path = shutil.which("frame")
    if not path:
        typer.echo("Error: frame not found on PATH", err=True)
        raise typer.Exit(1)
    return path


def _make_executable(path: Path):
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def package(
    dest: Optional[Path] = typer.Option(None, "--dest", help="Parent directory for Frame.app (default: /Applications)"),
    sign: bool = typer.Option(False, "--sign", help="Ad-hoc codesign the bundle after creation"),
):
    """Create a macOS .app bundle that wraps the frame CLI.

    This lets you grant Frame screen-recording and full-disk-access
    permissions in System Settings > Privacy & Security.
    """
    frame_bin = _find_frame_binary()

    dest_dir = dest or Path("/Applications")
    app_path = dest_dir / f"{BUNDLE_NAME}.app"
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources_dir = contents / "Resources"

    # Clean up existing bundle
    if app_path.exists():
        typer.echo(f"Removing existing {app_path}")
        shutil.rmtree(app_path)

    # Create skeleton
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    # Write Info.plist
    (contents / "Info.plist").write_text(INFO_PLIST)

    # Copy icon if available
    icon_src = Path(__file__).parent / "static" / ICON_FILE
    if icon_src.exists():
        shutil.copy2(icon_src, resources_dir / ICON_FILE)

    # Write executable wrapper
    executable = macos_dir / BUNDLE_NAME
    executable.write_text(f"""\
#!/bin/zsh
# Frame.app wrapper — execs the real frame binary with all arguments.
# This exists so macOS can grant screen-recording / disk-access to the bundle.
exec "{frame_bin}" "$@"
""")
    _make_executable(executable)

    typer.echo(f"Created {app_path}")
    typer.echo(f"  Executable: {executable}")
    typer.echo(f"  Wraps: {frame_bin}")

    # Optional codesign
    if sign:
        typer.echo("  Signing...")
        result = subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            typer.echo("  Signed (ad-hoc)")
        else:
            typer.echo(f"  Warning: codesign failed: {result.stderr.strip()}", err=True)

    typer.echo()
    typer.echo("Next steps:")
    typer.echo("  1. Open System Settings > Privacy & Security > Screen Recording")
    typer.echo(f"  2. Add {app_path}")
    typer.echo("  3. Restart the Frame server")
