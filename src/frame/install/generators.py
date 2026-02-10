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


def _read_handler_raw(handler_name: str, custom_dir: Optional[Path] = None) -> str:
    """Read raw handler file contents.

    Checks custom_dir first (if provided), then falls back to built-in handlers.
    """
    # Check custom directory first
    if custom_dir:
        custom_path = Path(custom_dir) / f"{handler_name}.yml"
        if custom_path.exists():
            return custom_path.read_text()

    # Fall back to built-in handlers
    handler_path = HANDLERS_DIR / f"{handler_name}.yml"
    if not handler_path.exists():
        raise FileNotFoundError(f"Handler not found: {handler_name}")
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
        parts = raw.split("\n---\n", 1)
        if len(parts) == 2:
            tasks_str = "---\n" + parts[1]
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


def generate_inventory(host: Optional[str] = None) -> str:
    """Generate inventory.ini for target host.

    If host is None, uses localhost with local connection.
    If host is provided (user@hostname), generates SSH inventory.
    """
    if host is None:
        return load_template("inventory.ini")

    # Parse user@hostname format
    if "@" in host:
        user, hostname = host.split("@", 1)
        return f"[targets]\n{hostname} ansible_user={user}\n"
    else:
        return f"[targets]\n{host}\n"


def step_label(entry: Dict[str, Any]) -> str:
    """Generate a human-readable label for a state entry.

    Used for both CLI display and ansible task names (so step detection works).
    """
    # Use explicit name if provided
    if "name" in entry:
        return entry["name"]
    # Fall back to auto-generated label
    t = entry["type"]
    if t == "install_app":
        source = entry.get("path", entry.get("remote", {}).get("url", "?"))
        return source.split("/")[-1]
    elif t == "homebrew":
        pkgs = entry.get("packages", [])
        label = ", ".join(pkgs[:3])
        if len(pkgs) > 3:
            label += f"... ({len(pkgs)} total)"
        return f"Homebrew: {label}"
    elif t == "copy":
        src_name = entry["src"].split("/")[-1]
        return f"Copy: {src_name} → {entry['dest']}"
    elif t == "launchctl":
        label = entry.get("label", entry.get("src", "?").split("/")[-1].replace(".plist", ""))
        return f"Service: {label}"
    elif t == "defaults":
        count = len(entry.get("items", []))
        return f"Defaults: {count} setting(s)"
    elif t == "command":
        args = entry.get("args", "")
        if isinstance(args, str):
            return args[:50]
        return " ".join(str(a) for a in args[:3])
    elif t == "systemsetup":
        count = len(entry.get("items", {}))
        return f"System: {count} setting(s)"
    elif t == "npx":
        return f"NPX: {entry.get('package', '?')}"
    elif t == "audio":
        return "Audio configuration"
    elif t == "download":
        filename = entry.get("url", "?").split("/")[-1]
        return f"Download: {filename}"
    elif t == "install_pkg":
        source = entry.get("path", entry.get("remote", {}).get("url", "?"))
        return source.split("/")[-1]
    else:
        return str(t)


def generate_site_yml(
    steps: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    host: Optional[str] = None,
) -> str:
    """Generate site.yml with one include_tasks per step instead of a loop.

    Each step becomes its own named include_tasks entry, so Ansible fires
    playbook_on_task_start for each step — giving natural step boundaries
    without needing markers or wrappers.

    If host is provided, targets remote machine via SSH instead of localhost.
    """
    tasks: List[Dict[str, Any]] = [
        {
            "name": "Gather facts",
            "setup": {},
            "tags": ["always"],
        }
    ]

    effective_config = config or {}

    for step in steps:
        step_type = step["type"]
        label = step_label(step)
        task: Dict[str, Any] = {
            "name": label,
            "include_tasks": f"types/{step_type}.yml",
            "vars": {
                "step": step,
                "config": effective_config,
            },
            "tags": ["always"],
        }
        when = step.get("when")
        if when is not None and when is not True:
            task["when"] = when
        tasks.append(task)

    # Configure play based on target
    if host:
        # Remote execution via SSH
        play_config: Dict[str, Any] = {
            "name": "Frame Installation",
            "hosts": "targets",
            "gather_facts": False,
            "tasks": tasks,
        }
    else:
        # Local execution
        play_config = {
            "name": "Frame Installation",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "tasks": tasks,
        }

    return yaml.dump([play_config], default_flow_style=False, sort_keys=False)


def list_available_handlers() -> List[str]:
    """List all available handler types by scanning the handlers directory."""
    if not HANDLERS_DIR.exists():
        return []
    return [path.stem for path in HANDLERS_DIR.glob("*.yml") if path.is_file()]
