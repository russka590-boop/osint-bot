from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.core.plugin import TargetKind, plugins_for

ENGINE_TITLES = {
    "all": "Все модули",
    "own": "Только наши",
    "maigret": "Maigret",
    "blackbird": "BlackBird",
}


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


def engines_keyboard(kind: TargetKind) -> InlineKeyboardMarkup:
    available = {plugin.name for plugin in plugins_for(kind)}
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="Все модули", callback_data=f"mode:all:{kind.value}"),
            InlineKeyboardButton(text="Только наши", callback_data=f"mode:own:{kind.value}"),
        ]
    ]
    external = [
        (name, ENGINE_TITLES[name])
        for name in ("maigret", "blackbird")
        if name in available
    ]
    if external:
        rows.append(
            [
                InlineKeyboardButton(text=title, callback_data=f"mode:{name}:{kind.value}")
                for name, title in external
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
