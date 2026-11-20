from __future__ import annotations

import asyncio
import json

from bot.config import settings
from bot.core.cli import find_binary, run_cli, split_command
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

FOUND_MARKERS = ("claimed", "found", "taken", "exists", "present", "used", "registered")
MISSING_MARKERS = ("available", "not found", "free", "absent", "vacant", "unavailable")


def parse_maigret(stdout: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        site = str(item.get("sitename") or item.get("site") or item.get("site_name") or "").strip()
        if not site:
            continue
        url = item.get("url_user") or item.get("url") or item.get("url_main") or ""
        status = item.get("status", "")
        if isinstance(status, dict):
            status = status.get("status") or status.get("ids") or ""
        status_text = str(status).strip()
        lowered = status_text.lower()
        is_missing = any(marker in lowered for marker in MISSING_MARKERS)
        is_found = bool(url) or any(marker in lowered for marker in FOUND_MARKERS)
        if is_missing and not any(marker in lowered for marker in FOUND_MARKERS):
            key = (site, "not_found")
            if key not in seen:
                seen.add(key)
                findings.append(Finding(source=site, status="not_found", details=status_text or None))
        elif is_found:
            key = (site, "found")
            if key not in seen:
                seen.add(key)
                findings.append(
                    Finding(source=site, status="found", url=str(url) or None, details=status_text or None)
                )
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
        try:
            code, stdout, stderr = await run_cli(cmd, timeout=max(60, self.default_timeout - 30))
        except asyncio.TimeoutError:
            result.ok = False
            result.errors.append(f"maigret не уложился в {self.default_timeout} с")
            return result
        except FileNotFoundError:
            result.ok = False
            result.errors.append("команда maigret не найдена в PATH")
            return result

        result.findings = parse_maigret(stdout)
        if not result.findings:
            result.ok = False
            tail = (stderr or stdout).strip().splitlines()[-3:]
            result.errors.append("пустой ответ maigret" + (f": {' / '.join(tail)}" if tail else ""))
        elif code != 0 and not result.found:
            result.errors.append(f"maigret завершился с кодом {code}, находок нет")
        return result


register(MaigretPlugin())
