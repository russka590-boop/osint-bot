from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from bot.config import settings
from bot.core.cli import find_binary, run_cli, split_command
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

URL_RE = re.compile(r"https?://[^\s'\"<>]+")
CSV_HINTS = ("site", "url", "status", "found")


def _source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or url


def parse_blackbird(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()

        parts = [part.strip().strip('"') for part in line.split(",")]
        if len(parts) >= 2 and "url" not in lowered and "," in line:
            site, url_part = parts[0], parts[1]
            status = parts[2] if len(parts) > 2 else ""
            if url_part.startswith("http") and url_part not in seen:
                seen.add(url_part)
                findings.append(
                    Finding(
                        source=site or _source_from_url(url_part),
                        status="found" if "not" not in status.lower() else "not_found",
                        url=url_part,
                        details=status or None,
                    )
                )
                continue

        for url in URL_RE.findall(line):
            url = url.rstrip(".,;)")
            if url in seen:
                continue
            seen.add(url)
            findings.append(
                Finding(
                    source=_source_from_url(url),
                    status="found",
                    url=url,
                    details=None if "not found" not in lowered else "помечено как not found",
                )
            )
    return findings


class BlackbirdPlugin(OSINTPlugin):
    name = "blackbird"
    title = "BlackBird — ник и email по площадкам"
    description = "Обёртка над CLI BlackBird (p1ngul1n0/blackbird): аккаунты по username и email."
    input_types = (TargetKind.USERNAME, TargetKind.EMAIL)
    requires_binary = "blackbird"
    default_timeout = settings.blackbird_timeout

    async def ready(self) -> tuple[bool, str]:
        if not settings.blackbird_cmd:
            return False, (
                "не настроен: скачайте репозиторий p1ngul1n0/blackbird и укажите в .env "
                "BLACKBIRD_CMD=python путь/к/blackbird.py"
            )
        parts = split_command(settings.blackbird_cmd)
        if not parts or find_binary(parts[0]) is None:
            return False, f"команда не найдена: {settings.blackbird_cmd}"
        return True, ""

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        is_email = "@" in target
        cmd = split_command(settings.blackbird_cmd) + (["-e", target] if is_email else ["-u", target])
        cmd += split_command(settings.blackbird_args)
        try:
            code, stdout, stderr = await run_cli(cmd, timeout=max(30, self.default_timeout - 15))
        except asyncio.TimeoutError:
            result.ok = False
            result.errors.append(f"BlackBird не уложился в {self.default_timeout} с")
            return result
        except FileNotFoundError:
            result.ok = False
            result.errors.append("команда BlackBird не найдена")
            return result

        result.findings = parse_blackbird("\n".join((stdout, stderr)))
        if not result.findings:
            result.ok = False
            tail = (stderr or stdout).strip().splitlines()[-3:]
            result.errors.append(
                "BlackBird не вернул распознанных результатов"
                + (f": {' / '.join(tail)}" if tail else "")
            )
        elif code != 0 and not result.found:
            result.errors.append(f"BlackBird завершился с кодом {code}, находок нет")
        return result


register(BlackbirdPlugin())
