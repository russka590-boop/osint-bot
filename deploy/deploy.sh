#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)" -lt 2048 ] && ! swapon --show | grep -q .; then
    echo "Мало RAM, создаю swap 2G..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

if [ ! -f .env ]; then
    echo "Ошибка: нет .env. Скопируйте .env.example и впишите BOT_TOKEN." >&2
    exit 1
fi

if ! grep -q '^BOT_TOKEN=[0-9]\{5,\}:' .env; then
    echo "Ошибка: BOT_TOKEN в .env не заполнен или не похож на токен." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker не найден, ставлю..."
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl enable --now docker
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    echo "Ставлю compose..."
    sudo apt-get install -y docker-compose-v2 || sudo apt-get install -y docker-compose
    COMPOSE="docker compose"
fi

sudo $COMPOSE up -d --build
sudo $COMPOSE ps
echo
echo "Готово. Смотрите лог: sudo $COMPOSE logs -f"
