from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.core.plugin import Finding, PluginResult, TargetKind  # noqa: E402
from bot.core.report import build_markdown, summary_text  # noqa: E402
from bot.core.utils import chunk, detect_kind, normalize  # noqa: E402
from bot.plugins.archives_plugin import (  # noqa: E402
    parse_cdx,
    parse_commoncrawl,
    parse_memento,
)
from bot.plugins.blackbird_plugin import parse_blackbird  # noqa: E402
from bot.plugins.domains_plugin import parse_crtsh  # noqa: E402
from bot.plugins.maigret_plugin import parse_maigret  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(condition), detail))


def main() -> int:
    ok, value, _ = normalize(TargetKind.USERNAME, "https://github.com/octocat/")
    check("username из URL", ok and value == "octocat", value)

    ok, value, _ = normalize(TargetKind.USERNAME, "@octo_cat")
    check("username с @", ok and value == "octo_cat", value)

    ok, value, _ = normalize(TargetKind.EMAIL, "  User@Example.COM ")
    check("email нормализация", ok and value == "user@example.com", value)

    ok, value, _ = normalize(TargetKind.DOMAIN, "https://www.Example.com/path?x=1")
    check("домен из URL", ok and value == "example.com", value)

    ok, value, _ = normalize(TargetKind.URL, "example.com/page")
    check("url без схемы", ok and value == "https://example.com/page", value)

    ok, _, _ = normalize(TargetKind.USERNAME, "плохой ник!")
    check("отказ на неверном username", not ok)

    check("detect email", detect_kind("a@b.ru") is TargetKind.EMAIL)
    check("detect url", detect_kind("https://x.dev") is TargetKind.URL)
    check("detect domain", detect_kind("sub.example.com") is TargetKind.DOMAIN)
    check("detect username", detect_kind("just_nick") is TargetKind.USERNAME)

    parts = chunk("a" * 50 + "\n" + "b" * 50, size=60)
    check("chunk режет длинный текст", len(parts) >= 2 and all(len(p) <= 60 for p in parts))

    maigret_sample = "\n".join(
        [
            '{"sitename": "GitHub", "url_user": "https://github.com/octocat", "status": {"status": "Claimed"}}',
            '{"sitename": "Reddit", "url_user": null, "status": {"status": "Available"}}',
            "not a json line",
        ]
    )
    findings = parse_maigret(maigret_sample)
    check("maigret: found", any(f.source == "GitHub" and f.status == "found" for f in findings))
    check("maigret: not_found", any(f.source == "Reddit" and f.status == "not_found" for f in findings))

    blackbird_sample = "\n".join(
        [
            "[+] GitHub: https://github.com/octocat",
            "site,url,status",
            "Reddit,https://reddit.com/user/octocat,Found",
            "[*] Email: test@example.com",
        ]
    )
    bb = parse_blackbird(blackbird_sample)
    check("blackbird: url", any(f.url == "https://github.com/octocat" for f in bb))
    check("blackbird: csv", any(f.source == "Reddit" for f in bb))

    cdx = [["timestamp", "original", "statuscode"], ["20200101120000", "example.com", "200"]]
    cdx_findings = parse_cdx(cdx)
    check(
        "cdx",
        len(cdx_findings) == 1
        and cdx_findings[0].url == "https://web.archive.org/web/20200101120000/example.com",
        str(cdx_findings),
    )

    memento = (
        '<https://web.archive.org/web/2020/http://example.com>; rel="memento"; '
        'datetime="2020-01-01T12:00:00Z"'
    )
    check("memento", len(parse_memento(memento)) == 1)

    cc = '{"url": "http://example.com", "timestamp": "20200101120000", "status": "200"}'
    check("commoncrawl", len(parse_commoncrawl(cc)) == 1)

    crt = '[{"name_value": "www.example.com\\nexample.com", "issuer_name": "CA", "not_before": "2024-01-01T00:00:00"}]'
    check("crt.sh", len(parse_crtsh(crt)) == 2)

    results = [
        PluginResult(
            plugin="demo",
            title="Demo",
            target="example.com",
            findings=[
                Finding(source="src", status="found", url="https://example.com", details="ok"),
                Finding(source="src2", status="not_found"),
            ],
            elapsed=1.2,
        )
    ]
    markdown = build_markdown(TargetKind.DOMAIN, "example.com", results, datetime.now(timezone.utc), 1.5)
    check("report: markdown", "# OSINT-отчёт" in markdown and "Demo" in markdown)
    check("report: summary", "найдено 1 из 2" in summary_text(results))

    failed = [item for item in CHECKS if not item[1]]
    for name, passed, detail in CHECKS:
        status = "OK  " if passed else "FAIL"
        suffix = f" ({detail})" if detail and not passed else ""
        print(f"{status} {name}{suffix}")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} проверок пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
