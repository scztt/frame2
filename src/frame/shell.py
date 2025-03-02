from functools import singledispatch
import asyncio
from typing import List


async def run_command_str(value: str):
    process = await asyncio.create_subprocess_shell(
        value,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(stderr.decode())

    return stdout.decode()


async def run_command_list(value: List[str]):
    process = await asyncio.create_subprocess_exec(
        *value,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(stderr.decode())

    return stdout.decode()


async def run_command(command):
    if isinstance(command, str):
        return await run_command_str(command)
    elif isinstance(command, list):
        return await run_command_list(command)
