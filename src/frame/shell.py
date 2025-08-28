from functools import singledispatch
import asyncio
import os
from typing import List, Union


async def run_command_str(value: str, sudo: bool = False):
    if sudo:
        sudo_password = os.environ.get("SUDO_PASSWORD")
        if sudo_password:
            # Use password with sudo -S
            command = f"echo '{sudo_password}' | sudo -S {value}"
        else:
            # Assume NOPASSWD sudo is configured
            command = f"sudo {value}"
    else:
        command = value
        
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(stderr.decode())

    return stdout.decode()


async def run_command_list(value: List[str], sudo: bool = False):
    if sudo:
        sudo_password = os.environ.get("SUDO_PASSWORD")
        if sudo_password:
            # For list commands with sudo + password, we need to use shell mode
            command_str = " ".join(value)
            command = f"echo '{sudo_password}' | sudo -S {command_str}"
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            # Use exec mode with sudo prepended
            process = await asyncio.create_subprocess_exec(
                "sudo", *value,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
    else:
        process = await asyncio.create_subprocess_exec(
            *value,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(stderr.decode())

    return stdout.decode()


async def run_command(command: Union[str, List[str]], sudo: bool = False):
    if isinstance(command, str):
        return await run_command_str(command, sudo=sudo)
    elif isinstance(command, list):
        return await run_command_list(command, sudo=sudo)
