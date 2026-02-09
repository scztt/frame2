"""
Data sources for the action-based observable system.

Sources are data producers that can be triggered to fetch data and notify subscribers.
Each source has a Settings dataclass for configuration and a run() method to execute.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import subprocess
import asyncio
import os

from frame.parsers import make_parser
from frame.utility import tail_lines
from frame.images import image_repo
from frame.registry import TypeRegistry
from frame.shell import run_command

# === Base and Registry ===


class SourceBase:
    """Base class for all sources."""

    def __init_subclass__(cls, name: str, settings: type):
        """Auto-register subclasses with the registry."""
        super().__init_subclass__()
        cls.name = name
        cls.settings_type = settings
        sources.register(name, cls)

    def run(self) -> Any:
        """Execute the source and return result."""
        raise NotImplementedError

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """Subscribe to source outputs."""
        raise NotImplementedError


sources = TypeRegistry[SourceBase]("source")


def make_source(settings: Dict[str, Any] | str) -> Tuple[SourceBase, Dict[str, Any]]:
    """
    Create a source from settings dict or string.

    Args:
        settings: Dict with 'type' key, or string type name

    Returns:
        Tuple of (source instance, resolved settings dict)

    Example:
        source, _ = make_source({"type": "shell", "command": "date"})
        source, _ = make_source("shell")
    """
    return sources.make(settings)


# === ShellSource ===


@dataclass
class ShellSourceSettings:
    """Settings for ShellSource."""

    command: Union[str, List[str]]
    parser: Optional[str | Dict[str, Any]] = None
    sudo: bool = False


class ShellSource(SourceBase, name="shell", settings=ShellSourceSettings):
    """
    Source that executes shell commands and notifies subscribers with results.

    The parser (if provided) pre-processes output before notifying subscribers.

    Example:
        # Simple shell source
        settings = ShellSourceSettings(command='date')
        shell = ShellSource(settings)
        shell.subscribe(lambda result: print(result))
        shell.run()

        # With parser and sudo
        settings = ShellSourceSettings(
            command='cat /etc/hosts',
            parser='string',
            sudo=True
        )
        shell = ShellSource(settings)
        shell.subscribe(lambda result: print(result))
        shell.run()
    """

    def __init__(self, settings: ShellSourceSettings):
        """
        Initialize ShellSource.

        Args:
            settings: ShellSource configuration
        """
        self.settings = settings
        self.command = settings.command
        self.sudo = settings.sudo
        self.subscribers: List[Callable[[Any], None]] = []

        # Initialize parser if provided
        if settings.parser is not None:
            self.parser, _ = make_parser(settings.parser)
        else:
            self.parser = None

    def run(self) -> Any:
        """
        Execute the shell command and notify subscribers with the result.

        Returns:
            Command output (parsed if parser is configured, otherwise raw string)
        """
        # Use run_command from shell.py which handles both string and list commands
        output = asyncio.run(run_command(self.command, sudo=self.sudo))
        output = output.strip()

        # Apply parser if configured
        if self.parser is not None:
            output = self.parser(output)

        for subscriber in self.subscribers:
            try:
                subscriber(output)
            except Exception as e:
                print(f"Error in ShellSource subscriber: {e}")

        return output

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to shell command results.

        Args:
            callback: Function called with command output (parsed or raw)
        """
        self.subscribers.append(callback)


# === TailSource ===


@dataclass
class TailSourceSettings:
    """Settings for TailSource."""

    path: str
    lines: int = 100


class TailSource(SourceBase, name="tail", settings=TailSourceSettings):
    """
    Source that reads the tail of a file and notifies subscribers when it changes.

    Tracks file modification time to avoid unnecessary reads.
    Only notifies subscribers when the file content actually changes.

    Example:
        settings = TailSourceSettings(path='/var/log/app.log', lines=50)
        tail = TailSource(settings)
        tail.subscribe(lambda content: print(content))
        tail.run()  # Read and notify if file changed
    """

    def __init__(self, settings: TailSourceSettings):
        """
        Initialize TailSource.

        Args:
            settings: TailSource configuration
        """
        self.settings = settings
        self.path = settings.path
        self.lines = settings.lines
        self.subscribers: List[Callable[[str], None]] = []

        # Track modification time and last value to avoid unnecessary reads
        self.mod_time = 0.0
        self.last_value = ""

    def run(self) -> str:
        """
        Check file modification time and read tail if changed.

        Returns:
            File tail content (cached if file hasn't changed)
        """
        try:
            current_mod_time = os.path.getmtime(self.path)

            # Only read if file was modified
            if current_mod_time > self.mod_time:
                self.mod_time = current_mod_time
                self.last_value = tail_lines(self.path, self.lines)

                # Notify subscribers of new content
                for subscriber in self.subscribers:
                    try:
                        subscriber(self.last_value)
                    except Exception as e:
                        print(f"Error in TailSource subscriber: {e}")

            return self.last_value

        except FileNotFoundError:
            error_msg = f"File not found: {self.path}"
            print(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Error reading file {self.path}: {e}"
            print(error_msg)
            return error_msg

    def subscribe(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to file tail updates.

        Args:
            callback: Function called with file content when it changes
        """
        self.subscribers.append(callback)


# === ScreenshotSource ===


@dataclass
class ScreenshotSourceSettings:
    """Settings for ScreenshotSource."""

    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    sudo: bool = False
    id: str = "screenshot"


class ScreenshotSource(SourceBase, name="screenshot", settings=ScreenshotSourceSettings):
    """
    Source that captures screenshots and notifies subscribers with image references.

    Can capture full screen or a specific region if x, y, width, height are provided.

    Example:
        # Full screen capture
        settings = ScreenshotSourceSettings()
        screenshot = ScreenshotSource(settings)
        screenshot.subscribe(lambda ref: print(f"Saved to: {ref.path}"))
        screenshot.run()

        # Region capture
        settings = ScreenshotSourceSettings(x=0, y=0, width=800, height=600)
        screenshot = ScreenshotSource(settings)
        screenshot.subscribe(lambda ref: print(f"Region saved to: {ref.path}"))
        screenshot.run()
    """

    def __init__(self, settings: ScreenshotSourceSettings):
        """
        Initialize ScreenshotSource.

        Args:
            settings: ScreenshotSource configuration
        """
        self.settings = settings
        self.x = settings.x
        self.y = settings.y
        self.width = settings.width
        self.height = settings.height
        self.sudo = settings.sudo
        self.id = settings.id
        self.subscribers: List[Callable[[Any], None]] = []

    def run(self) -> Any:
        """
        Capture screenshot and notify subscribers with image reference.

        Returns:
            Image reference object with path to saved screenshot
        """
        ref = image_repo.make_image_ref(self.id + ".png")

        # Region capture if coordinates provided
        if self.x is not None and self.y is not None and self.width is not None and self.height is not None:
            result = subprocess.run(
                [
                    "screencapture",
                    "-R",
                    f"{self.x},{self.y},{self.width},{self.height}",
                    ref.path,
                ],
                capture_output=True,
                text=True,
            )
        else:
            # Full screen capture
            result = subprocess.run(["screencapture", ref.path], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Screenshot failed: {result.stderr}")

        # Notify subscribers with image reference
        for subscriber in self.subscribers:
            try:
                subscriber(ref)
            except Exception as e:
                print(f"Error in ScreenshotSource subscriber: {e}")

        return ref

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to screenshot captures.

        Args:
            callback: Function called with image reference
        """
        self.subscribers.append(callback)


# === OSCSource ===


@dataclass
class OSCSourceSettings:
    """Settings for OSCSource."""

    port: int
    address: str  # OSC address pattern like "/control/volume"
    ip: str = "0.0.0.0"  # Listen on all interfaces by default
    value_index: Optional[int] = None  # Extract single value at index


class OSCSource(SourceBase, name="osc", settings=OSCSourceSettings):
    """
    Source that listens for OSC (Open Sound Control) messages.

    Starts a UDP server listening for OSC messages on the specified port and address.
    When messages are received, notifies subscribers with the value(s).

    Example:
        settings = OSCSourceSettings(
            port=8000,
            address="/control/volume",
            value_index=0  # Extract first value
        )
        source = OSCSource(settings)
        source.subscribe(lambda value: print(f"Received: {value}"))
        source.run()  # Start listening
    """

    def __init__(self, settings: OSCSourceSettings):
        """
        Initialize OSCSource.

        Args:
            settings: OSC configuration
        """
        self.settings = settings
        self.port = settings.port
        self.address = settings.address
        self.ip = settings.ip
        self.value_index = settings.value_index
        self.subscribers: List[Callable[[Any], None]] = []
        self.server = None
        self.server_thread = None

    def run(self) -> None:
        """
        Start OSC server listening for messages.

        Runs the server in a background thread. Messages matching the address
        pattern will trigger subscriber callbacks.
        """
        if self.server is not None:
            print(f"OSCSource already running on {self.ip}:{self.port}")
            return

        import threading
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.osc_server import BlockingOSCUDPServer

        # Set up dispatcher with our address handler
        dispatcher = Dispatcher()
        dispatcher.map(self.address, self._handle_message)

        # Create server
        self.server = BlockingOSCUDPServer((self.ip, self.port), dispatcher)

        # Run server in background thread
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True, name=f"OSCSource-{self.port}")
        self.server_thread.start()

        print(f"OSCSource listening on {self.ip}:{self.port} for {self.address}")

    def _handle_message(self, address: str, *args) -> None:
        """
        Handle incoming OSC message.

        Args:
            address: OSC address pattern
            *args: OSC message arguments
        """
        # Extract value based on settings
        if self.value_index is not None:
            # Extract single value at index
            if len(args) > self.value_index:
                value = args[self.value_index]
            else:
                value = None
        else:
            # Return all values as list
            value = list(args)

        # Notify subscribers
        for subscriber in self.subscribers:
            try:
                subscriber(value)
            except Exception as e:
                print(f"Error in OSCSource subscriber: {e}")

    def stop(self) -> None:
        """Stop the OSC server."""
        if self.server is not None:
            self.server.shutdown()
            self.server = None
            self.server_thread = None
            print(f"OSCSource stopped on {self.ip}:{self.port}")

    def subscribe(self, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to OSC messages.

        Args:
            callback: Function called with message value(s)
        """
        self.subscribers.append(callback)
