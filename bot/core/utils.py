from __future__ import annotations

import re
import unicodedata

from bot.core.plugin import TargetKind

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{3,255}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _clean(raw: str) -> str:
    value = unicodedata.normalize("NFKC", raw or "").strip()
    return value.strip("`'\"<>()[] ")


def to_username(raw: str) -> tuple[bool, str, str]:
    value = _clean(raw)
    if "://" in value:
        value = value.rstrip("/").rsplit("/", 1)[-1]
    value = value.lstrip("@")
    value = value.split("?", 1)[0]
    if not USERNAME_RE.match(value):
        return False, value, "username: только буквы, цифры, точка, дефис, подчёркивание (до 64 символов)"
    return True, value, ""


def to_email(raw: str) -> tuple[bool, str, str]:
    value = _clean(raw).lower()
    if not EMAIL_RE.match(value):
        return False, value, "email: формат name@example.com"
    return True, value, ""


def to_domain(raw: str) -> tuple[bool, str, str]:
    value = _clean(raw).lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].split("@")[-1].split(":", 1)[0]
    if value.startswith("www."):
        value = value[4:]
    if not DOMAIN_RE.match(value):
        return False, value, "домен: формат example.com"
    return True, value, ""


def to_url(raw: str) -> tuple[bool, str, str]:
    value = _clean(raw)
    if not value:
        return False, value, "url: пустая строка"
    if "://" not in value:
        value = f"https://{value}"
    if not URL_RE.match(value):
        return False, value, "url: формат https://example.com/page"
    return True, value, ""


_NORMALIZERS = {
    TargetKind.USERNAME: to_username,
    TargetKind.EMAIL: to_email,
    TargetKind.DOMAIN: to_domain,
    TargetKind.URL: to_url,
}


def normalize(kind: TargetKind, raw: str) -> tuple[bool, str, str]:
    return _NORMALIZERS[kind](raw)


def detect_kind(raw: str) -> TargetKind:
    value = _clean(raw)
    if value.startswith(("http://", "https://")):
        return TargetKind.URL
    if "@" in value and "." in value.split("@", 1)[-1]:
        return TargetKind.EMAIL
    if DOMAIN_RE.match(value.lower().split("/", 1)[0]):
        return TargetKind.DOMAIN
    return TargetKind.USERNAME


def chunk(text: str, size: int = 3800) -> list[str]:
    if len(text) <= size:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.splitlines(keepends=True):
        while len(line) > size:
            parts.append(line[:size])
            line = line[size:]
        if length + len(line) > size:
            parts.append("".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line)
    if current:
        parts.append("".join(current))
    return parts


def human_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} с"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes} мин {rest} с"


def safe_filename(value: str, limit: int = 40) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return (cleaned or "target")[:limit]
