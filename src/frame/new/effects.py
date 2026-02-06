"""
Effects for the action-based observable system.

Effects are side-effect producers (outputs) that are triggered by observable changes.
Each effect has a Settings dataclass for configuration and is callable to execute the effect.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import asyncio
import jinja2

from frame.registry import TypeRegistry
from frame.renderers import make_renderer, RendererBase
from frame.shell import run_command
from frame.parsers import make_parser
from pythonosc import udp_client


# === Base and Registry ===

class EffectBase:
    """Base class for all effects."""

    def __init_subclass__(cls, name: str, settings: type):
        """Auto-register subclasses with the registry."""
        super().__init_subclass__()
        cls.name = name
        cls.settings_type = settings
        effects.register(name, cls)

    def __call__(self, value: Any) -> None:
        """
        Execute the effect with the given value.

        Args:
            value: Input value to process and use for the effect
        """
        raise NotImplementedError


effects = TypeRegistry[EffectBase]("effect")


def make_effect(settings: Dict[str, Any] | str) -> Tuple[EffectBase, Dict[str, Any]]:
    """
    Create an effect from settings dict or string.

    Args:
        settings: Dict with 'type' key, or string type name

    Returns:
        Tuple of (effect instance, resolved settings dict)

    Example:
        effect, _ = make_effect({"type": "file_write", "path": "/tmp/out.txt"})
        effect({"message": "hello"})
    """
    return effects.make(settings)


# === ShellEffect ===

@dataclass
class ShellEffectSettings:
    """Settings for ShellEffect."""
    command: Union[str, List[str]]
    sudo: bool = False
    renderer: Optional[str | Dict[str, Any]] = None


class ShellEffect(EffectBase, name="shell", settings=ShellEffectSettings):
    """
    Effect that executes shell commands.

    The renderer (if provided) processes the input value before passing to the command.

    Example:
        settings = ShellEffectSettings(command="echo {message}")
        effect = ShellEffect(settings)
        effect({"message": "hello"})
    """

    def __init__(self, settings: ShellEffectSettings):
        """
        Initialize ShellEffect.

        Args:
            settings: ShellEffect configuration
        """
        self.settings = settings
        self.command = settings.command
        self.sudo = settings.sudo

        # Initialize renderer if provided
        if settings.renderer is not None:
            self.renderer, _ = make_renderer(settings.renderer)
        else:
            self.renderer = None

    def __call__(self, value: Any) -> None:
        """
        Execute the shell command with the given value.

        Args:
            value: Input value (processed by renderer if configured)
        """
        # Apply renderer if configured
        if self.renderer is not None:
            rendered_value = self.renderer(value)
        else:
            rendered_value = str(value) if not isinstance(value, str) else value

        # If command is a template string, render it with the value
        if isinstance(self.command, str) and "{" in self.command:
            if isinstance(value, dict):
                template = jinja2.Template(self.command)
                command = template.render(**value)
            else:
                command = self.command.format(value=value)
        else:
            command = self.command

        # Execute command synchronously (wrapping async run_command)
        asyncio.run(run_command(command, sudo=self.sudo))


# === FileWriteEffect ===

@dataclass
class FileWriteEffectSettings:
    """Settings for FileWriteEffect."""
    path: str
    template: str
    append: bool = False
    renderer: Optional[str | Dict[str, Any]] = None


class FileWriteEffect(EffectBase, name="file_write", settings=FileWriteEffectSettings):
    """
    Effect that writes to files using Jinja2 templates.

    The template is rendered with the input value as context.

    Example:
        settings = FileWriteEffectSettings(
            path="/tmp/output.txt",
            template="Message: {{ message }}"
        )
        effect = FileWriteEffect(settings)
        effect({"message": "hello"})
    """

    def __init__(self, settings: FileWriteEffectSettings):
        """
        Initialize FileWriteEffect.

        Args:
            settings: FileWriteEffect configuration
        """
        self.settings = settings
        self.path = settings.path
        self.template = jinja2.Template(settings.template)
        self.append = settings.append

        # Initialize renderer if provided
        if settings.renderer is not None:
            self.renderer, _ = make_renderer(settings.renderer)
        else:
            self.renderer = None

    def __call__(self, value: Any) -> None:
        """
        Write to file with the given value as template context.

        Args:
            value: Input value (dict for template rendering)
        """
        # Apply renderer if configured
        if self.renderer is not None:
            value = self.renderer(value)

        # Render template
        if isinstance(value, dict):
            content = self.template.render(**value)
        else:
            content = self.template.render(value=value)

        # Write to file
        mode = 'a' if self.append else 'w'
        with open(self.path, mode) as f:
            f.write(content)


# === OSCEffect ===

@dataclass
class OSCEffectSettings:
    """Settings for OSCEffect."""
    address: str
    port: int
    path: str
    renderer: Optional[str | Dict[str, Any]] = None


class OSCEffect(EffectBase, name="osc", settings=OSCEffectSettings):
    """
    Effect that sends OSC messages.

    Example:
        settings = OSCEffectSettings(
            address="127.0.0.1",
            port=8000,
            path="/test"
        )
        effect = OSCEffect(settings)
        effect({"param": 42})
    """

    def __init__(self, settings: OSCEffectSettings):
        """
        Initialize OSCEffect.

        Args:
            settings: OSCEffect configuration
        """
        self.settings = settings
        self.path = settings.path
        self.client = udp_client.SimpleUDPClient(settings.address, settings.port)

        # Initialize renderer if provided
        if settings.renderer is not None:
            self.renderer, _ = make_renderer(settings.renderer)
        else:
            self.renderer = None

    def __call__(self, value: Any) -> None:
        """
        Send OSC message with the given value.

        Args:
            value: Input value (converted to OSC message)
        """
        # Apply renderer if configured
        if self.renderer is not None:
            value = self.renderer(value)

        # Convert value to OSC message arguments
        if isinstance(value, dict):
            # Flatten dict to key-value pairs
            msg = [item for pair in value.items() for item in pair]
        elif isinstance(value, (list, tuple)):
            msg = list(value)
        else:
            msg = [value]

        self.client.send_message(self.path, msg)


# === NotificationEffect ===

@dataclass
class NotificationEffectSettings:
    """Settings for NotificationEffect."""
    message: str
    targets: List[Dict[str, Any]]
    renderer: Optional[str | Dict[str, Any]] = None


class NotificationEffect(EffectBase, name="notification", settings=NotificationEffectSettings):
    """
    Effect that sends notifications.

    Example:
        settings = NotificationEffectSettings(
            message="Alert: {{ value }}",
            targets=[{"type": "console"}]
        )
        effect = NotificationEffect(settings)
        effect("something happened")
    """

    def __init__(self, settings: NotificationEffectSettings):
        """
        Initialize NotificationEffect.

        Args:
            settings: NotificationEffect configuration
        """
        self.settings = settings
        self.message_template = jinja2.Template(settings.message)
        self.targets = settings.targets

        # Initialize renderer if provided
        if settings.renderer is not None:
            self.renderer, _ = make_renderer(settings.renderer)
        else:
            self.renderer = None

    def __call__(self, value: Any) -> None:
        """
        Send notification with the given value.

        Args:
            value: Input value (used in message template)
        """
        # Apply renderer if configured
        if self.renderer is not None:
            value = self.renderer(value)

        # Render message
        if isinstance(value, dict):
            message = self.message_template.render(**value)
        else:
            message = self.message_template.render(value=value)

        # Send to targets (simplified - just print for now)
        print(f"Notification: {message}")
        # TODO: Implement actual notification target sending


# === SequenceEffect ===

@dataclass
class SequenceEffectSettings:
    """Settings for SequenceEffect."""
    effects: List[Dict[str, Any]]
    renderer: Optional[str | Dict[str, Any]] = None


class SequenceEffect(EffectBase, name="sequence", settings=SequenceEffectSettings):
    """
    Effect that executes multiple effects in sequence.

    Example:
        settings = SequenceEffectSettings(
            effects=[
                {"type": "file_write", "path": "/tmp/1.txt", "template": "{{ value }}"},
                {"type": "shell", "command": "cat /tmp/1.txt"}
            ]
        )
        effect = SequenceEffect(settings)
        effect("hello")
    """

    def __init__(self, settings: SequenceEffectSettings):
        """
        Initialize SequenceEffect.

        Args:
            settings: SequenceEffect configuration
        """
        self.settings = settings
        self.effect_instances = []

        # Create effect instances from settings
        for effect_config in settings.effects:
            effect_instance, _ = make_effect(effect_config)
            self.effect_instances.append(effect_instance)

        # Initialize renderer if provided
        if settings.renderer is not None:
            self.renderer, _ = make_renderer(settings.renderer)
        else:
            self.renderer = None

    def __call__(self, value: Any) -> None:
        """
        Execute all effects in sequence with the given value.

        Args:
            value: Input value (passed to all effects)
        """
        # Apply renderer if configured
        if self.renderer is not None:
            value = self.renderer(value)

        # Execute each effect
        for effect in self.effect_instances:
            effect(value)
