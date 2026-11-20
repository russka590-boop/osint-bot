from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def _ids(name: str) -> frozenset[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return frozenset()
    out: set[int] = set()
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser() if raw else default


@dataclass(frozen=True)
class Settings:
    token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", "").strip())
    admin_ids: frozenset[int] = field(default_factory=lambda: _ids("ADMIN_IDS"))
    allowed_ids: frozenset[int] = field(default_factory=lambda: _ids("ALLOWED_USER_IDS"))
    max_concurrent_jobs: int = field(default_factory=lambda: _int("MAX_CONCURRENT_JOBS", 4))
    user_cooldown: int = field(default_factory=lambda: _int("USER_COOLDOWN_SEC", 30))
    max_targets_per_scan: int = field(default_factory=lambda: _int("MAX_PLUGINS_PER_SCAN", 6))

    maigret_cmd: str = field(default_factory=lambda: os.getenv("MAIGRET_CMD", "maigret").strip())
    maigret_args: str = field(
        default_factory=lambda: os.getenv("MAIGRET_ARGS", "-a").strip()
    )
    maigret_timeout: int = field(default_factory=lambda: _int("MAIGRET_TIMEOUT", 900))
    blackbird_cmd: str = field(default_factory=lambda: os.getenv("BLACKBIRD_CMD", "").strip())
    blackbird_args: str = field(default_factory=lambda: os.getenv("BLACKBIRD_ARGS", "").strip())
    blackbird_timeout: int = field(default_factory=lambda: _int("BLACKBIRD_TIMEOUT", 180))

    report_dir: Path = field(default_factory=lambda: _path("REPORT_DIR", BASE_DIR / "data" / "reports"))
    db_path: Path = field(default_factory=lambda: _path("DB_PATH", BASE_DIR / "data" / "bot.sqlite3"))

    def ensure_dirs(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


settings = Settings()
