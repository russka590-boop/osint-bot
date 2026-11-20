from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import settings

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]

DENY_TEXT = "Доступ к боту закрыт. Передайте свой ID администратору."


def is_allowed(user_id: int) -> bool:
    if settings.is_admin(user_id):
        return True
    if not settings.allowed_ids:
        return True
    return user_id in settings.allowed_ids


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if not is_allowed(user.id):
            if isinstance(event, Message):
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
