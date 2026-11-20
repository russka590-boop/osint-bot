from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ErrorEvent,
    FSInputFile,
    Message,
)

from bot.config import settings
from bot.core import net
from bot.core.access import AccessMiddleware, cooldown
from bot.core.plugin import REGISTRY, TargetKind, plugins_for
from bot.core.report import build_markdown, summary_text, write_report
from bot.core.runner import Runner
from bot.core.storage import Storage
from bot.core.utils import chunk, detect_kind, human_duration, normalize
from bot.keyboards import kinds_keyboard
from bot.plugins import load_plugins

log = logging.getLogger(__name__)

router = Router()
runner = Runner(settings.max_concurrent_jobs)
storage: Storage | None = None

WELCOME = (
    "OSINT-бот: сбор только из открытых источников.\n\n"
    "Что умеет:\n"
    "— ник: Maigret (~3000 площадок), BlackBird, GitHub/GitLab/Reddit/HN/Keybase;\n"
    "— Telegram: занят ли ник, что видно на публичной странице t.me;\n"
    "— VK: профиль и публичные подписки по нику (нужен VK_TOKEN);\n"
    "— домен: DNS, поддомены из crt.sh, регистратор через RDAP;\n"
    "— IP: сеть, страна и диапазон через RDAP;\n"
    "— URL: сохранённые копии в веб-архивах (Wayback, archive.today, Memento, Common Crawl);\n"
    "— телефон: страна, оператор и регион номера (без владельца).\n\n"
    "Команды:\n"
    "/scan <тип> <цель> — тип: username, email, domain, url, ip, phone\n"
    "/archives <url> — только веб-архивы\n"
    "/plugins — какие модули доступны\n"
    "/stats — ваша статистика\n"
    "/cancel — сбросить выбор\n\n"
    "Выберите тип цели:"
)


class ScanForm(StatesGroup):
    waiting_target = State()


def _db() -> Storage:
    if storage is None:
        raise RuntimeError("storage is not initialised")
    return storage


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=kinds_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=kinds_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Состояние сброшено.", reply_markup=kinds_keyboard())


@router.message(Command("plugins"))
async def cmd_plugins(message: Message) -> None:
    await message.answer(await _plugins_report())


@router.callback_query(F.data == "plugins:list")
async def cb_plugins(callback: CallbackQuery) -> None:
    await callback.message.answer(await _plugins_report())
    await callback.answer()


async def _plugins_report() -> str:
    if not REGISTRY:
        return "Модули не загружены."
    lines: list[str] = ["Модули:"]
    for plugin in REGISTRY.values():
        ready, note = await plugin.ready()
        state_text = "готов" if ready else f"недоступен — {note}"
        kinds = ", ".join(kind.value for kind in plugin.input_types)
        lines.append(f"— {plugin.title} [{plugin.name}]: {state_text} (типы: {kinds})")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("kind:"))
async def cb_kind(callback: CallbackQuery, state: FSMContext) -> None:
    raw = (callback.data or "").split(":", 1)[-1]
    try:
        kind = TargetKind(raw)
    except ValueError:
        await callback.answer("Неизвестный тип", show_alert=True)
        return
    await state.set_state(ScanForm.waiting_target)
    await state.update_data(kind=kind.value)
    await callback.message.answer(f"{kind.title}: пришлите цель одним сообщением.")
    await callback.answer()


@router.message(ScanForm.waiting_target, F.text)
async def got_target(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    try:
        kind = TargetKind(data.get("kind", "username"))
    except ValueError:
        kind = TargetKind.USERNAME
    await scan_and_reply(message, kind, (message.text or "").strip())


@router.message(Command("scan"))
async def cmd_scan(message: Message, command: CommandObject) -> None:
    args = (command.args or "").strip()
    if not args:
        await message.answer("Формат: /scan username vasya или /scan domain example.com")
        return
    parts = args.split(maxsplit=1)
    if len(parts) == 1:
        kind = detect_kind(parts[0])
        await scan_and_reply(message, kind, parts[0])
        return
    raw_kind, target = parts
    try:
        kind = TargetKind(raw_kind.lower())
    except ValueError:
        await message.answer("Тип цели: username, email, domain или url.")
        return
    await scan_and_reply(message, kind, target.strip())


@router.message(Command("archives"))
async def cmd_archives(message: Message, command: CommandObject) -> None:
    target = (command.args or "").strip()
    if not target:
        await message.answer("Формат: /archives https://example.com/page")
        return
    await scan_and_reply(message, TargetKind.URL, target, only={"archives"})


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    total, found = await _db().stats(message.from_user.id)
    await message.answer(f"Запросов: {total}\nВсего находок: {found}")


@router.message(Command("log"))
async def cmd_log(message: Message) -> None:
    if not settings.is_admin(message.from_user.id):
        await message.answer("Команда только для администратора.")
        return
    rows = await _db().recent(20)
    if not rows:
        await message.answer("Журнал пуст.")
        return
    lines = ["Последние запросы:"]
    for created, user_id, username, kind, target, found, elapsed, status in rows:
        who = username or user_id
        lines.append(f"{created} · {who} · {kind} · {target} · находок {found} · {elapsed:.0f} с · {status}")
    for part in chunk("\n".join(lines)):
        await message.answer(part)


@router.message(F.text)
async def free_text(message: Message) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        return
    await scan_and_reply(message, detect_kind(raw), raw)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.error("ошибка обработки обновления", exc_info=event.exception)
    message = event.update.message
    if message is not None:
        try:
            await message.answer("Не получилось обработать запрос. Попробуйте ещё раз.")
        except Exception:  # noqa: BLE001
            pass
    return True


async def scan_and_reply(
    message: Message,
    kind: TargetKind,
    raw: str,
    only: set[str] | None = None,
) -> None:
    user = message.from_user
    if user is None:
        return
    wait = cooldown.check(user.id)
    if wait:
        await message.answer(f"Слишком часто. Подождите {wait} с.")
        return

    ok, target, error = normalize(kind, raw)
    if not ok:
        await message.answer(f"Неверная цель — {error}")
        return

    candidates = [plugin for plugin in plugins_for(kind) if only is None or plugin.name in only]
    if not candidates:
        await message.answer("Для этого типа цели нет модулей.")
        return

    active = []
    skipped: list[str] = []
    for plugin in candidates:
        ready, note = await plugin.ready()
        if ready:
            active.append(plugin)
        else:
            skipped.append(f"{plugin.title}: {note}")

    if not active:
        await message.answer("Нет доступных модулей:\n" + "\n".join(skipped))
        return

    started_at = datetime.now(timezone.utc)
    hint = "\nПолный скан занимает 10–20 минут." if any(
        plugin.name == "maigret" for plugin in active
    ) else ""
    status = await message.answer(
        f"Сканирую: {target}\nТип: {kind.title}\nМодулей: {len(active)}{hint}"
    )
    began = time.perf_counter()

    async def on_done(result, done: int, total: int) -> None:
        try:
            await status.edit_text(
                f"{done}/{total} готово: {result.title}\nЦель: {target}"
            )
        except Exception:  # noqa: BLE001
            pass

    results = await runner.run_many(active, target, on_done)
    elapsed = time.perf_counter() - began
    found_total = sum(len(result.found) for result in results)

    markdown = build_markdown(kind, target, results, started_at, elapsed)
    path = write_report(kind, target, markdown, settings.report_dir, started_at)

    summary = summary_text(results)
    head = f"Готово за {human_duration(elapsed)}. Находок: {found_total}."
    if skipped:
        head += "\nНе запущены:\n" + "\n".join(skipped)
    body = f"{head}\n\n{summary}"
    try:
        await status.edit_text(body[:4000])
    except Exception:  # noqa: BLE001
        await message.answer(body[:4000])

    try:
        await message.answer_document(
            FSInputFile(path), caption=f"{kind.title}: {target} · находок {found_total}"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось отправить отчёт: %s", exc)
        await message.answer(f"Отчёт сохранён: {path}")

    await _db().log_query(
        user_id=user.id,
        username=user.username,
        kind=kind.value,
        target=target,
        plugins=",".join(plugin.name for plugin in active),
        found=found_total,
        elapsed=elapsed,
    )


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="меню"),
            BotCommand(command="scan", description="скан: /scan username vasya"),
            BotCommand(command="archives", description="поиск в веб-архивах"),
            BotCommand(command="plugins", description="доступные модули"),
            BotCommand(command="stats", description="моя статистика"),
            BotCommand(command="cancel", description="сбросить выбор"),
        ]
    )


async def main() -> None:
    global storage
    if not settings.token:
        raise SystemExit("BOT_TOKEN не задан. Заполните .env (см. .env.example).")

    settings.ensure_dirs()
    storage = Storage(settings.db_path)
    await storage.connect()
    load_plugins()

    bot = Bot(settings.token, default=DefaultBotProperties())
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.callback_query.middleware(AccessMiddleware())
    dispatcher.include_router(router)

    try:
        await _set_commands(bot)
    except Exception as exc:  # noqa: BLE001
        log.warning("не удалось обновить список команд: %s", exc)
    log.info("модулей загружено: %s", ", ".join(REGISTRY) or "нет")
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await net.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
