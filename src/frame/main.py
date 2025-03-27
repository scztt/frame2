from functools import wraps
import hashlib
import json
from typing import Any, Dict
from uuid import uuid4
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
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
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from datetime import datetime, timedelta
import secrets
from pydantic import BaseModel



TOKENS = set()


# --- Helper functions ---
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str):
    return hash_password(plain_password) == hashed_password


def ordered_yaml_load(stream):
    """Loads YAML while preserving key order."""

    class OrderedLoader(yaml.SafeLoader):
        pass

    def construct_ordered_mapping(loader, node):
        return OrderedDict(loader.construct_pairs(node))

    OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_ordered_mapping)

    return yaml.load(stream, OrderedLoader)


app = FastAPI()
config = Config(ordered_yaml_load(open("src/frame/examples/corecore.yaml")))


# --- Login Page ---
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap">
        <link rel="stylesheet" href="style.css">
    </head>
    <body>
        <div class="login-container">
            <h1>Login</h1>
            <form action="/login" method="post">
                <label for="password">Password</label>
                <input type="password" name="password" id="password">
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """


# --- Login Endpoint ---
@app.post("/login")
async def login(response: Response, password: str = Form(...)):
    if hashlib.sha256(password.encode()).hexdigest() != config.password_hash:
        raise HTTPException(status_code=401, detail="Incorrect password")
    token = secrets.token_urlsafe(32)
    TOKENS.add(token)
    # Set token in an HTTP-only cookie
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("auth_token", token, httponly=True)
    return response


# Dependency to check token in cookie
async def verify_token_redirect(request: Request):
    token = request.cookies.get("auth_token")
    if not token or token not in TOKENS:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/login"})

# Dependency to check token in cookie
async def verify_token_fail(request: Request):
    token = request.cookies.get("auth_token")
    if not token or token not in TOKENS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

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
        async def get_rendered_update_stream(_=Depends(verify_token_fail)):
            return StreamingResponse(
                config.get_rendered_update_stream(),
                media_type="text/event-stream",
            )

        endpoints_future.set_result(endpoints)

        actions: list[Dict[str, Any]] = []

        @app.post("/action/{action_name}", response_class=HTMLResponse)
        async def do_action(
            action_name: str,
            params: Dict[str, Any] = {},
            _=Depends(verify_token_redirect),
        ):
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
async def get_css(
    _=Depends(verify_token_redirect),
):
    return FileResponse("src/frame/static/style.css", media_type="text/css")


@app.get("/script.js")
async def get_script(
    _=Depends(verify_token_redirect),
):
    return FileResponse("src/frame/static/script.js", media_type="text/javascript")


@app.get("/images/{image_name}")
async def get_image(
    image_name: str,
    _=Depends(verify_token_redirect),
):
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
async def home(
    _=Depends(verify_token_redirect),
):
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
        <div class="actions-list">
        {"\n".join(value['render_func'](value['name'], value['path'], value['rendered']) for i, value in enumerate(actions))}
        </div>
        <script src="script.js"></script>
    </body>
    </html>
    """
