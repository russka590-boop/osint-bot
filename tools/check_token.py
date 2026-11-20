from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiogram import Bot  # noqa: E402

from bot.config import settings  # noqa: E402
from bot.core.plugin import REGISTRY  # noqa: E402
from bot.plugins import load_plugins  # noqa: E402


async def main() -> int:
    load_plugins()
    print(f"модулей: {len(REGISTRY)}")
    for plugin in REGISTRY.values():
        ready, note = await plugin.ready()
        print(f"  {plugin.name}: {'готов' if ready else 'недоступен'} {note if not ready else ''}".rstrip())

    if not settings.token:
        print("BOT_TOKEN пуст")
        return 1

    bot = Bot(settings.token)
    try:
        me = await bot.get_me()
        print(f"токен валиден: @{me.username} (id {me.id})")
    except Exception as exc:  # noqa: BLE001
        print(f"токен не принят: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await bot.session.close()

    if not settings.allowed_ids:
        print("внимание: ALLOWED_USER_IDS пуст — бот открыт всем")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
