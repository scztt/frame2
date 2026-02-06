"""
Web UI for Frame Install - a simple HTMX-powered installer dashboard.

Provides:
- /install - Main page showing all steps with status
- /install/check - Run --check to populate status
- /install/run - Run full installation
- /install/status - SSE stream for live updates
"""

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import subprocess
import re

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

router = APIRouter(prefix="/install", tags=["install"])


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
    name: str
    type: str
    index: int
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None


@dataclass
class InstallState:
    """Global install state - cached and shared across requests."""
    state_file: Optional[Path] = None
    steps: list[Step] = field(default_factory=list)
    is_checking: bool = False
    is_installing: bool = False
    last_error: Optional[str] = None

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
        for q in self._subscribers:
            await q.put(f"event: {event}\ndata: {data}\n\n")


# Global state (singleton)
_state = InstallState()


def get_state() -> InstallState:
    return _state


def parse_state_file(state_file: Path) -> list[Step]:
    """Parse state file and return list of steps."""
    import yaml

    # Use the include-aware loader from installer
    from frame.install.installer import load_yaml_with_includes, flatten_includes

    raw = load_yaml_with_includes(state_file)
    raw = flatten_includes(raw)

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = raw.get('steps', [])
        entries = flatten_includes(entries)
    else:
        return []

    steps = []
    for i, entry in enumerate(entries):
        if isinstance(entry, dict):
            name = entry.get('name', entry.get('type', f'Step {i+1}'))
            step_type = entry.get('type', 'unknown')
            steps.append(Step(name=name, type=step_type, index=i))

    return steps


async def run_install_process(
    state: InstallState,
    check_only: bool = False
) -> None:
    """Run frame install in background, parsing output for status updates."""
    if not state.state_file or not state.state_file.exists():
        state.last_error = "No state file configured"
        await state.notify("error", state.last_error)
        return

    # Mark all steps as checking/installing
    initial_status = StepStatus.CHECKING if check_only else StepStatus.INSTALLING
    for step in state.steps:
        step.status = initial_status
        step.error = None
    await state.notify("refresh", "")

    cmd = ["uv", "run", "frame", "install", str(state.state_file), "--verbose"]
    if check_only:
        cmd.append("--check")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=Path(__file__).parent.parent.parent,  # Project root
        )

        current_step_idx = -1

        async for line in process.stdout:
            line_str = line.decode('utf-8', errors='replace').strip()

            # Parse step boundaries: "  [1/10] Step Name"
            step_match = re.match(r'\s*\[(\d+)/(\d+)\]\s+(.+)', line_str)
            if step_match:
                step_num = int(step_match.group(1)) - 1
                if 0 <= step_num < len(state.steps):
                    current_step_idx = step_num
                    state.steps[step_num].status = StepStatus.CHECKING if check_only else StepStatus.INSTALLING
                    await state.notify("step", str(step_num))
                continue

            # Parse sub-task results
            if current_step_idx >= 0 and current_step_idx < len(state.steps):
                step = state.steps[current_step_idx]

                if '[!]' in line_str:
                    # Failure
                    step.status = StepStatus.FAILED
                    # Try to extract error message
                    error_match = re.search(r'Error:\s*(.+)', line_str)
                    if error_match:
                        step.error = error_match.group(1)
                    await state.notify("step", str(current_step_idx))
                elif '[~]' in line_str:
                    # Changed (for check mode, means would change)
                    if check_only:
                        step.status = StepStatus.CHANGED
                    else:
                        step.status = StepStatus.COMPLETE
                    await state.notify("step", str(current_step_idx))
                elif '[x]' in line_str:
                    # OK
                    if step.status not in (StepStatus.FAILED, StepStatus.CHANGED):
                        step.status = StepStatus.OK if check_only else StepStatus.COMPLETE
                    await state.notify("step", str(current_step_idx))

        await process.wait()

        # Mark any remaining pending steps as skipped
        for step in state.steps:
            if step.status in (StepStatus.CHECKING, StepStatus.INSTALLING, StepStatus.PENDING):
                step.status = StepStatus.SKIPPED

        await state.notify("complete", "")

    except Exception as e:
        state.last_error = str(e)
        await state.notify("error", str(e))
    finally:
        state.is_checking = False
        state.is_installing = False


def render_step_html(step: Step) -> str:
    """Render a single step as HTML."""
    status_class = step.status.value
    status_icon = {
        StepStatus.PENDING: "&#x2B24;",      # Circle
        StepStatus.CHECKING: "&#x21BB;",     # Refresh
        StepStatus.OK: "&#x2713;",           # Check
        StepStatus.CHANGED: "&#x2022;",      # Bullet (would change)
        StepStatus.FAILED: "&#x2717;",       # X
        StepStatus.INSTALLING: "&#x21BB;",   # Refresh
        StepStatus.COMPLETE: "&#x2714;",     # Heavy check
        StepStatus.SKIPPED: "&#x2014;",      # Dash
    }.get(step.status, "?")

    error_html = f'<span class="step-error">{step.error}</span>' if step.error else ''

    return f'''
    <div id="step-{step.index}" class="step status-{status_class}">
        <span class="step-icon">{status_icon}</span>
        <span class="step-name">{step.name}</span>
        <span class="step-type">{step.type}</span>
        {error_html}
    </div>
    '''


def render_page(state: InstallState) -> str:
    """Render the full install page."""
    steps_html = "\n".join(render_step_html(s) for s in state.steps)

    # Disable buttons if already running
    check_disabled = "disabled" if state.is_checking or state.is_installing else ""
    install_disabled = "disabled" if state.is_installing else ""

    status_msg = ""
    if state.is_checking:
        status_msg = '<div class="status-banner checking">Checking...</div>'
    elif state.is_installing:
        status_msg = '<div class="status-banner installing">Installing...</div>'
    elif state.last_error:
        status_msg = f'<div class="status-banner error">Error: {state.last_error}</div>'

    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Frame Install</title>
        <script src="https://unpkg.com/htmx.org@1.9.5"></script>
        <script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <style>
            :root {{
                --bg: #1a1a2e;
                --card: #16213e;
                --text: #eee;
                --muted: #888;
                --accent: #0f3460;
                --success: #4ade80;
                --warning: #fbbf24;
                --error: #f87171;
                --pending: #64748b;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                font-family: 'Inter', -apple-system, sans-serif;
                background: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
            }}
            h1 {{
                font-size: 1.5rem;
                font-weight: 500;
                margin-bottom: 1rem;
            }}
            .controls {{
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }}
            button {{
                background: var(--accent);
                color: var(--text);
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
            }}
            button:hover:not(:disabled) {{
                background: #1a4980;
            }}
            button:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}
            button.primary {{
                background: var(--success);
                color: #000;
            }}
            .status-banner {{
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 15px;
                font-size: 14px;
            }}
            .status-banner.checking {{ background: var(--accent); }}
            .status-banner.installing {{ background: var(--warning); color: #000; }}
            .status-banner.error {{ background: var(--error); color: #000; }}
            .steps {{
                background: var(--card);
                border-radius: 8px;
                overflow: hidden;
            }}
            .step {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                border-bottom: 1px solid var(--accent);
            }}
            .step:last-child {{ border-bottom: none; }}
            .step-icon {{
                width: 20px;
                text-align: center;
                font-size: 16px;
            }}
            .step-name {{
                flex: 1;
                font-size: 14px;
            }}
            .step-type {{
                font-size: 12px;
                color: var(--muted);
                background: var(--accent);
                padding: 2px 8px;
                border-radius: 4px;
            }}
            .step-error {{
                font-size: 12px;
                color: var(--error);
                margin-left: auto;
            }}
            .status-pending .step-icon {{ color: var(--pending); }}
            .status-checking .step-icon, .status-installing .step-icon {{
                color: var(--warning);
                animation: spin 1s linear infinite;
            }}
            .status-ok .step-icon {{ color: var(--success); }}
            .status-changed .step-icon {{ color: var(--warning); }}
            .status-failed .step-icon {{ color: var(--error); }}
            .status-complete .step-icon {{ color: var(--success); }}
            .status-skipped .step-icon {{ color: var(--muted); }}
            @keyframes spin {{
                from {{ transform: rotate(0deg); }}
                to {{ transform: rotate(360deg); }}
            }}
            .empty {{
                padding: 40px;
                text-align: center;
                color: var(--muted);
            }}
            .file-input {{
                display: flex;
                gap: 10px;
                margin-bottom: 20px;
            }}
            .file-input input {{
                flex: 1;
                background: var(--card);
                border: 1px solid var(--accent);
                color: var(--text);
                padding: 10px;
                border-radius: 6px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body hx-ext="sse" sse-connect="/install/status">
        <h1>Frame Install</h1>

        <form class="file-input" hx-post="/install/load" hx-swap="innerHTML" hx-target="#main">
            <input type="text" name="state_file"
                   value="{state.state_file or ''}"
                   placeholder="Path to state.yml">
            <button type="submit">Load</button>
        </form>

        <div id="main" sse-swap="refresh">
            {status_msg}

            <div class="controls">
                <button hx-post="/install/check" hx-swap="none" {check_disabled}>
                    Check Status
                </button>
                <button class="primary" hx-post="/install/run" hx-swap="none" {install_disabled}>
                    Install All
                </button>
            </div>

            <div class="steps">
                {steps_html if state.steps else '<div class="empty">No steps loaded. Enter a state file path above.</div>'}
            </div>
        </div>

        <script>
            // Handle SSE step updates
            document.body.addEventListener('sse:step', function(e) {{
                const idx = e.detail.data;
                htmx.ajax('GET', '/install/step/' + idx, '#step-' + idx);
            }});
            // Handle refresh event
            document.body.addEventListener('sse:refresh', function(e) {{
                htmx.ajax('GET', '/install/main', '#main');
            }});
            document.body.addEventListener('sse:complete', function(e) {{
                htmx.ajax('GET', '/install/main', '#main');
            }});
            document.body.addEventListener('sse:error', function(e) {{
                htmx.ajax('GET', '/install/main', '#main');
            }});
        </script>
    </body>
    </html>
    '''


# --- Routes ---

@router.get("", response_class=HTMLResponse)
async def install_page(state: InstallState = Depends(get_state)):
    """Main install page."""
    return render_page(state)


@router.get("/main", response_class=HTMLResponse)
async def install_main(state: InstallState = Depends(get_state)):
    """Just the main content area (for HTMX refresh)."""
    steps_html = "\n".join(render_step_html(s) for s in state.steps)

    check_disabled = "disabled" if state.is_checking or state.is_installing else ""
    install_disabled = "disabled" if state.is_installing else ""

    status_msg = ""
    if state.is_checking:
        status_msg = '<div class="status-banner checking">Checking...</div>'
    elif state.is_installing:
        status_msg = '<div class="status-banner installing">Installing...</div>'
    elif state.last_error:
        status_msg = f'<div class="status-banner error">Error: {state.last_error}</div>'

    return f'''
    {status_msg}
    <div class="controls">
        <button hx-post="/install/check" hx-swap="none" {check_disabled}>Check Status</button>
        <button class="primary" hx-post="/install/run" hx-swap="none" {install_disabled}>Install All</button>
    </div>
    <div class="steps">
        {steps_html if state.steps else '<div class="empty">No steps loaded.</div>'}
    </div>
    '''


@router.get("/step/{idx}", response_class=HTMLResponse)
async def get_step(idx: int, state: InstallState = Depends(get_state)):
    """Get a single step's HTML (for HTMX updates)."""
    if 0 <= idx < len(state.steps):
        return render_step_html(state.steps[idx])
    return ""


@router.post("/load", response_class=HTMLResponse)
async def load_state(
    state_file: str,
    state: InstallState = Depends(get_state)
):
    """Load a state file."""
    path = Path(state_file)
    if not path.exists():
        state.last_error = f"File not found: {state_file}"
        return await install_main(state)

    try:
        state.state_file = path
        state.steps = parse_state_file(path)
        state.last_error = None
        # Reset all statuses
        for step in state.steps:
            step.status = StepStatus.PENDING
            step.error = None
    except Exception as e:
        state.last_error = str(e)

    return await install_main(state)


@router.post("/check")
async def check_install(state: InstallState = Depends(get_state)):
    """Run --check to populate status."""
    if state.is_checking or state.is_installing:
        raise HTTPException(400, "Already running")

    state.is_checking = True
    state.last_error = None

    # Run in background
    asyncio.create_task(run_install_process(state, check_only=True))

    return {"status": "started"}


@router.post("/run")
async def run_install(state: InstallState = Depends(get_state)):
    """Run full installation."""
    if state.is_installing:
        raise HTTPException(400, "Already installing")

    state.is_installing = True
    state.last_error = None

    # Run in background
    asyncio.create_task(run_install_process(state, check_only=False))

    return {"status": "started"}


@router.get("/status")
async def status_stream(state: InstallState = Depends(get_state)):
    """SSE stream for live status updates."""
    queue = state.subscribe()

    async def generate():
        try:
            # Send initial ping
            yield "event: ping\ndata: connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield msg
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield "event: ping\ndata: keepalive\n\n"
        finally:
            state.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
