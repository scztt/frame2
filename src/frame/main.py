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
from fastapi.responses import FileResponse
import os
from fastapi import Body


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


@app.get("/style.css")
async def get_css():
    return FileResponse("src/frame/static/style.css", media_type="text/css")


@app.get("/script.js")
async def get_script():
    return FileResponse("src/frame/static/script.js", media_type="text/javascript")


@app.get("/images/{image_name}")
async def get_image(image_name: str):
    # Define directory where images are stored
    image_path = image_repo.get_image_path(image_name)
    extension = os.path.splitext(image_path)[1]

    # Determine content type based on file extension
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }

    return FileResponse(image_path, media_type=content_types.get(extension, "application/octet-stream"))


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
        <script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>
        <script src="https://unpkg.com/htmx.org/dist/ext/json-enc.js"></script>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap">
        <link rel="stylesheet" href="style.css">
    </head>
    <body hx-ext="sse" sse-connect="/updates">
        <div id="lightbox-overlay" class="lightbox-overlay"></div>
        <h1>{config.project_name}</h1>
        {"\n".join(value['render_func'](value['name'], value['path']) for i, value in enumerate(endpoints))}
        <h2>Actions:</h2>
        {"\n".join(value['render_func'](value['name'], value['path'], value['rendered']) for i, value in enumerate(actions))}
        <script src="script.js"></script>
    </body>
    </html>
    """
