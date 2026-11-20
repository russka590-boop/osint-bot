from __future__ import annotations

from bot.config import settings
from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

API = "https://api.vk.com/method"
VERSION = "5.199"
MAX_SUBSCRIPTIONS = 25


def parse_vk_user(data: object) -> Finding | None:
    if not isinstance(data, list) or not data:
        return None
    user = data[0]
    if not isinstance(user, dict) or not user.get("id"):
        return None
    name = " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part)
    details = [name]
    if user.get("verified"):
        details.append("подтверждён")
    city = user.get("city")
    if isinstance(city, dict) and city.get("title"):
        details.append(f"город: {city['title']}")
    if user.get("followers_count") is not None:
        details.append(f"подписчиков: {user.get('followers_count')}")
    screen = user.get("screen_name") or f"id{user.get('id')}"
    return Finding(
        source="VK",
        status="found",
        url=f"https://vk.com/{screen}",
        details=", ".join(part for part in details if part) or None,
    )


def parse_vk_subscriptions(data: object) -> list[Finding]:
    if not isinstance(data, dict):
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    findings: list[Finding] = []
    for item in items[:MAX_SUBSCRIPTIONS]:
        if not isinstance(item, dict):
            continue
        title = item.get("name") or item.get("screen_name")
        if not title:
            continue
        url = None
        if item.get("screen_name"):
            url = f"https://vk.com/{item['screen_name']}"
        elif item.get("id"):
            url = f"https://vk.com/public{item['id']}"
        findings.append(
            Finding(source="VK подписки", status="found", url=url, details=str(title)[:80])
        )
    return findings


class VKPlugin(OSINTPlugin):
    name = "vk"
    title = "VK — профиль и подписки по нику"
    description = "Официальный API VK: профиль по screen_name и публичные подписки."
    input_types = (TargetKind.USERNAME,)
    default_timeout = 45

    async def ready(self) -> tuple[bool, str]:
        if not settings.vk_token:
            return False, "нужен VK_TOKEN: dev.vk.com → приложение → access token, затем добавить в секреты"
        return True, ""

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        token = settings.vk_token

        status, data, error = await net.get_json_status(
            f"{API}/users.get?user_ids={target}"
            "&fields=screen_name,city,verified,followers_count,counters,site"
            f"&access_token={token}&v={VERSION}",
            timeout=20,
        )
        if status != 200:
            result.ok = False
            result.errors.append(error or f"HTTP {status}")
            return result
        if isinstance(data, dict) and data.get("error"):
            api_error = data["error"]
            result.ok = False
            result.errors.append(
                f"VK API: {api_error.get('error_msg')} (код {api_error.get('error_code')})"
            )
            return result

        users = data.get("response") if isinstance(data, dict) else None
        finding = parse_vk_user(users)
        if finding is None:
            result.findings.append(
                Finding(source="VK", status="not_found", details="профиль по этому нику не найден")
            )
            return result

        result.findings.append(finding)
        user_id = users[0].get("id") if isinstance(users, list) and users else None
        if user_id:
            sub_status, sub_data, _ = await net.get_json_status(
                f"{API}/users.getSubscriptions?user_id={user_id}&extended=1"
                f"&count={MAX_SUBSCRIPTIONS}&access_token={token}&v={VERSION}",
                timeout=20,
            )
            if sub_status == 200 and isinstance(sub_data, dict) and not sub_data.get("error"):
                subscriptions = parse_vk_subscriptions(sub_data.get("response"))
                result.findings.extend(subscriptions)
                if not subscriptions:
                    result.errors.append("подписки недоступны: профиль закрыт или скрыт")
        return result


register(VKPlugin())
