from ast import Call
import asyncio
from typing import Callable, Dict, Any, Type
import uuid
from frame.images import ImageRef
from frame.shell import run_command
from frame.parsers import make_parser
import subprocess


def render_nested_dict(data, indent=0):
    """Recursively renders nested dictionaries and lists as indented HTML."""
    html = ""

    if not (isinstance(data, dict)):
        return str(data)

    print("rendering: " + str(data))

    for key, value in data.items():
        html += f"<div style='margin-left:{indent * 20}px;'><strong>{key}:</strong> "

        if isinstance(value, dict):
            html += "<br>" + render_nested_dict(value, indent + 1)
        elif isinstance(value, list):
            if value[0].get("_name"):
                value = {item["_name"]: item for item in value}

                for item in value:
                    del value[item]["_name"]

                html += render_nested_dict(value, indent + 1)
            else:
                html += (
                    "<ul>"
                    + "".join(f"<li>{render_nested_dict(item)}</li>" for item in value)
                    + "</ul>"
                )
        else:
            html += str(value)

        html += "</div>"
    return html


def render_streaming(path, id):
    path = path + "/streaming"
    return f"""
    <script>
        (new EventSource("{path}")).onmessage = function(event) {{
            document.getElementById("output-{id}").innerHTML = event.data;
        }};
    </script>
    """


def render_folding_value(name, path, streaming):
    id = uuid.uuid4().hex
    result = f"""
        <div class="endpoint-container" id="container-{id}" data-path="{path}">
            <div class="header" onclick="toggleSection('{path}', 'container-{id}')">
                <span class="toggle-icon">▶</span>
                <h3>{name}</h3>
                <span id="refresh-{id}" class="refresh-icon" hx-get="{path}" 
                      hx-target="#output-{id}" onclick="refreshData(event, 'container-{id}', 'refresh-{id}', '{path}')">
                  ↻
                </span>
            </div>
            <div id="output-{id}" class="output-container"></div>
        </div>
    """

    if True:
        result = render_streaming(path, id) + result

    return result


def render_simple_value(name, path, streaming):
    id = uuid.uuid4().hex
    result = f"""
        <div class="endpoint-container" id="container-{id}" data-path="{path}">
            <div class="header" style="align-items: center;">
                <h3 style="margin-right: 10px;">{name}:</h3>
                <div id="output-{id}" class="output-container" style="display: flex; display: inline-block; margin-left: 15px; border-top: none; padding: 0;"></div>
                <span id="refresh-{id}" class="refresh-icon" hx-get="{path}" 
                      hx-target="#output-{id}" onclick="refreshData(event, 'container-{id}', 'refresh-{id}', '{path}')">
                  ↻
                </span>
            </div>
        </div>
    """

    if streaming:
        result = render_streaming(path, id) + result

    return result


renderers: Dict[str, Any] = {}


class RendererBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        renderers[name] = cls

    def __init__(self, settings: Dict[str, Any]):
        self.folding = settings.get("folding", False)
        self.streaming = True

    def render_data(self, data: Dict[str, Any]) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def render_list_item(self, name: str, path: str) -> str:
        if self.folding:
            return render_folding_value(name, path, self.streaming)
        else:
            return render_simple_value(name, path, self.streaming)


def make_renderer(settings: dict | str, streaming=False) -> RendererBase:
    """Get an action by name."""
    if isinstance(settings, str):
        settings = {"type": settings}

    settings["streaming"] = streaming

    renderer_class = renderers.get(settings["type"])

    if renderer_class is None:
        raise ValueError(f"No renderer registered with name: {settings["type"]}")

    return renderer_class(settings)


############################################################
# Implementations
############################################################
class StringRenderer(RendererBase, name="string"):
    def render_data(self, data: Any) -> str:
        return f"<div class='value'>{data}</div>"


class JSONRenderer(RendererBase, name="json"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.folding = settings.get("folding", True)

    def render_data(self, data: dict) -> str:
        return render_nested_dict(data)


class StatusRenderer(RendererBase, name="status"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

    def render_data(self, data: bool) -> str:
        if data:
            return "<div class='value success'>Good</div>"
        else:
            return "<div class='value failure'>Error</div>"


class ImageRenderer(RendererBase, name="image"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.folding = settings.get("folding", True)

    def render_data(self, data: ImageRef) -> str:
        return f"""
            <img 
                src='/{data.url}?{uuid.uuid4().hex}' 
                class='screenshot-img' 
                onclick="this.classList.toggle('fullsize'); document.getElementById('lightbox-overlay').classList.toggle('active');"
                alt="Screenshot" 
            />
        """
