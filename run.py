from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError

from bot.main import main

log = logging.getLogger("run")


async def _loop() -> None:
    delay = 5
    while True:
        try:
            await main()
            return
        except TelegramNetworkError as exc:
            log.warning("нет связи с Telegram API (%s). Повтор через %s с.", exc, delay)
        except Exception as exc:  # noqa: BLE001
            log.exception("бот остановился с ошибкой: %s", exc)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(_loop())
    except KeyboardInterrupt:
        print("остановлено")
