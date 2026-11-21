from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.core.plugin import Finding, PluginResult, TargetKind  # noqa: E402
from bot.core.report import build_markdown, summary_text  # noqa: E402
from bot.core.utils import chunk, detect_kind, normalize, to_ip, to_phone  # noqa: E402
from bot.plugins.archives_plugin import (  # noqa: E402
    parse_cdx,
    parse_commoncrawl,
    parse_memento,
)
from bot.plugins.blackbird_plugin import parse_blackbird_json, parse_blackbird_text  # noqa: E402
from bot.plugins.domains_plugin import parse_crtsh  # noqa: E402
from bot.plugins.maigret_plugin import parse_maigret  # noqa: E402
from bot.plugins.rdap_plugin import parse_rdap_domain, parse_rdap_ip  # noqa: E402
from bot.plugins.telegram_plugin import parse_telegram  # noqa: E402
from bot.plugins.vk_plugin import parse_vk_subscriptions, parse_vk_user  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(condition), detail))


async def storage_checks() -> None:
    import tempfile

    from bot.core.storage import Storage

    with tempfile.TemporaryDirectory() as tmp:
        store = Storage(Path(tmp) / "test.db")
        await store.connect()
        is_new, greeted, role = await store.register_user(1, "nick", "Имя")
        check("storage: новый пользователь", is_new and not greeted and role == "user")

        await store.set_role(1, "trusted")
        check("storage: роль", await store.get_role(1) == "trusted")

        await store.save_message(
            chat_id=1, message_id=10, user_id=1, username="nick",
            kind="text", content="привет", file_id=None,
        )
        old_content, edit_id = await store.record_edit(1, 10, "пока")
        check("storage: правка", old_content == "привет" and edit_id is not None)

        messages = await store.user_messages(1)
        check("storage: история", bool(messages) and messages[0]["content"] == "пока")

        await store.set_setting("auto_reply", "текст")
        check("storage: настройка", await store.get_setting("auto_reply") == "текст")
        check("storage: согласие по умолчанию", await store.get_consent(1) is None)
        await store.set_consent(1, "1.0")
        check("storage: согласие выдано", await store.get_consent(1) == "1.0")
        await store.clear_consent(1)
        check("storage: согласие отозвано", await store.get_consent(1) is None)
        check("storage: список пользователей", await store.all_user_ids() == [1])
        await store.close()


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
            '{"url_user": "https://github.com/octocat", "status": '
            '{"site_name": "GitHub", "url": "https://github.com/octocat", "status": "Claimed"}}',
            '{"url_user": null, "status": {"site_name": "Reddit", "status": "Available"}}',
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
    bb = parse_blackbird_text(blackbird_sample)
    check("blackbird: url", any(f.url == "https://github.com/octocat" for f in bb))
    check("blackbird: csv", len(bb) >= 2)

    bb_json = parse_blackbird_json(
        [{"name": "GitHub", "url": "https://github.com/octocat", "category": "coding", "status": "FOUND"}]
    )
    check(
        "blackbird: json",
        len(bb_json) == 1 and bb_json[0].source == "GitHub" and bb_json[0].details == "coding",
    )

    maigret_file = (
        '{"site": {"urlMain": "https://github.com/"}, "url_user": "https://github.com/octocat",'
        ' "status": {"site_name": "GitHub", "url": "https://github.com/octocat", "status": "Claimed",'
        ' "ids": {"fullname": "The Octocat", "location": "San Francisco", "created_at": "2011-01-25T18:44:36Z"}}}'
    )
    mf = parse_maigret(maigret_file)
    check(
        "maigret: ndjson-файл",
        len(mf) == 1 and mf[0].source == "GitHub" and "The Octocat" in (mf[0].details or ""),
        str(mf),
    )

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

    ok, value, _ = to_phone("8 (999) 123-45-67")
    check("phone нормализация", ok and value == "+79991234567", value)

    ok, value, _ = to_ip(" 8.8.8.8 ")
    check("ip нормализация", ok and value == "8.8.8.8", value)

    tg_page = (
        '<div class="tgme_page_title"><span dir="auto">Pavel Durov</span></div>'
        '<div class="tgme_page_extra">12 345 subscribers</div>'
    )
    tg = parse_telegram("durov", tg_page)
    check("telegram: профиль", tg is not None and tg.status == "found" and "12 345" in (tg.details or ""))

    tg_free = parse_telegram(
        "free_nick",
        '<div class="tgme_page_title"><span dir="auto">Telegram: Contact @free_nick</span></div>',
    )
    check("telegram: свободный ник", tg_free is not None and tg_free.status == "not_found")

    vk_user = parse_vk_user(
        [
            {
                "id": 1,
                "first_name": "Pavel",
                "last_name": "Durov",
                "screen_name": "durov",
                "followers_count": 100,
                "verified": 1,
                "city": {"title": "Санкт-Петербург"},
            }
        ]
    )
    check("vk: профиль", vk_user is not None and vk_user.url == "https://vk.com/durov", str(vk_user))

    vk_subs = parse_vk_subscriptions({"items": [{"name": "Канал", "screen_name": "chan"}]})
    check("vk: подписки", len(vk_subs) == 1 and vk_subs[0].url == "https://vk.com/chan")

    rdap_domain = parse_rdap_domain(
        {
            "ldhName": "EXAMPLE.COM",
            "status": ["active"],
            "events": [{"eventAction": "registration", "eventDate": "1997-09-15T04:00:00Z"}],
            "entities": [
                {
                    "roles": ["registrar"],
                    "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "REG LLC"]]],
                }
            ],
        }
    )
    check(
        "rdap: домен",
        rdap_domain is not None
        and "REG LLC" in (rdap_domain.details or "")
        and "1997-09-15" in (rdap_domain.details or ""),
        str(rdap_domain),
    )

    rdap_ip = parse_rdap_ip(
        {
            "handle": "8.8.8.0 - 8.8.8.255",
            "name": "GOGL",
            "country": "US",
            "startAddress": "8.8.8.0",
            "endAddress": "8.8.8.255",
        }
    )
    check("rdap: ip", rdap_ip is not None and "US" in (rdap_ip.details or ""), str(rdap_ip))

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

    asyncio.run(storage_checks())

    failed = [item for item in CHECKS if not item[1]]
    for name, passed, detail in CHECKS:
        status = "OK  " if passed else "FAIL"
        suffix = f" ({detail})" if detail and not passed else ""
        print(f"{status} {name}{suffix}")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} проверок пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
