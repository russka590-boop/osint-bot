from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kinds_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Имя пользователя", callback_data="kind:username"),
                InlineKeyboardButton(text="Email", callback_data="kind:email"),
            ],
            [
                InlineKeyboardButton(text="Домен", callback_data="kind:domain"),
                InlineKeyboardButton(text="URL / архивы", callback_data="kind:url"),
            ],
            [
                InlineKeyboardButton(text="IP-адрес", callback_data="kind:ip"),
                InlineKeyboardButton(text="Телефон", callback_data="kind:phone"),
            ],
            [InlineKeyboardButton(text="Состояние модулей", callback_data="plugins:list")],
        ]
    )
