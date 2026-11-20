from __future__ import annotations

import asyncio
import shlex
import shutil

IS_WINDOWS = __import__("sys").platform.startswith("win")


async def run_cli(
    cmd: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise
    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def split_command(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return shlex.split(raw, posix=not IS_WINDOWS)


def find_binary(raw: str) -> str | None:
    parts = split_command(raw)
    if not parts:
        return None
    return shutil.which(parts[0])
