import asyncio
import json
from typing import Any, Callable, Dict, List
from frame.plugin_interface import Key, PluginBase, PluginInterface, plugin_getter


class SystemInformationPlugin(PluginBase, name="system_information"):
    def setup(self) -> None:
        pass

    def setdown(self) -> None:
        pass

    @plugin_getter
    async def get_system_info(self):
        """Runs system_profiler asynchronously and returns the parsed JSON output."""
        process = await asyncio.create_subprocess_exec(
            "system_profiler",
            "SPHardwareDataType",
            "SPSoftwareDataType",
            "SPStorageDataType",
            "-json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(stderr.decode())

        result = json.loads(stdout.decode())
        return result
