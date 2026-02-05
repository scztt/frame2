"""Ansible playbook and handler generators for Frame installer."""

from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml


# Get the templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
HANDLERS_DIR = TEMPLATES_DIR / "handlers"


def load_template(template_name: str) -> str:
    """Load a template file from the templates directory."""
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    return template_path.read_text()


def _read_handler_raw(handler_name: str) -> str:
    """Read raw handler file contents."""
    handler_path = HANDLERS_DIR / f"{handler_name}.yml"
    if not handler_path.exists():
        raise FileNotFoundError(f"Handler not found: {handler_path}")
    return handler_path.read_text()


def _split_handler(raw: str) -> tuple:
    """Split a handler file into (metadata_dict, tasks_str).

    Handlers can use multi-document YAML (separated by ---) where the
    first document is metadata and the second is ansible tasks.
    If no metadata document exists, returns ({}, raw).
    """
    # Check for multi-document: metadata is a dict, tasks is a list
    docs = list(yaml.safe_load_all(raw))
    if len(docs) >= 2 and isinstance(docs[0], dict) and isinstance(docs[1], list):
        meta = docs[0]
        # Return the raw text after the first --- separator for the tasks
        # Find the second '---' which starts the tasks document
        parts = raw.split('\n---\n', 1)
        if len(parts) == 2:
            tasks_str = '---\n' + parts[1]
        else:
            tasks_str = raw
        return meta, tasks_str
    return {}, raw


def load_handler(handler_name: str) -> str:
    """Load a handler template, stripping any metadata section."""
    raw = _read_handler_raw(handler_name)
    _, tasks = _split_handler(raw)
    return tasks


def get_handler_dependencies(handler_name: str) -> List[str]:
    """Extract dependencies declared in a handler's metadata."""
    raw = _read_handler_raw(handler_name)
    meta, _ = _split_handler(raw)
    return meta.get("dependencies", [])


def get_static_site_yml() -> str:
    """Return the static canonical site.yml that loads and executes plan.yml."""
    return load_template("site.yml")


def generate_plan_yml(steps: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> str:
    """Generate plan.yml containing the installation steps and config from state.yaml."""
    plan: Dict[str, Any] = {"steps": steps}
    if config:
        plan["config"] = config
    return yaml.dump(plan, default_flow_style=False, sort_keys=False)


def generate_ansible_cfg() -> str:
    """Generate ansible.cfg for local execution."""
    return load_template("ansible.cfg")


def generate_inventory() -> str:
    """Generate inventory.ini for localhost."""
    return load_template("inventory.ini")


# Handler generator functions - now just load from files
def generate_install_app_handler() -> str:
    """Load the install_app handler template."""
    return load_handler("install_app")


def generate_defaults_handler() -> str:
    """Load the defaults handler template."""
    return load_handler("defaults")


def generate_homebrew_handler() -> str:
    """Load the homebrew handler template."""
    return load_handler("homebrew")


def generate_launchctl_handler() -> str:
    """Load the launchctl handler template."""
    return load_handler("launchctl")


def generate_copy_handler() -> str:
    """Load the copy handler template."""
    return load_handler("copy")


def generate_command_handler() -> str:
    """Load the command handler template."""
    return load_handler("command")


def generate_install_pkg_handler() -> str:
    """Load the install_pkg handler template."""
    return load_handler("install_pkg")


def generate_systemsetup_handler() -> str:
    """Load the systemsetup handler template."""
    return load_handler("systemsetup")


def generate_npx_handler() -> str:
    """Load the npx handler template."""
    return load_handler("npx")


def generate_audio_handler() -> str:
    """Load the audio handler template."""
    return load_handler("audio")


def generate_download_handler() -> str:
    """Load the download handler template."""
    return load_handler("download")


# Registry of handler generators by type
HANDLER_GENERATORS = {
    "install_app": generate_install_app_handler,
    "defaults": generate_defaults_handler,
    "homebrew": generate_homebrew_handler,
    "launchctl": generate_launchctl_handler,
    "copy": generate_copy_handler,
    "command": generate_command_handler,
    "install_pkg": generate_install_pkg_handler,
    "systemsetup": generate_systemsetup_handler,
    "npx": generate_npx_handler,
    "audio": generate_audio_handler,
    "download": generate_download_handler,
}


def get_handler_generator(handler_type: str):
    """Get the handler generator function for a given type."""
    if handler_type not in HANDLER_GENERATORS:
        raise ValueError(f"Unknown handler type: {handler_type}")
    return HANDLER_GENERATORS[handler_type]


def list_available_handlers() -> List[str]:
    """List all available handler types by scanning the handlers directory."""
    if not HANDLERS_DIR.exists():
        return []
    return [
        path.stem for path in HANDLERS_DIR.glob("*.yml")
        if path.is_file()
    ]


def register_handler_from_file(handler_name: str) -> None:
    """
    Dynamically register a handler from a file in the handlers directory.

    This allows third parties to add new handler types by simply
    adding a .yml file to the handlers directory.
    """
    def loader():
        return load_handler(handler_name)

    HANDLER_GENERATORS[handler_name] = loader
