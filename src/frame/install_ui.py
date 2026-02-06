"""
Web UI for Frame Install - an HTMX-powered installer dashboard.

Routes:
- /install - Main page showing all steps with live status
- /install/check - Run --check to populate status
- /install/run - Run full installation
- /install/status - SSE stream for live updates

The state file path is configured via `install_state` key in server config YAML.
"""

import asyncio
import html as html_mod
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any, Dict

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

router = APIRouter(prefix="/install", tags=["install"])

# Set by main.py after config is loaded
_install_state_path: Optional[Path] = None
_shutdown_event: Optional[asyncio.Event] = None


def set_install_state_path(path: Optional[str]) -> None:
    """Set the install state file path from config."""
    global _install_state_path
    if path:
        _install_state_path = Path(path)


def set_shutdown_event(event: asyncio.Event) -> None:
    """Set the shutdown event from main.py."""
    global _shutdown_event
    _shutdown_event = event


# --- Data Models ---


class StepStatus(Enum):
    PENDING = "pending"
    CHECKING = "checking"
    OK = "ok"
    CHANGED = "changed"
    FAILED = "failed"
    INSTALLING = "installing"
    COMPLETE = "complete"
    SKIPPED = "skipped"


@dataclass
class Step:
    """A single installation step."""
    name: str
    type: str
    index: int
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    output: Optional[str] = None
    tasks: list[Dict[str, str]] = field(default_factory=list)
    yaml_source: Optional[str] = None


@dataclass
class InstallState:
    """Global install state singleton - shared across requests."""

    state_file: Optional[Path] = None
    steps: list[Step] = field(default_factory=list)
    is_checking: bool = False
    is_installing: bool = False
    last_error: Optional[str] = None
    auto_checked: bool = False

    # File watching
    _file_mod_time: Optional[float] = None
    _watcher_task: Optional["asyncio.Task[None]"] = None
    _cancel_requested: bool = False

    # SSE subscribers
    _subscribers: list[asyncio.Queue] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def notify(self, event: str, data: str = ""):
        """Send SSE event to all subscribers."""
        if "\n" in data:
            data_lines = "\n".join(f"data: {line}" for line in data.split("\n"))
            msg = f"event: {event}\n{data_lines}\n\n"
        else:
            msg = f"event: {event}\ndata: {data}\n\n"
        for q in self._subscribers:
            await q.put(msg)

    def is_cancelled(self) -> bool:
        return self._cancel_requested

    def clear_cancel(self):
        self._cancel_requested = False

    def start_file_watcher(self):
        """Start file watcher if not already running."""
        if self._watcher_task is None or self._watcher_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._watcher_task = loop.create_task(self._watch_file())
            except RuntimeError:
                pass  # No loop yet - will start on first async access

    def ensure_file_watcher(self):
        """Ensure file watcher is running (call from async context)."""
        if self._watcher_task is None or self._watcher_task.done():
            print(f"[install_ui] Starting file watcher for: {self.state_file}")
            self._watcher_task = asyncio.create_task(self._watch_file())

    async def _watch_file(self):
        """Poll for state file changes."""
        while True:
            await asyncio.sleep(1.0)
            if not self.state_file or not self.state_file.exists():
                continue
            try:
                mtime = self.state_file.stat().st_mtime
                if self._file_mod_time is not None and mtime != self._file_mod_time:
                    await self._on_file_changed()
                self._file_mod_time = mtime
            except OSError:
                pass

    async def _on_file_changed(self):
        """Handle state file change - reload and restart check."""
        print("[install_ui] State file changed, reloading...")
        self._cancel_requested = True

        # Reload steps
        if self.state_file and self.state_file.exists():
            try:
                self.steps = parse_state_file(self.state_file)
                self._file_mod_time = self.state_file.stat().st_mtime
            except Exception as e:
                self.last_error = f"Reload failed: {e}"
                self.steps = []

        # Reset statuses
        for step in self.steps:
            step.status = StepStatus.PENDING
            step.error = None
            step.tasks = []

        self.auto_checked = False
        self.last_error = None
        await self.notify("main", render_main_html(self))

        # If process running, let it exit via cancel check
        if self.is_checking or self.is_installing:
            print("[install_ui] Process running, will restart after exit")
            return

        # Start new check
        self._cancel_requested = False
        self.is_checking = True
        self.auto_checked = True
        print("[install_ui] Starting check after reload")
        asyncio.create_task(run_install_process(self, check_only=True))


# Global singleton
_state = InstallState()
_state_initialized = False


def get_state() -> InstallState:
    """Get or initialize the global install state."""
    global _state_initialized
    if not _state_initialized and _install_state_path:
        _state_initialized = True
        if _install_state_path.exists():
            _state.state_file = _install_state_path
            _state._file_mod_time = _install_state_path.stat().st_mtime
            try:
                _state.steps = parse_state_file(_install_state_path)
            except Exception as e:
                _state.last_error = str(e)
            _state.start_file_watcher()
    return _state


def parse_state_file(state_file: Path) -> list[Step]:
    """Parse state file and return list of steps."""
    from frame.install.installer import load_yaml_with_includes, flatten_includes

    raw = load_yaml_with_includes(state_file)
    raw = flatten_includes(raw)

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = flatten_includes(raw.get("steps", []))
    else:
        return []

    steps = []
    for i, entry in enumerate(entries):
        if isinstance(entry, dict):
            name = entry.get("name", entry.get("type", f"Step {i+1}"))
            step_type = entry.get("type", "unknown")
            yaml_source = yaml.dump(entry, default_flow_style=False, allow_unicode=True, sort_keys=False)
            steps.append(Step(name=name, type=step_type, index=i, yaml_source=yaml_source))
    return steps


# --- Ansible Runner ---

_executor = ThreadPoolExecutor(max_workers=2)


def _run_ansible_sync(
    state_file: Path,
    check_only: bool,
    on_step_start: Callable[[int], None],
    on_step_result: Callable[[int, bool, bool, str, Dict[str, Any]], None],
) -> bool:
    """Run ansible synchronously in thread pool. Returns True if successful."""
    import ansible_runner
    from frame.install.installer import (
        load_yaml_with_includes, flatten_includes, validate_state_entries,
        get_required_handlers, generate_site_yml, generate_ansible_cfg,
        generate_inventory, load_handler, check_ansible_installed,
    )
    from frame.install.generators import step_label

    try:
        check_ansible_installed()
    except SystemExit:
        return False

    raw = load_yaml_with_includes(state_file)
    raw = flatten_includes(raw)

    if isinstance(raw, list):
        state_entries, config = raw, {}
    elif isinstance(raw, dict):
        config = raw.get("config", {})
        state_entries = flatten_includes(raw.get("steps", []))
    else:
        return False

    config.setdefault("resources_dir", str(state_file.resolve().parent))
    config["cwd"] = str(Path.cwd().resolve())

    try:
        validate_state_entries(state_entries)
    except SystemExit:
        return False

    required_handlers = get_required_handlers(state_entries)
    step_names = {step_label(e) for e in state_entries}
    current_step = [-1]
    step_has_failed = {}
    step_has_changed = set()
    step_results: dict[int, dict] = {}

    def finalize_step(idx: int):
        if idx < 0 or idx >= len(state_entries):
            return
        results = step_results.get(idx, {})
        on_step_result(
            idx,
            idx in step_has_failed,
            idx in step_has_changed,
            results.get("error", ""),
            {"tasks": results.get("tasks", []), "output": results.get("output", "")},
        )

    def on_event(event):
        event_type = event.get("event", "")
        data = event.get("event_data", {})

        if event_type == "playbook_on_task_start":
            task_name = data.get("task", "")
            if task_name in step_names:
                if current_step[0] >= 0:
                    finalize_step(current_step[0])
                current_step[0] += 1
                step_results[current_step[0]] = {"tasks": [], "output": "", "error": ""}
                on_step_start(current_step[0])
            return

        if event_type in ("runner_on_ok", "runner_on_failed", "runner_on_skipped",
                          "runner_item_on_ok", "runner_item_on_failed", "runner_item_on_skipped"):
            idx = current_step[0]
            if idx < 0 or idx >= len(state_entries):
                return

            res = data.get("res", {})
            task_name = data.get("task", "unknown")
            is_failed = "failed" in event_type
            is_changed = res.get("changed", False)

            if idx not in step_results:
                step_results[idx] = {"tasks": [], "output": "", "error": ""}
            results = step_results[idx]

            # Extract useful output from task result
            task_output: str | None = None
            msg = res.get("msg")
            if msg:  # debug module output
                task_output = str(msg)
            elif res.get("dest"):  # copy, get_url, synchronize
                task_output = f"→ {res['dest']}"
            elif res.get("path"):  # file module
                task_output = f"→ {res['path']}"
            elif res.get("stdout"):  # command/shell
                task_output = str(res["stdout"])[:200]

            if task_output:
                print(f"[install_ui] Task output: {task_name[:40]} => {task_output[:80]}")

            if is_failed:
                step_has_failed[idx] = True
                results["tasks"].append({"name": task_name, "status": "failed", "output": task_output})
                results["error"] = res.get("msg", "") or str(res.get("stderr", ""))[:200]
                stdout = res.get("stdout", "") or res.get("module_stdout", "")
                stderr = res.get("stderr", "") or res.get("module_stderr", "")
                if stdout or stderr:
                    results["output"] = f"{stdout}\n{stderr}".strip()[:500]
            elif is_changed:
                step_has_changed.add(idx)
                results["tasks"].append({"name": task_name, "status": "changed", "output": task_output})
            else:
                results["tasks"].append({"name": task_name, "status": "ok", "output": task_output})

        if event_type == "playbook_on_stats" and current_step[0] >= 0:
            finalize_step(current_step[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        ansible_dir = Path(tmpdir) / "ansible"
        ansible_dir.mkdir()
        project_dir = ansible_dir / "project"
        project_dir.mkdir()
        types_dir = project_dir / "types"
        types_dir.mkdir()
        inventory_dir = ansible_dir / "inventory"
        inventory_dir.mkdir()

        (project_dir / "site.yml").write_text(generate_site_yml(state_entries, config))
        (project_dir / "ansible.cfg").write_text(generate_ansible_cfg())
        (inventory_dir / "hosts").write_text(generate_inventory(host=None))

        for handler in required_handlers:
            (types_dir / f"{handler}.yml").write_text(load_handler(handler))

        envvars = {}
        become_pass = os.environ.get("FRAME_BECOME_PASS") or os.environ.get("ANSIBLE_BECOME_PASS")
        if become_pass:
            envvars["ANSIBLE_BECOME_PASS"] = become_pass

        result = ansible_runner.run(
            private_data_dir=str(ansible_dir),
            playbook="site.yml",
            cmdline="--check" if check_only else None,
            quiet=True,
            event_handler=on_event,
            envvars=envvars or None,
        )
        return result.status == "successful"


async def run_install_process(state: InstallState, check_only: bool = False) -> None:
    """Run ansible in background with live SSE updates."""
    action = "check" if check_only else "install"
    print(f"[install_ui] Starting {action}")

    if not state.state_file or not state.state_file.exists():
        state.last_error = "No state file configured"
        await state.notify("error", state.last_error)
        return

    if state.is_cancelled():
        print("[install_ui] Cancelled before start")
        return

    for step in state.steps:
        step.status = StepStatus.PENDING
        step.error = None
    await state.notify("main", render_main_html(state))

    loop = asyncio.get_event_loop()

    def send_update():
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(state.notify("main", render_main_html(state)))
        )

    def on_step_start(idx: int):
        if 0 <= idx < len(state.steps):
            state.steps[idx].status = StepStatus.CHECKING if check_only else StepStatus.INSTALLING
            send_update()

    def on_step_result(idx: int, failed: bool, changed: bool, error_msg: str, task_info: dict):
        if 0 <= idx < len(state.steps):
            step = state.steps[idx]
            if failed:
                step.status = StepStatus.FAILED
                step.error = error_msg[:200] if error_msg else "Failed"
            elif changed:
                step.status = StepStatus.CHANGED if check_only else StepStatus.COMPLETE
            elif step.status != StepStatus.FAILED:
                step.status = StepStatus.OK if check_only else StepStatus.COMPLETE
            step.tasks = task_info.get("tasks", [])
            step.output = task_info.get("output", "")
            send_update()

    try:
        success = await loop.run_in_executor(
            _executor, _run_ansible_sync, state.state_file, check_only, on_step_start, on_step_result
        )

        if state.is_cancelled():
            print("[install_ui] Cancelled after run")
            return

        for step in state.steps:
            if step.status in (StepStatus.CHECKING, StepStatus.INSTALLING, StepStatus.PENDING):
                step.status = StepStatus.SKIPPED

        if not success:
            state.last_error = "Installation failed"

    except Exception as e:
        state.last_error = str(e)
    finally:
        state.is_checking = False
        state.is_installing = False
        state.clear_cancel()
        # Send final update with buttons re-enabled
        await state.notify("main", render_main_html(state))
        print(f"[install_ui] Finished {action}")


# --- HTML Rendering ---

STEP_ICONS = {
    StepStatus.PENDING: "&#x2B24;",      # Circle
    StepStatus.CHECKING: "&#x21BB;",     # Refresh
    StepStatus.OK: "&#x2713;",           # Check
    StepStatus.CHANGED: "&#x2022;",      # Bullet
    StepStatus.FAILED: "&#x2717;",       # X
    StepStatus.INSTALLING: "&#x21BB;",   # Refresh
    StepStatus.COMPLETE: "&#x2714;",     # Heavy check
    StepStatus.SKIPPED: "&#x2014;",      # Dash
}

TASK_ICONS = {
    "ok": '<span class="task-ok">&#x2713;</span>',
    "changed": '<span class="task-changed">&#x25CB;</span>',
    "failed": '<span class="task-failed">&#x2717;</span>',
    "skipped": '<span class="task-skipped">&#x2014;</span>',
}


def render_steps_html(steps: list[Step]) -> str:
    if not steps:
        return '<div class="empty">No steps loaded.</div>'
    return "\n".join(render_step_html(s) for s in steps)


def render_main_html(state: InstallState) -> str:
    """Render the #main content (controls + steps) for SSE updates."""
    steps_html = render_steps_html(state.steps) if state.steps else '<div class="empty">No steps loaded.</div>'
    return f'''{render_controls(state)}
    <div class="steps">{steps_html}</div>'''


def render_step_html(step: Step) -> str:
    status_class = step.status.value
    icon = STEP_ICONS.get(step.status, "?")
    error_html = f'<span class="step-error">{html_mod.escape(step.error)}</span>' if step.error else ""

    # Build expandable details
    parts = []
    if step.tasks:
        task_items = []
        for t in step.tasks:
            icon = TASK_ICONS.get(t.get("status", "ok"), "?")
            name = html_mod.escape(t.get("name", ""))
            output = t.get("output")
            output_html = f' <span class="task-output">{html_mod.escape(output)}</span>' if output else ""
            task_items.append(f'<div class="task-item">{icon} {name}{output_html}</div>')
        tasks_html = "".join(task_items)
        parts.append(f'<div class="detail-section"><strong>Tasks:</strong>{tasks_html}</div>')
    if step.error:
        parts.append(f'<div class="detail-section detail-error"><strong>Error:</strong> {html_mod.escape(step.error)}</div>')
    if step.yaml_source:
        parts.append(f'<div class="detail-section"><strong>YAML:</strong><pre class="detail-yaml">{html_mod.escape(step.yaml_source)}</pre></div>')
    if step.output:
        parts.append(f'<div class="detail-section"><strong>Output:</strong><pre class="detail-output">{html_mod.escape(step.output)}</pre></div>')

    details_html = "".join(parts) or '<div class="detail-section">No details available</div>'

    return f'''<details id="step-{step.index}" class="step status-{status_class}">
        <summary><span class="step-icon">{icon}</span><span class="step-name">{step.name}</span><span class="step-type">{step.type}</span>{error_html}</summary>
        <div class="step-details">{details_html}</div>
    </details>'''


def render_controls(state: InstallState) -> str:
    """Render the control buttons and status banner."""
    is_busy = state.is_checking or state.is_installing

    if state.is_checking:
        check_class, check_text = "loading", "Checking..."
        status = '<div class="status-banner checking">Checking...</div>'
    elif state.is_installing:
        check_class, check_text = "", "Check Status"
        status = '<div class="status-banner installing">Installing...</div>'
    elif state.last_error:
        check_class, check_text = "", "Check Status"
        status = f'<div class="status-banner error">Error: {state.last_error}</div>'
    else:
        check_class, check_text = "", "Check Status"
        status = ""

    install_class = "primary" + (" loading" if state.is_installing else "")
    install_text = "Installing..." if state.is_installing else "Install All"
    disabled = "disabled" if is_busy else ""

    return f'''
    {status}
    <div class="controls">
        <button class="{check_class}" hx-post="/install/check" hx-target="#main" hx-swap="innerHTML" {disabled}>{check_text}</button>
        <button class="{install_class}" hx-post="/install/run" hx-target="#main" hx-swap="innerHTML" {disabled}>{install_text}</button>
    </div>
    '''


def render_page(state: InstallState) -> str:
    """Render the full install page."""
    steps_html = render_steps_html(state.steps) if state.steps else '<div class="empty">No steps loaded.</div>'
    controls = render_controls(state)

    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Frame Install</title>
    <script src="https://unpkg.com/htmx.org@1.9.5"></script>
    <script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap">
    <link rel="stylesheet" href="/style.css">
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
</head>
<body class="install-page" hx-ext="sse" sse-connect="/install/status">
    <h1>Frame Install</h1>

    <div class="config-path">
        <span class="label">State file:</span>
        <span class="path">{state.state_file or 'Not configured (set install_state in config.yaml)'}</span>
    </div>

    <div id="main" sse-swap="main" hx-swap="innerHTML">
        {controls}
        <div class="steps">{steps_html}</div>
    </div>

    <script>
        // Preserve expanded state across SSE updates
        (function() {{
            const openSteps = new Set();

            // Track toggle events on body (captures all details)
            document.body.addEventListener('toggle', function(e) {{
                if (e.target.tagName === 'DETAILS' && e.target.closest('.steps')) {{
                    if (e.target.open) openSteps.add(e.target.id);
                    else openSteps.delete(e.target.id);
                }}
            }}, true);

            // Restore open state after DOM changes
            new MutationObserver(function() {{
                openSteps.forEach(id => {{
                    const el = document.getElementById(id);
                    if (el && !el.open) el.open = true;
                }});
            }}).observe(document.getElementById('main'), {{ childList: true, subtree: true }});
        }})();
    </script>
</body>
</html>'''


# --- Routes ---


@router.get("", response_class=HTMLResponse)
async def install_page(state: InstallState = Depends(get_state)):
    """Main install page."""
    state.ensure_file_watcher()
    if state.steps and not state.auto_checked and not state.is_checking and not state.is_installing:
        state.auto_checked = True
        state.is_checking = True
        asyncio.create_task(run_install_process(state, check_only=True))
    return render_page(state)


@router.get("/main", response_class=HTMLResponse)
async def install_main(state: InstallState = Depends(get_state)):
    """Main content area for HTMX refresh."""
    return render_main_html(state)


@router.post("/check", response_class=HTMLResponse)
async def check_install(state: InstallState = Depends(get_state)):
    """Run --check to populate status."""
    if state.is_checking or state.is_installing:
        raise HTTPException(400, "Already running")

    state.is_checking = True
    state.last_error = None
    asyncio.create_task(run_install_process(state, check_only=True))
    return await install_main(state)


@router.post("/run", response_class=HTMLResponse)
async def run_install(state: InstallState = Depends(get_state)):
    """Run full installation."""
    if state.is_installing:
        raise HTTPException(400, "Already installing")

    state.is_installing = True
    state.last_error = None
    asyncio.create_task(run_install_process(state, check_only=False))
    return await install_main(state)


@router.get("/status")
async def status_stream(state: InstallState = Depends(get_state)):
    """SSE stream for live status updates."""
    queue = state.subscribe()

    async def generate():
        try:
            yield "event: ping\ndata: connected\n\n"
            while True:
                if _shutdown_event and _shutdown_event.is_set():
                    return

                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: keepalive\n\n"
                except asyncio.CancelledError:
                    return
        finally:
            state.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
