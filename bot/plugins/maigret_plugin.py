from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from bot.config import settings
from bot.core.cli import find_binary, run_cli, split_command
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

DETAIL_KEYS = ("fullname", "name", "location", "created_at", "follower_count")


def _details(status: dict) -> str | None:
    parts: list[str] = []
    identifiers = status.get("ids")
    if isinstance(identifiers, dict):
        for key in DETAIL_KEYS:
            value = identifiers.get(key)
            if value:
                text = str(value)
                if key == "created_at":
                    text = text[:10]
                parts.append(text)
    return " · ".join(parts[:4]) or None


def parse_maigret(payload: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    for raw_line in (payload or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue

        status = item.get("status")
        if isinstance(status, dict):
            site = str(status.get("site_name") or item.get("url_main") or "").strip()
            url = str(status.get("url") or item.get("url_user") or "").strip()
            state = str(status.get("status") or "").strip()
            details = _details(status)
        else:
            site = str(item.get("sitename") or item.get("site_name") or "").strip()
            url = str(item.get("url_user") or item.get("url") or "").strip()
            state = str(status or "").strip()
            details = state or None

        if not site:
            site = urlparse(url).netloc or "site"
        lowered = state.lower()
        is_found = "claimed" in lowered or "found" in lowered or "present" in lowered
        is_missing = any(word in lowered for word in ("available", "not found", "illegal", "unknown"))

        if is_found or (url and not is_missing):
            key = (site, url)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                Finding(source=site, status="found", url=url or None, details=details or state or None)
            )
        elif is_missing:
            key = (site, "not_found")
            if key in seen:
                continue
            seen.add(key)
            findings.append(Finding(source=site, status="not_found", details=state or None))

    return findings


class MaigretPlugin(OSINTPlugin):
    name = "maigret"
    title = "Maigret — ник по базе площадок"
    description = "Обёртка над CLI maigret: ищет профили по имени пользователя на тысячах сайтов."
    input_types = (TargetKind.USERNAME,)
    requires_binary = "maigret"
    default_timeout = settings.maigret_timeout

    async def ready(self) -> tuple[bool, str]:
        parts = split_command(settings.maigret_cmd)
        if not parts or find_binary(parts[0]) is None:
            return False, "не установлен: pip install maigret"
        return True, ""

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        cmd = split_command(settings.maigret_cmd) + [
            target,
            "--json",
            "ndjson",
            "--no-progressbar",
            "--no-color",
            "--timeout",
            "15",
        ]
        cmd += split_command(settings.maigret_args)
        payload = ""
        stdout = ""
        stderr = ""
        try:
            with tempfile.TemporaryDirectory() as workdir:
                code, stdout, stderr = await run_cli(
                    cmd, timeout=max(60, self.default_timeout - 30), cwd=workdir
                )
                reports = sorted(
                    Path(workdir).glob("reports/*.json"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
                if reports:
                    payload = reports[0].read_text(encoding="utf-8", errors="replace")
        except asyncio.TimeoutError:
            result.ok = False
            result.errors.append(f"maigret не уложился в {self.default_timeout} с")
            return result
        except FileNotFoundError:
            result.ok = False
            result.errors.append("команда maigret не найдена в PATH")
            return result

        result.findings = parse_maigret(payload or stdout)
        output = f"{stdout}\n{stderr}".lower()
        empty = "returned 0 accounts" in output or "no accounts" in output
        if not result.findings and not empty:
            result.ok = False
            tail = (stderr or stdout).strip().splitlines()[-2:]
            result.errors.append("maigret не вернул отчёт" + (f": {' / '.join(tail)}" if tail else ""))
        elif code != 0 and not result.findings:
            result.errors.append(f"maigret завершился с кодом {code}, находок нет")
        return result


register(MaigretPlugin())
