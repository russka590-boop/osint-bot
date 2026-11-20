from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_session: Any = None
_lock: asyncio.Lock | None = None


async def get_session() -> Any:
    global _session, _lock
    import aiohttp

    if _lock is None:
        _lock = asyncio.Lock()
    if _session is None or _session.closed:
        async with _lock:
            if _session is None or _session.closed:
                _session = aiohttp.ClientSession(
                    headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                    timeout=aiohttp.ClientTimeout(total=40),
                )
    return _session


async def close() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def get_text(
    url: str,
    *,
    timeout: float = 25,
    headers: dict[str, str] | None = None,
    allow_redirects: bool = True,
) -> tuple[str | None, str]:
    import aiohttp

    try:
        session = await get_session()
        async with session.get(
            url,
            headers=headers,
            allow_redirects=allow_redirects,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status >= 400:
                return None, f"HTTP {response.status}"
            return await response.text(errors="replace"), ""
    except asyncio.TimeoutError:
        return None, f"таймаут {timeout:.0f} с"
    except aiohttp.ClientError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


async def get_json(
    url: str,
    *,
    timeout: float = 25,
    headers: dict[str, str] | None = None,
) -> tuple[Any, str]:
    import json

    text, error = await get_text(url, timeout=timeout, headers=headers)
    if error:
        return None, error
    try:
        return json.loads(text or ""), ""
    except json.JSONDecodeError as exc:
        return None, f"невалидный JSON: {exc}"


async def head_status(url: str, *, timeout: float = 20) -> tuple[int | None, str | None, str]:
    import aiohttp

    try:
        session = await get_session()
        async with session.get(
            url,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"Accept": "text/html"},
        ) as response:
            return response.status, response.headers.get("Location"), ""
    except asyncio.TimeoutError:
        return None, None, f"таймаут {timeout:.0f} с"
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"
