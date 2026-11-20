from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from bot.core.plugin import OSINTPlugin, PluginResult

ProgressCallback = Callable[[PluginResult, int, int], Awaitable[None]]


class Runner:
    def __init__(self, max_concurrent: int = 4) -> None:
        self._sem = asyncio.Semaphore(max(1, max_concurrent))

    async def run_many(
        self,
        plugins: list[OSINTPlugin],
        target: str,
        on_done: ProgressCallback | None = None,
    ) -> list[PluginResult]:
        total = len(plugins)
        counter = {"done": 0}

        async def run_one(plugin: OSINTPlugin) -> PluginResult:
            async with self._sem:
                started = time.perf_counter()
                result: PluginResult
                try:
                    result = await asyncio.wait_for(plugin.run(target), timeout=plugin.default_timeout)
                except asyncio.TimeoutError:
                    result = PluginResult(plugin=plugin.name, title=plugin.title, target=target, ok=False)
                    result.errors.append(f"превышен таймаут {plugin.default_timeout} с")
                except Exception as exc:  # noqa: BLE001
                    result = PluginResult(plugin=plugin.name, title=plugin.title, target=target, ok=False)
                    result.errors.append(f"{type(exc).__name__}: {exc}")
                result.elapsed = time.perf_counter() - started
                counter["done"] += 1
                if on_done is not None:
                    try:
                        await on_done(result, counter["done"], total)
                    except Exception:  # noqa: BLE001
                        pass
                return result

        return list(await asyncio.gather(*(run_one(plugin) for plugin in plugins)))
