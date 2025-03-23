import json
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import yaml
from frame.model import Config
import asyncio
from fastapi.responses import StreamingResponse
from frame.images import image_repo

from collections import OrderedDict

from frame.renderers import render_action, render_simple_value


def ordered_yaml_load(stream):
    """Loads YAML while preserving key order."""

    class OrderedLoader(yaml.SafeLoader):
        pass

    def construct_ordered_mapping(loader, node):
        return OrderedDict(loader.construct_pairs(node))

    OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_ordered_mapping)

    return yaml.load(stream, OrderedLoader)


app = FastAPI()
config = Config(ordered_yaml_load(open("src/frame/examples/example_config.yaml")))


async def get_system_info():
    """Runs system_profiler asynchronously and returns the parsed JSON output."""
    process = await asyncio.create_subprocess_exec(
        "system_profiler",
        "-detailLevel",
        "mini",
        "-json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        return {"error": stderr.decode()}

    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        return {"error": str(e)}


@app.get("/system_info", response_class=HTMLResponse)
async def system_info():
    data = await get_system_info()
    return json.dumps(data, indent=2)


def make_endpoints():
    endpoints_future = asyncio.Future[list[Dict[str, Any]]]()
    actions_future = asyncio.Future[list[Dict[str, Any]]]()

    def make(_):
        endpoints: list[Dict[str, Any]] = []

        for property_name in config.get_properties():
            property = config.get_property(property_name)

            endpoint_path = config.get_property_path(property_name)

            @app.get(endpoint_path, response_class=HTMLResponse)
            async def get_property_value(property_name=property_name):
                queue = asyncio.Queue[Any]()
                with config.subscribe_rendered_updates(property_name, queue) as sub:
                    _, rendered = await queue.get()
                    return rendered

            if property.update_time:
                config.auto_update(property_name, property.update_time)

            # Add to list of endpoints
            endpoints.append(
                {
                    "path": endpoint_path,
                    "name": property.display_name,
                    "render_func": property.renderer.render_list_item,
                }
            )

        @app.get("/updates")
        async def get_rendered_update_stream():
            return StreamingResponse(
                config.get_rendered_update_stream(),
                media_type="text/event-stream",
            )

        endpoints_future.set_result(endpoints)

        actions: list[Dict[str, Any]] = []

        @app.post("/action/{action_name}", response_class=HTMLResponse)
        async def do_action(action_name: str, params: Dict[str, Any] = {}):
            params_to_use = params or {}
            return await config.do(action_name, params_to_use)

        for action_name in config.get_actions():
            rendered = config.get_rendered_action(action_name)

            if rendered:
                action_path = f"/action/{action_name}"
                actions.append({"rendered": rendered, "render_func": render_action, "name": action_name, "path": action_path})

        actions_future.set_result(actions)

    config.done().add_done_callback(make)

    return endpoints_future, actions_future


endpoints_future, actions_future = make_endpoints()


@app.get("/", response_class=HTMLResponse)
async def home():
    # Define endpoints and their display names

    endpoints = await endpoints_future
    actions = await actions_future

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/htmx.org@1.9.5"></script>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap">
        <style>
            :root {{
            
            /* Dark mode variables */
            --dark-bg-color: #1a1a1a;
            --dark-card-bg: #2d2d2d;
            --dark-text-primary: #f5f5f7;
            --dark-text-secondary: #a1a1a6;
            --dark-accent-color: #0a84ff;
            --dark-border-color: #3a3a3c;
            --dark-hover-color: #3a3a3a;

            /* Dark mode variables */
            --bg-color: #f5f5f7;
            --card-bg: #ffffff;
            --text-primary: #1d1d1f;
            --text-secondary: #6e6e73;
            --accent-color: #0071e3;
            --border-color: #e0e0e0;
            --hover-color: #f0f0f0;
            
            /* Button styles */
            --button-radius: 6px;
            --button-transition: all 0.2s ease;
            --button-shadow: 0 1px 2px rgba(0,0,0,0.07);
            --button-shadow-pressed: 0 1px 1px rgba(0,0,0,0.1);

            button {{
                background-color: var(--accent-color);
                color: white;
                border: none;
                border-radius: var(--button-radius);
                padding: 8px 16px;
                font-family: inherit;
                font-size: 0.9rem;
                font-weight: 500;
                cursor: pointer;
                transition: var(--button-transition);
                box-shadow: var(--button-shadow);
                outline: none;
            }}

            button:hover {{
                background-color: rgba(0, 113, 227, 0.9);
                transform: translateY(-1px);
            }}

            button:active {{
                background-color: rgba(0, 113, 227, 0.8);
                transform: translateY(1px);
                box-shadow: var(--button-shadow-pressed);
            }}

            button:disabled {{
                background-color: #b0b0b0;
                cursor: not-allowed;
                transform: none;
            }}

            button.waiting {{
                background-color: rgba(0, 113, 227, 0.6);
                position: relative;
                color: transparent;
                pointer-events: none;
            }}

            button.waiting::after {{
                content: "";
                position: absolute;
                top: 50%;
                left: 50%;
                width: 16px;
                height: 16px;
                margin-top: -8px;
                margin-left: -8px;
                border-radius: 50%;
                border: 2px solid rgba(255, 255, 255, 0.25);
                border-top-color: white;
                animation: spin 0.8s linear infinite;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-primary);
                line-height: 1.5;
                padding: 2rem;
                max-width: 800px;
                margin: 0 auto;
            }}
            
            h1 {{
                font-weight: 500;
                font-size: 1.8rem;
                margin-bottom: 1.5rem;
                color: var(--text-primary);
                letter-spacing: -0.5px;
            }}
            
            .endpoint-container {{
                margin-bottom: 1rem;
                background-color: var(--card-bg);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                transition: all 0.2s ease;
            }}
            
            .endpoint-container:hover {{
                box-shadow: 0 3px 8px rgba(0,0,0,0.15);
            }}
            
            .header {{
                display: flex;
                padding: 0.5rem;
                align-items: center;
                cursor: pointer;
                user-select: none;
                border-bottom: 1px solid transparent;
                transition: background-color 0.2s ease;
            }}
            
            .header:hover {{
                background-color: var(--hover-color);
            }}
            
            .toggle-icon {{
                width: 20px;
                flex-shrink: 0;
                font-size: 12px;
                color: var(--text-secondary);
                transition: transform 0.3s ease;
                transform-origin: 25% 50%;
            }}
            
            .header h3 {{
                margin: 0;
                flex-grow: 1;
                font-weight: 500;
                font-size: 1rem;
                margin-left: 0.5rem;
            }}
            
            .refresh-icon {{
                cursor: pointer;
                color: var(--text-secondary);
                font-size: 14px;
                margin-left: 8px;
                padding: 4px;
                border-radius: 50%;
                transition: all 0.2s ease;
            }}
            
            .refresh-icon:hover {{
                background-color: rgba(0,0,0,0.05);
                color: var(--accent-color);
            }}
            
            .output-container {{
                padding: 1rem;
                background-color: var(--card-bg);
                border-top: 1px solid var(--border-color);
                font-size: 0.9rem;
                color: var(--text-secondary);
                display: none;
                overflow: auto;
                max-height: 400px;
            }}
            
            .expanded .toggle-icon {{
                transform: rotate(90deg);
                transform-origin: 25% 50%;
            }}
            
            .expanded .output-container {{
                display: block;
            }}
            
            .expanded .header {{
                border-bottom: 1px solid var(--border-color);
            }}
            
            .screenshot-img {{ 
                width: 400px; 
                cursor: pointer;
                transform-origin: center center;
                # transition: all 0.3s ease; 
            }}
            
            .fullsize {{ 
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                transform-origin: center center;
                max-width: 90%;
                max-height: 90vh;
                width: auto;
                height: auto;
                z-index: 1000;
                box-shadow: 0 5px 30px rgba(0,0,0,0.3);
                object-fit: contain;
            }}
            
            .lightbox-overlay {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.8);
                z-index: 999;
                display: none;
                opacity: 0;
                transition: opacity 0.3s ease;
            }}
            
            .lightbox-overlay.active {{
                display: block;
                opacity: 1;
            }}

            .value {{
                font-family: monospace, monospace;
                background-color: rgba(0, 0, 0, 0.05);
                padding: 6px;
                border-radius: 4px;
            }}

            .success {{
                color: green;
                background-color: rgba(0, 255, 0, 0.1);
            }}

            .failure {{
                color: red;
                background-color: rgba(255, 0, 0, 0.1);
            }}
                
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            
            .spinning {{
                animation: spin 1s linear infinite;
            }}
        </style>
    </head>
    <body>
        <div id="lightbox-overlay" class="lightbox-overlay"></div>
        <h1>{config.project_name}</h1>

        {"\n".join(value['render_func'](value['name'], value['path']) for i, value in enumerate(endpoints))}

        <h2>Actions:</h2>
        {"\n".join(value['render_func'](value['name'], value['path'], value['rendered']) for i, value in enumerate(actions))}

        <script>
            // Load saved states when page loads
            document.addEventListener('DOMContentLoaded', function() {{
                // For each container, check if it was expanded
                document.querySelectorAll('.endpoint-container').forEach(container => {{
                    const path = container.getAttribute('data-path');
                    const isExpanded = localStorage.getItem('expanded_' + path) === 'true';
                    
                    if (isExpanded) {{
                        container.classList.add('expanded');
                        
                        // Also load the data if it was expanded
                        const refreshIcon = container.querySelector('.refresh-icon');
                        if (refreshIcon) {{
                            // Trigger the htmx request
                            htmx.trigger(refreshIcon, 'click');
                        }}
                    }}
                }});
                
                // Set up lightbox overlay click handler
                document.getElementById('lightbox-overlay').addEventListener('click', function() {{
                    const fullsizeImages = document.querySelectorAll('.fullsize');
                    fullsizeImages.forEach(img => {{
                        img.classList.remove('fullsize');
                    }});
                    this.classList.remove('active');
                }});
                
                // Set up image click handlers after content is loaded
                document.body.addEventListener('htmx:afterOnLoad', function() {{
                    setupImageHandlers();
                }});
            }});
            
            function setupImageHandlers() {{
                document.querySelectorAll('.screenshot-img').forEach(img => {{
                    img.addEventListener('click', function(e) {{
                        const overlay = document.getElementById('lightbox-overlay');
                        
                        if (this.classList.contains('fullsize')) {{
                            this.classList.remove('fullsize');
                            overlay.classList.remove('active');
                        }} else {{
                            this.classList.add('fullsize');
                            overlay.classList.add('active');
                            e.stopPropagation();
                        }}
                    }});
                }});
            }}
            
            function toggleSection(path, id) {{
                const container = document.getElementById(id);
                const wasExpanded = container.classList.contains('expanded');
                container.classList.toggle('expanded');
                
                // Store state in localStorage
                localStorage.setItem('expanded_' + path, (!wasExpanded).toString());
                
                // If we're expanding and there's no content yet, trigger the refresh
                if (!wasExpanded && container.querySelector('.output-container').innerHTML.trim() === '') {{
                    const refreshIcon = container.querySelector('.refresh-icon');
                    if (refreshIcon) {{
                        // Trigger the htmx request without the animation
                        htmx.ajax('GET', refreshIcon.getAttribute('hx-get'), {{target: refreshIcon.getAttribute('hx-target')}});
                    }}
                }}
            }}
            
            function refreshData(event, containerId, refreshIconId, path) {{
                event.stopPropagation();
                
                // Add spinning animation
                const refreshIcon = document.getElementById(refreshIconId);
                refreshIcon.classList.add('spinning');
                
                // Ensure container is expanded
                const container = document.getElementById(containerId);
                container.classList.add('expanded');
                
                // Save expanded state to localStorage
                localStorage.setItem('expanded_' + path, 'true');
                
                // Remove spinning after data loads
                document.getElementById(refreshIconId).addEventListener('htmx:afterOnLoad', function() {{
                    refreshIcon.classList.remove('spinning');
                    setupImageHandlers(); // Set up image handlers after content loads
                }}, {{once: true}});
            }}

            (new EventSource("/updates")).onmessage = function(event) {{
                let data = JSON.parse(event.data);
                let element = document.getElementById(`output-${{data.id}}`);
                element.innerHTML = data.rendered;
            }};
        </script>
    </body>
    </html>
    """


@app.get("/images/{image_name}")
async def get_image(image_name: str):
    # Define directory where images are stored
    image_file, extension = image_repo.get_image_stream(image_name)

    # Determine content type based on file extension
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    content_type = content_types.get(extension, "application/octet-stream")

    # Create a file stream
    def iterfile():
        with image_file as file:
            yield from file

    # Return a streaming response with the appropriate content type
    return StreamingResponse(iterfile(), media_type=content_type)
