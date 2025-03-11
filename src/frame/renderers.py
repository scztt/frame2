from typing import Dict, Any, Generic, Type
import uuid

from annotated_types import T
from frame.images import ImageRef
from frame.registry import TypeRegistry


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
            html += (
                f"<div style='margin-left:{indent * 20}px;'><strong>{key}:</strong> "
            )
            html += render_nested(value, indent + 1)
            html += "</div>"
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
    id = path.replace("/", "-")
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

    return result


def render_simple_value(name: str, path: str):
    id = path.replace("/", "-")
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

    def render_data(self, data) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def render_list_item(self, name: str, path: str) -> str:
        if self.folding:
            return render_folding_value(name, path)
        else:
            return render_simple_value(name, path)


renderer_registry = TypeRegistry[RendererBase]("renderer")


def make_renderer(settings: Dict[str, Any] | str):
    """Legacy function for backward compatibility"""
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
