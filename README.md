# OSINT-бот

Telegram-бот, который собирает информацию из **открытых источников** и складывает результаты
в один отчёт. Работает как обёртка над популярными open-source инструментами, плюс собственные
модули для веб-архивов и DNS.

## Что внутри

| Модуль | Что делает | Тип цели |
| --- | --- | --- |
| `maigret` | ник по базе площадок (~3000 сайтов) | username |
| `blackbird` | ник и email по площадкам | username, email |
| `archives` | Wayback Machine, archive.today, Memento, Common Crawl | url, domain |
| `domains` | DNS-записи и поддомены из crt.sh | domain |

Новые инструменты добавляются одним файлом в `bot/plugins/` — ядро их находит само.

## Рамки

Бот работает только с публичными данными: открытые профили, логи Certificate Transparency,
DNS, публичные архивы страниц. Он не ходит в закрытые базы, не подбирает пароли, не обходит
авторизацию и не ищет данные, доступ к которым ограничен. Перед массовыми проверками сверьтесь
с ToS площадок и 152-ФЗ: сбор и хранение персональных данных третьих лиц требует законного
основания.

## Установка

### Вариант 1. Локально (Windows/Linux)

```powershell
cd osint-bot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
python run.py
```

На Linux/macOS вместо активации: `source .venv/bin/activate`.

Нужен Python 3.11+. На 3.14 часть зависимостей может требовать свежих колёс — если `pip install`
ругается, используйте 3.12.

### Вариант 2. Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f
```

Собрать сразу с Maigret: `INSTALL_MAIGRET=1` в `docker-compose.yml` → `args`.

### Внешние CLI

- **Maigret**: `pip install maigret`, затем `MAIGRET_CMD=maigret`.
- **BlackBird**: склонируйте `https://github.com/p1ngul1n0/blackbird`, поставьте зависимости,
  укажите путь: `BLACKBIRD_CMD=python C:\tools\blackbird\blackbird.py`.

Если инструмент не установлен, бот не падает: модуль помечается «недоступен» в `/plugins`,
остальные работают.

## Команды

- `/start` — меню выбора типа цели
- `/scan username vasya` — полный скан
- `/scan domain example.com`
- `/archives https://example.com/page` — только веб-архивы
- `/plugins` — состояние модулей
- `/stats` — ваша статистика
- `/log` — журнал запросов (админ)
- `/cancel` — сброс

Отчёт приходит файлом `.md` и сохраняется в `reports/`.

## Доступ

`ALLOWED_USER_IDS` — список Telegram ID через запятую. Пустое значение = бот открыт всем,
это удобно для теста и плохо для продакшена. `ADMIN_IDS` даёт доступ к `/log`.

## Как добавить свой модуль

Создайте `bot/plugins/my_plugin.py`:

```python
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register


class MyPlugin(OSINTPlugin):
    name = "my_plugin"
    title = "Мой источник"
    input_types = (TargetKind.DOMAIN,)
    default_timeout = 30

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        result.findings.append(
            Finding(source="my_source", status="found", url=f"https://{target}", details="пример")
        )
        return result


register(MyPlugin())
```

Перезапуск — модуль появится в `/plugins` и в сканах для доменов.

## Структура

```
bot/
  config.py          настройки из .env
  main.py            хендлеры aiogram
  keyboards.py       меню
  core/
    plugin.py        базовый класс, реестр, типы целей
    runner.py        параллельный запуск с таймаутами
    report.py        markdown-отчёт
    storage.py       SQLite-журнал запросов
    access.py        whitelist и кулдаун
    net.py           общий aiohttp-клиент
    cli.py           запуск внешних утилит
    utils.py         нормализация целей, чанки
  plugins/           модули (автоподхват)
tools/selftest.py    офлайн-проверка парсеров и нормализации
```

## Проверка

```bash
python tools/selftest.py
python -m compileall bot
```

## Ограничения

- Публичные API (crt.sh, archive.org, Common Crawl) периодически отвечают 429/503 — модуль
  покажет ошибку, скан продолжится.
- Maigret на полной базе идёт долго; по умолчанию `--top-sites 500`, таймаут 180 с.
- Чужие CLI меняют формат вывода. Если BlackBird обновился и парсер не видит результаты,
  поправьте `parse_blackbird` в `bot/plugins/blackbird_plugin.py` — он изолирован.
