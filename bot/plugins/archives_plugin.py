from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import quote, urlparse

from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

MEMENTO_RE = re.compile(r'<([^>]+)>;\s*rel="([^"]+)"(?:;\s*datetime="([^"]*)")?')
CC_CACHE: dict[str, object] = {"ts": 0.0, "index": None}
CC_TTL = 12 * 3600


def _fmt_ts(timestamp: str) -> str:
    digits = "".join(ch for ch in timestamp if ch.isdigit())
    if len(digits) >= 14:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}"
    if len(digits) >= 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return timestamp or "—"


def parse_cdx(payload: object) -> list[Finding]:
    if not payload:
        return []
    rows = payload
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except json.JSONDecodeError:
            return []
    if not isinstance(rows, list) or len(rows) < 2:
        return []
    header = [str(item) for item in rows[0]]
    findings: list[Finding] = []
    for row in rows[1:]:
        record = dict(zip(header, row))
        original = str(record.get("original") or "").strip()
        timestamp = str(record.get("timestamp") or "").strip()
        status = str(record.get("statuscode") or "").strip()
        if not original:
            continue
        findings.append(
            Finding(
                source="Wayback Machine",
                status="found",
                url=f"https://web.archive.org/web/{timestamp}/{original}",
                details=f"{_fmt_ts(timestamp)} · HTTP {status or '—'}",
            )
        )
    return findings


def parse_memento(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for match in MEMENTO_RE.finditer(text or ""):
        url, rel, datetime = match.group(1), match.group(2), match.group(3) or ""
        if rel not in ("memento", "first memento"):
            continue
        if url in seen:
            continue
        seen.add(url)
        host = urlparse(url).netloc.lower()
        findings.append(
            Finding(
                source=f"Архив: {host}",
                status="found",
                url=url,
                details=_fmt_ts(datetime) if datetime else None,
            )
        )
    return findings


def parse_commoncrawl(text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = str(record.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        findings.append(
            Finding(
                source="Common Crawl",
                status="found",
                url=url,
                details=f"{_fmt_ts(str(record.get('timestamp', '')))} · HTTP {record.get('status', '—')}",
            )
        )
    return findings


async def _cc_index() -> str | None:
    now = time.time()
    cached = CC_CACHE.get("index")
    if cached and now - float(CC_CACHE.get("ts") or 0) < CC_TTL:
        return str(cached)
    data, error = await net.get_json("https://index.commoncrawl.org/collinfo.json", timeout=20)
    if error or not isinstance(data, list) or not data:
        return None
    index = str(data[0].get("id") or "")
    if index:
        CC_CACHE.update({"ts": now, "index": index})
        return index
    return None


class ArchivesPlugin(OSINTPlugin):
    name = "archives"
    title = "Веб-архивы (Wayback, archive.today, Memento, Common Crawl)"
    description = "Ищет сохранённые копии страницы в крупнейших веб-архивах."
    input_types = (TargetKind.URL, TargetKind.DOMAIN)
    default_timeout = 90

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        base = target if target.startswith("http") else f"https://{target}"
        encoded = quote(base, safe="")

        wayback, archive_today, memento, commoncrawl = await asyncio.gather(
            self._wayback(base, encoded),
            self._archive_today(base),
            self._memento(base),
            self._commoncrawl(encoded),
        )

        for part, source_name in (
            (wayback, "Wayback"),
            (archive_today, "archive.today"),
            (memento, "Memento"),
            (commoncrawl, "Common Crawl"),
        ):
            findings, error = part
            result.findings.extend(findings)
            if error:
                result.errors.append(f"{source_name}: {error}")

        if not result.findings and not result.errors:
            result.errors.append("в архивах ничего не найдено")
        if not result.findings and result.errors and all(
            "ничего не найдено" in item for item in result.errors
        ):
            result.ok = True
        return result

    async def _wayback(self, base: str, encoded: str) -> tuple[list[Finding], str]:
        data, error = await net.get_json(
            "https://web.archive.org/cdx/search/cdx"
            f"?url={encoded}&output=json&limit=-25&fl=timestamp,original,statuscode"
            "&collapse=urlkey&filter=statuscode:200",
            timeout=30,
        )
        if error:
            return [], f"CDX недоступен ({error})"
        findings = parse_cdx(data)
        if findings:
            return findings[:10], ""
        data, error = await net.get_json(
            f"https://archive.org/wayback/available?url={encoded}", timeout=20
        )
        if error or not isinstance(data, dict):
            return [], "" if not error else f"availability API: {error}"
        closest = (data.get("archived_snapshots") or {}).get("closest") or {}
        url = closest.get("url")
        if url:
            return [
                Finding(
                    source="Wayback Machine",
                    status="found",
                    url=str(url),
                    details=_fmt_ts(str(closest.get("timestamp", ""))),
                )
            ], ""
        return [], ""

    async def _archive_today(self, base: str) -> tuple[list[Finding], str]:
        status, location, error = await net.head_status(
            f"https://archive.ph/newest/{base}", timeout=20
        )
        if error:
            return [], error
        if status in (301, 302, 303, 307, 308) and location:
            url = location if location.startswith("http") else f"https://archive.ph{location}"
            return [Finding(source="archive.today", status="found", url=url)], ""
        if status == 200:
            return [Finding(source="archive.today", status="found", url=f"https://archive.ph/newest/{base}")], ""
        if status == 404:
            return [], ""
        return [], f"HTTP {status}"

    async def _memento(self, base: str) -> tuple[list[Finding], str]:
        text, error = await net.get_text(
            f"https://timetravel.mementoweb.org/timemap/link/{base}", timeout=25
        )
        if error:
            return [], f"агрегатор недоступен ({error})"
        return parse_memento(text)[:10], ""

    async def _commoncrawl(self, encoded: str) -> tuple[list[Finding], str]:
        index = await _cc_index()
        if not index:
            return [], "индекс недоступен"
        text, error = await net.get_text(
            f"https://index.commoncrawl.org/{index}?url={encoded}&output=json&limit=5", timeout=30
        )
        if error:
            return [], error
        return parse_commoncrawl(text), ""


register(ArchivesPlugin())
