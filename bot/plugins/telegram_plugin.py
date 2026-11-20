from __future__ import annotations

import html
import re

from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

PAGE_TITLE_RE = re.compile(r'<div class="tgme_page_title"[^>]*>(.*?)</div>', re.S)
OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="([^"]*)"', re.I)
OG_DESC_RE = re.compile(r'<meta\s+property="og:description"\s+content="([^"]*)"', re.I)
EXTRA_RE = re.compile(r'<div class="tgme_page_extra">(.*?)</div>', re.S)


def _text(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", raw or "")).strip()


def parse_telegram(username: str, page: str) -> Finding | None:
    title_match = PAGE_TITLE_RE.search(page) or OG_TITLE_RE.search(page)
    title = _text(title_match.group(1)) if title_match else ""
    desc_match = OG_DESC_RE.search(page)
    desc = _text(desc_match.group(1)) if desc_match else ""
    extra_match = EXTRA_RE.search(page)
    extra = _text(extra_match.group(1)) if extra_match else ""

    if not title or title.lower().startswith("telegram: contact"):
        return Finding(
            source="Telegram",
            status="not_found",
            url=f"https://t.me/{username}",
            details="профиль не отображается: ник, скорее всего, свободен",
        )
    details = " · ".join(part for part in (extra, desc[:140]) if part)
    return Finding(
        source="Telegram",
        status="found",
        url=f"https://t.me/{username}",
        details=details or title,
    )


class TelegramPlugin(OSINTPlugin):
    name = "telegram"
    title = "Telegram — публичная страница по нику"
    description = "Проверяет, занят ли ник, и показывает, что отдаёт t.me (канал, группа или профиль)."
    input_types = (TargetKind.USERNAME,)
    default_timeout = 30

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        status, page, error = await net.get_text_status(f"https://t.me/{target}", timeout=20)
        if status == 0:
            result.ok = False
            result.errors.append(f"t.me недоступен: {error}")
            return result
        if status == 404:
            result.findings.append(
                Finding(
                    source="Telegram",
                    status="not_found",
                    url=f"https://t.me/{target}",
                    details="ник свободен (HTTP 404)",
                )
            )
            return result
        if status != 200:
            result.ok = False
            result.errors.append(f"t.me ответил HTTP {status}")
            return result
        finding = parse_telegram(target, page)
        if finding is not None:
            result.findings.append(finding)
        return result


register(TelegramPlugin())
