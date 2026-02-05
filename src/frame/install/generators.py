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


def generate_site_yml(steps: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> str:
    """Generate site.yml with one include_tasks per step instead of a loop.

    Each step becomes its own named include_tasks entry, so Ansible fires
    playbook_on_task_start for each step — giving natural step boundaries
    without needing markers or wrappers.
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
        label = step.get("name", step_type)
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

    play = [
        {
            "name": "Frame Installation",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "tasks": tasks,
        }
    ]

    return yaml.dump(play, default_flow_style=False, sort_keys=False)


def list_available_handlers() -> List[str]:
    """List all available handler types by scanning the handlers directory."""
    if not HANDLERS_DIR.exists():
        return []
    return [
        path.stem for path in HANDLERS_DIR.glob("*.yml")
        if path.is_file()
    ]
