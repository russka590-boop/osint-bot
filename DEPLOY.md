# Развёртывание на VPS

Боту нужен сервер с исходящим доступом к `api.telegram.org`. Входящие порты открывать не
нужно: бот сам ходит в Telegram (long polling), никаких доменов и SSL.

Минимальная конфигурация: 1 vCPU, 1 ГБ RAM, Ubuntu 22.04/24.04, 10 ГБ диска.

## 1. Сервер

Подойдёт любой VPS. Варианты:

- **Oracle Cloud Always Free** — бесплатный ARM-инстанс, нужна карта для верификации.
- **Hetzner CX22** — около 4 €/мес.
- **Timeweb / Beget / Aeza** — от 150–300 ₽/мес, оплата картой РФ.

При создании выберите Ubuntu 24.04 и добавьте свой SSH-ключ (или получите пароль root
в письме).

## 2. Загрузка проекта

С локальной машины:

```powershell
scp -r .\osint-bot root@<IP>:/opt/osint-bot
```

Если проект в git-репозитории — на сервере:

```bash
apt-get update && apt-get install -y git
git clone <URL> /opt/osint-bot
```

## 3. Настройка

На сервере:

```bash
cd /opt/osint-bot
cp .env.example .env
nano .env
```

Заполните минимум:

```
BOT_TOKEN=ваш_токен
ALLOWED_USER_IDS=ваш_telegram_id
ADMIN_IDS=ваш_telegram_id
```

`ALLOWED_USER_IDS` обязателен: пустое значение делает бота открытым для всех.

## 4. Запуск

```bash
cd /opt/osint-bot
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

Скрипт поставит Docker при необходимости, соберёт образ и поднимет контейнер.
Проверка:

```bash
sudo docker compose logs -f
```

В логе должно быть:

```
INFO bot.main: модулей загружено: archives, blackbird, domains, maigret
INFO aiogram.dispatcher: Start polling
```

После этого `/start` в Telegram отвечает.

## 5. Автозапуск после перезагрузки

```bash
sudo cp deploy/osint-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now osint-bot
```

Проверка: `systemctl status osint-bot`.

## 6. Обновление

```bash
cd /opt/osint-bot
git pull            # если через git
./deploy/deploy.sh
```

## 7. Данные

- `reports/` — markdown-отчёты (монтируется в контейнер).
- `data/bot.sqlite3` — журнал запросов.
- `.env` — секреты, в образ не попадает (исключён в `.dockerignore`).

Бэкап: `tar czf backup.tgz reports data .env`.

## Если не стартует

```bash
sudo docker compose logs --tail=100
```

- `BOT_TOKEN не задан` — проверьте `.env`, он должен лежать рядом с `docker-compose.yml`.
- `TelegramNetworkError` — сервер не видит `api.telegram.org`; проверьте исходящий доступ.
- `Conflict: terminated by other getUpdates` — где-то запущен второй экземпляр бота
  (например, локально). Остановите его.

## Модули после установки

`archives` и `domains` работают сразу. Для `maigret`:

```bash
sudo docker compose exec bot pip install maigret
```

либо соберите образ с `INSTALL_MAIGRET: "1"` в `docker-compose.yml`.
Для `blackbird` укажите в `.env` путь к скрипту внутри контейнера.

## Вариант без сервера: GitHub Actions (бесплатно)

Бот живёт на раннерах GitHub: бесплатно для публичных репозиториев, 4 ядра и 16 ГБ RAM,
`maigret` устанавливается на лету, `blackbird` тоже влезает.

Как это работает: workflow `.github/workflows/bot.yml` запускается по расписанию каждые
6 часов и держит процесс 340 минут. Между запусками пауза 10–20 минут; сообщения не теряются,
Telegram отдаёт их при переподключении.

Настройка:

1. Создайте публичный репозиторий на GitHub и загрузите туда папку проекта.
2. Settings → Secrets and variables → Actions → New repository secret:
   `BOT_TOKEN`, `ALLOWED_USER_IDS`, `ADMIN_IDS`.
3. Вкладка Actions → workflow `osint-bot` → Run workflow.

Ограничения: отчёты и SQLite между запусками не сохраняются; через 60 дней без коммитов
GitHub отключает расписание — достаточно нажать Run workflow.
