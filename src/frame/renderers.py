from typing import Dict, Any, Generic, Tuple, Type
import uuid

from annotated_types import T
from frame.images import ImageRef
from frame.registry import TypeRegistry
import html as html_module


def render_nested_list(data, indent=0):
    """Recursively renders nested dictionaries and lists as indented HTML."""
    html = ""

    has_name_key = all("_name" in item for item in data)
    if has_name_key:
        data = {item["_name"]: item for item in data}
        return render_nested_dict(data, indent)

    html = "<ul>"
    html += "".join(f"<li>{render_nested(subitem, indent+1)}</li>" for subitem in data)
    html += "</ul>"

    return html


def render_nested_dict(data, indent=0):
    """Recursively renders nested dictionaries and lists as indented HTML."""
    html = ""

    if not (isinstance(data, dict)):
        return str(data)

    for key, value in data.items():
        if key != "_name":
            html += f"<div style='margin-left:{indent * 20}px;'><strong>{key}:</strong> "
            html += render_nested(value, indent + 1)
            html += "</div>"
    return html


def render_log(log: str):
    """Render a log output as scrollable pre-formatted text with monospaced font"""
    # Escape HTML to prevent rendering as HTML
    escaped_log = html_module.escape(str(log))

    # Generate a unique ID for the container
    container_id = f"log-container-{uuid.uuid4().hex[:8]}"

    html = f"""
        <div id="{container_id}" class="log-container" style="overflow-y: auto; margin: 10px 0; width: 100%; height: 100%;">
            <pre style="font-family: monospace; white-space: pre; margin: 0; padding: 10px; background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; width: 100%; height: 100%;"><code>{escaped_log}</code></pre>
        </div>
        <script>
            (function() {{
                const container = document.getElementById('{container_id}');
                if (container) {{
                    container.scrollTop = container.scrollHeight;
                }}
            }})();
        </script>
    """
    return html


def render_nested(data, indent=0):
    """Recursively renders nested dictionaries and lists as indented HTML."""
    html = ""

    if isinstance(data, dict):
        html += render_nested_dict(data, indent)
    elif isinstance(data, list):
        html += render_nested_list(data, indent)
    else:
        html += str(data)

    return html


def render_folding_value(name: str, path: str):
    id = path.replace("/", "-")[1:]
    result = f"""
        <div class="endpoint-container" id="container-{id}" data-path="{path}">
            <div class="header" onclick="toggleSection('{path}', 'container-{id}')">
                <span class="toggle-icon">▶</span>
                <h3>{name}</h3>
                <span id="refresh-{id}" class="refresh-icon refresh-{id}" 
                    hx-get="{path}" 
                    hx-target="#output-{id}" 
                    onclick="refreshData(event, 'container-{id}', 'refresh-{id}', '{path}')">
                  ↻
                </span>
            </div>
            <div id="output-{id}" sse-swap="{id}" class="output-container"></div>
        </div>
    """

    return result


def render_simple_value(name: str, path: str):
    id = path.replace("/", "-")[1:]
    result = f"""
        <div class="endpoint-container" id="container-{id}" data-path="{path}">
            <div class="header" style="align-items: center;">
                <h3 style="margin-right: 10px;">{name}:</h3>
                <div id="output-{id}" class="output-container" sse-swap="{id}" style="display: flex; display: inline-block; margin-left: 15px; border-top: none; padding: 0;"></div>
                <span id="refresh-{id}" class="refresh-icon refresh-{id}" 
                    hx-get="{path}"
                    hx-target="#output-{id}" 
                    onclick="refreshData(event, 'container-{id}', 'refresh-{id}', '{path}')">
                ↻
                </span>
            </div>
        </div>
    """

    return result


def render_action(name: str, path: str, rendered: str):
    id = path.replace("/", "-")[1:]
    result = f"""
        <div class="endpoint-container" id="container-{id}" data-path="{path}">
            <div class="header" style="align-items: center;">
                <h3 style="margin-right: 10px;">{name}:</h3>
                {rendered}
                <div id="output-{id}" class="output-container" sse-swap="{id}" style="display: inline-block; margin-left: 15px;"></div>
            </div>
        </div>
    """

    return result


renderers: Dict[str, Any] = {}
ref_types: Dict[str, Dict[str, Any]] = {}


class RendererBase:
    def __init_subclass__(cls, *, name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        renderer_registry.register(name, cls)

    def __init__(self, settings: Dict[str, Any]):
        self.folding = settings.get("folding", False)
        self.streaming = True

    def render_data(self, data: Any) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def render_list_item(self, name: str, path: str) -> str:
        if self.folding:
            return render_folding_value(name, path)
        else:
            return render_simple_value(name, path)


renderer_registry = TypeRegistry[RendererBase]("renderer")


def make_renderer(settings: Dict[str, Any] | str) -> Tuple[RendererBase, Dict[str, Any]]:
    return renderer_registry.make(settings)


# Fix the load_renderer_types function
def load_renderer_types(settings: Dict[str, Any]):
    for name, ref_settings in settings.items():
        renderer_registry.register_ref(name, ref_settings)
        ref_types[name] = ref_settings  # Keep for backward compatibility


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
        return render_nested(data)


class LogRenderer(RendererBase, name="log"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.folding = settings.get("folding", True)

    def render_data(self, data: dict) -> str:
        return render_log(data)


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


class ActionRenderer(RendererBase, name="action"):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)

    def render_data(self, data: "ActionBase") -> str:
        id = uuid.uuid4().hex

        btn_id = f"btn-{id}"
        output_id = f"output-{id}"
        return f"""
            <button id="{btn_id}" class="action-button" 
            hx-post="{data.url}" 
            hx-target="#{output_id}" 
            hx-swap="innerHTML"
            hx-headers='{{"Content-Type": "application/json"}}'
            hx-vals='{{}}'>
            {data.display_name}
            </button>
            <div id="{output_id}" class="action-output"></div>
        """
