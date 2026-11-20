from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bot.core.plugin import PluginResult, TargetKind
from bot.core.utils import human_duration, safe_filename


def build_markdown(
    kind: TargetKind,
    target: str,
    results: list[PluginResult],
    started_at: datetime,
    elapsed: float,
) -> str:
    total_found = sum(len(item.found) for item in results)
    lines: list[str] = [
        "# OSINT-отчёт",
        "",
        f"- Цель: `{target}`",
        f"- Тип: {kind.title}",
        f"- Начало: {started_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"- Длительность: {human_duration(elapsed)}",
        f"- Модулей: {len(results)}",
        f"- Находок: {total_found}",
        "",
        "---",
        "",
    ]

    for result in results:
        lines.append(f"## {result.title}")
        lines.append("")
        status = "ok" if result.ok else "ошибка"
        lines.append(f"Модуль: `{result.plugin}` · статус: {status} · время: {result.elapsed:.1f} с")
        lines.append("")
        if result.errors:
            lines.append("Ошибки:")
            for error in result.errors:
                lines.append(f"- {error}")
            lines.append("")
        if result.findings:
            lines.append("| Источник | Статус | Ссылка | Детали |")
            lines.append("| --- | --- | --- | --- |")
            for finding in result.findings:
                url = f"[{_short(finding.url)}]({finding.url})" if finding.url else "—"
                details = (finding.details or "—").replace("|", "\\|").replace("\n", " ")
                source = finding.source.replace("|", "\\|")
                lines.append(f"| {source} | {finding.status} | {url} | {details} |")
        else:
            lines.append("Ничего не найдено.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Отчёт собран автоматически из открытых источников.")
    return "\n".join(lines)


def _short(url: str | None, limit: int = 60) -> str:
    if not url:
        return "—"
    return url if len(url) <= limit else f"{url[: limit - 1]}…"


def summary_text(results: list[PluginResult]) -> str:
    lines: list[str] = []
    for result in results:
        if not result.ok:
            reason = result.errors[0] if result.errors else "неизвестная ошибка"
            lines.append(f"— {result.title}: ошибка ({reason})")
            continue
        lines.append(
            f"— {result.title}: найдено {len(result.found)} из {result.checked}, {result.elapsed:.1f} с"
        )
    return "\n".join(lines) or "Нет данных."


def write_report(
    kind: TargetKind,
    target: str,
    markdown: str,
    report_dir: Path,
    stamp: datetime,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    name = f"{stamp.strftime('%Y%m%d-%H%M%S')}_{kind.value}_{safe_filename(target)}.md"
    path = report_dir / name
    path.write_text(markdown, encoding="utf-8")
    return path
