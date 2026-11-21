from __future__ import annotations

import asyncio

from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register


def parse_github(data: object) -> Finding | None:
    if not isinstance(data, dict) or not data.get("login"):
        return None
    details = ", ".join(
        part
        for part in (
            data.get("name"),
            data.get("company"),
            f"репозиториев: {data.get('public_repos')}" if data.get("public_repos") is not None else "",
            f"подписчиков: {data.get('followers')}" if data.get("followers") is not None else "",
            f"создан: {str(data.get('created_at', ''))[:10]}" if data.get("created_at") else "",
        )
        if part
    )
    return Finding(
        source="GitHub",
        status="found",
        url=str(data.get("html_url") or ""),
        details=details or None,
    )


def parse_gitlab(data: object) -> Finding | None:
    if not isinstance(data, list) or not data:
        return None
    user = data[0]
    if not isinstance(user, dict):
        return None
    details = ", ".join(
        part
        for part in (
            user.get("name"),
            f"проектов: {user.get('projects_count')}" if user.get("projects_count") is not None else "",
            f"создан: {str(user.get('created_at', ''))[:10]}" if user.get("created_at") else "",
        )
        if part
    )
    return Finding(
        source="GitLab",
        status="found",
        url=str(user.get("web_url") or ""),
        details=details or None,
    )


def parse_reddit(data: object) -> Finding | None:
    if not isinstance(data, dict):
        return None
    payload = data.get("data")
    if not isinstance(payload, dict) or payload.get("is_suspended"):
        return None
    name = payload.get("name")
    if not name:
        return None
    details = []
    if payload.get("total_karma") is not None:
        details.append(f"карма: {payload.get('total_karma')}")
    if payload.get("created_utc"):
        import datetime

        created = datetime.datetime.fromtimestamp(float(payload["created_utc"]), datetime.timezone.utc)
        details.append(f"создан: {created:%Y-%m-%d}")
    return Finding(
        source="Reddit",
        status="found",
        url=f"https://www.reddit.com/user/{name}",
        details=", ".join(details) or None,
    )


def parse_hn(data: object) -> Finding | None:
    if not isinstance(data, dict) or not data.get("id"):
        return None
    import datetime

    details = []
    if data.get("karma") is not None:
        details.append(f"карма: {data.get('karma')}")
    if data.get("created"):
        created = datetime.datetime.fromtimestamp(float(data["created"]), datetime.timezone.utc)
        details.append(f"создан: {created:%Y-%m-%d}")
    return Finding(
        source="Hacker News",
        status="found",
        url=f"https://news.ycombinator.com/user?id={data['id']}",
        details=", ".join(details) or None,
    )


def parse_keybase(data: object) -> Finding | None:
    if not isinstance(data, dict):
        return None
    them = data.get("them")
    if not isinstance(them, list) or not them:
        return None
    user = them[0]
    if not isinstance(user, dict):
        return None
    profile = user.get("profile") or {}
    details = ", ".join(
        part
        for part in (
            profile.get("full_name"),
            profile.get("location"),
            f"подтверждений: {user.get('proofs_summary', {}).get('all')}"
            if isinstance(user.get("proofs_summary"), dict)
            else "",
        )
        if part
    )
    return Finding(
        source="Keybase",
        status="found",
        url=f"https://keybase.io/{user.get('username', '')}",
        details=details or None,
    )


SOURCES = (
    ("GitHub", "https://api.github.com/users/{target}", parse_github),
    ("GitLab", "https://gitlab.com/api/v4/users?username={target}", parse_gitlab),
    ("Reddit", "https://www.reddit.com/user/{target}/about.json", parse_reddit),
    ("Hacker News", "https://hacker-news.firebaseio.com/v0/user/{target}.json", parse_hn),
    (
        "Keybase",
        "https://keybase.io/_/api/1.0/user/lookup.json?username={target}",
        parse_keybase,
    ),
)


class ProfilesPlugin(OSINTPlugin):
    name = "profiles"
    title = "Профили по нику (GitHub, GitLab, Reddit, HN, Keybase)"
    description = "Проверяет ник через открытые API площадок."
    input_types = (TargetKind.USERNAME,)
    default_timeout = 45

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)

        async def check(name: str, template: str, parser) -> tuple[list[Finding], str]:
            status, data, error = await net.get_json_status(
                template.format(target=target), timeout=15
            )
            if status == 404:
                return [], ""
            if status == 403:
                return [], f"{name}: 403 — площадка блокирует серверные IP"
            if status == 0:
                return [], f"{name}: {error}"
            if status != 200:
                return [], f"{name}: {error}"
            finding = parser(data)
            return ([finding] if finding else []), ""

        outcomes = await asyncio.gather(*(check(*source) for source in SOURCES))
        for findings, error in outcomes:
            result.findings.extend(findings)
            if error:
                result.errors.append(error)

        if not result.findings and not result.errors:
            result.errors.append("профили не найдены")
        return result


register(ProfilesPlugin())
