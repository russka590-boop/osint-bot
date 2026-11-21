from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bot.config import settings
from bot.core.cli import find_binary, run_cli, split_command
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

URL_RE = re.compile(r"https?://[^\s'\"<>]+")


def _source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or url


def parse_blackbird_json(data: object) -> list[Finding]:
    if not isinstance(data, list):
        return []
    findings: list[Finding] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        name = str(item.get("name") or _source_from_url(url))
        category = str(item.get("category") or "")
        findings.append(
            Finding(
                source=name,
                status="found",
                url=url,
                details=category or None,
            )
        )
    return findings


def parse_blackbird_text(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        for url in URL_RE.findall(line):
            url = url.rstrip(".,;)")
            if url in seen:
                continue
            seen.add(url)
            findings.append(Finding(source=_source_from_url(url), status="found", url=url))
    return findings


def _repo_root(cmd: list[str]) -> Path | None:
    for token in cmd:
        if token.lower().endswith(".py"):
            path = Path(token)
            if path.exists():
                return path.parent
    return None


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
                "не настроен: клонируйте p1ngul1n0/blackbird и задайте "
                "BLACKBIRD_CMD=python /path/to/blackbird/blackbird.py"
            )
        parts = split_command(settings.blackbird_cmd)
        if not parts or find_binary(parts[0]) is None:
            return False, f"команда не найдена: {settings.blackbird_cmd}"
        root = _repo_root(parts)
        if root is not None and not (root / "blackbird.py").exists():
            return False, f"в {root} нет blackbird.py"
        return True, ""

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        base = split_command(settings.blackbird_cmd)
        is_email = "@" in target
        cmd = base + (["--email", target] if is_email else ["--username", target])
        cmd += ["--json", "--no-nsfw", "--timeout", "15"]
        cmd += split_command(settings.blackbird_args)

        root = _repo_root(base)
        stdout = ""
        stderr = ""
        payload = ""
        try:
            code, stdout, stderr = await run_cli(
                cmd,
                timeout=max(60, self.default_timeout - 30),
                cwd=str(root) if root else None,
            )
        except asyncio.TimeoutError:
            result.ok = False
            result.errors.append(f"BlackBird не уложился в {self.default_timeout} с")
            return result
        except FileNotFoundError:
            result.ok = False
            result.errors.append("команда BlackBird не найдена")
            return result

        if root is not None:
            reports = sorted(
                (root / "results").glob("*/*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if reports:
                try:
                    data = json.loads(reports[0].read_text(encoding="utf-8", errors="replace"))
                    result.findings = parse_blackbird_json(data)
                except json.JSONDecodeError:
                    result.findings = []

        if not result.findings:
            result.findings = parse_blackbird_text("\n".join((stdout, stderr)))

        output = f"{stdout}\n{stderr}".lower()
        empty = "no accounts were found" in output
        if not result.findings and not empty:
            result.ok = False
            tail = (stderr or stdout).strip().splitlines()[-2:]
            result.errors.append(
                "BlackBird не вернул распознанных результатов"
                + (f": {' / '.join(tail)}" if tail else "")
            )
        elif code != 0 and not result.findings:
            result.errors.append(f"BlackBird завершился с кодом {code}, находок нет")
        return result


register(BlackbirdPlugin())
