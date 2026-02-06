import asyncio


async def do_update(cmd: str):
    while True:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(stderr.decode())

        print(stdout)
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    task = asyncio.run(do_update("ps aux | grep bash"))
