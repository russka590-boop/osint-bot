from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

DENY_TEXT = "Доступ к боту закрыт. Напишите /msg ваш_текст, чтобы отправить заявку администратору."
PUBLIC_COMMANDS = ("/start", "/help", "/msg")

_role_lookup: Callable[[int], Awaitable[str | None]] | None = None


def bind_roles(lookup: Callable[[int], Awaitable[str | None]]) -> None:
    global _role_lookup
    _role_lookup = lookup


async def is_allowed(user_id: int) -> bool:
    if settings.is_admin(user_id):
        return True
    if user_id in settings.allowed_ids:
        return True
    if _role_lookup is not None:
        try:
            role = await _role_lookup(user_id)
        except Exception:  # noqa: BLE001
            role = None
        if role == "trusted":
            return True
        if role == "banned":
            return False
    return not settings.allowed_ids


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if not await is_allowed(user.id):
            if isinstance(event, Message):
                command = (event.text or "").split(maxsplit=1)[0].split("@")[0].lower()
                if command in PUBLIC_COMMANDS:
                    return await handler(event, data)
                await event.answer(f"{DENY_TEXT}\nВаш ID: {user.id}")
            elif isinstance(event, CallbackQuery):
                await event.answer(f"{DENY_TEXT} Ваш ID: {user.id}", show_alert=True)
            return None
        return await handler(event, data)


class Cooldown:
    def __init__(self, seconds: int) -> None:
        self._seconds = seconds
        self._last: dict[int, float] = {}

    def check(self, user_id: int) -> int:
        if self._seconds <= 0:
            return 0
        now = time.monotonic()
        last = self._last.get(user_id, 0.0)
        remaining = self._seconds - (now - last)
        if remaining > 0:
            return int(remaining) + 1
        self._last[user_id] = now
        return 0


cooldown = Cooldown(settings.user_cooldown)
