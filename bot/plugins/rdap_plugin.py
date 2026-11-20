from __future__ import annotations

import ipaddress

from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register


def _event(data: dict, action: str) -> str:
    for event in data.get("events") or []:
        if isinstance(event, dict) and event.get("eventAction") == action:
            return str(event.get("eventDate") or "")[:10]
    return ""


def _registrar(data: dict) -> str:
    for entity in data.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if "registrar" not in (entity.get("roles") or []):
            continue
        vcard = entity.get("vcardArray")
        if isinstance(vcard, list) and len(vcard) > 1 and isinstance(vcard[1], list):
            for item in vcard[1]:
                if isinstance(item, list) and item and item[0] == "fn" and len(item) > 3:
                    return str(item[3])
    return ""


def parse_rdap_domain(data: object) -> Finding | None:
    if not isinstance(data, dict):
        return None
    name = data.get("ldhName") or data.get("unicodeName")
    if not name:
        return None
    parts = []
    registrar = _registrar(data)
    if registrar:
        parts.append(f"регистратор: {registrar}")
    created = _event(data, "registration")
    if created:
        parts.append(f"создан: {created}")
    expires = _event(data, "expiration")
    if expires:
        parts.append(f"истекает: {expires}")
    statuses = data.get("status") or []
    if statuses:
        parts.append("статусы: " + ", ".join(str(item) for item in statuses[:4]))
    return Finding(
        source="RDAP",
        status="found",
        url=f"https://rdap.org/domain/{str(name).lower()}",
        details="; ".join(parts) or None,
    )


def parse_rdap_ip(data: object) -> Finding | None:
    if not isinstance(data, dict):
        return None
    handle = data.get("handle") or data.get("startAddress")
    if not handle:
        return None
    parts = []
    if data.get("name"):
        parts.append(f"сеть: {data.get('name')}")
    if data.get("country"):
        parts.append(f"страна: {data.get('country')}")
    if data.get("startAddress") and data.get("endAddress"):
        parts.append(f"диапазон: {data.get('startAddress')} — {data.get('endAddress')}")
    return Finding(
        source="RDAP",
        status="found",
        url=f"https://rdap.org/ip/{handle}",
        details="; ".join(parts) or None,
    )


class RDAPPlugin(OSINTPlugin):
    name = "rdap"
    title = "RDAP — регистратор домена и сеть по IP"
    description = "Открытый протокол RDAP: кто регистратор, даты регистрации, диапазон адресов."
    input_types = (TargetKind.DOMAIN, TargetKind.IP)
    default_timeout = 35

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        is_ip = False
        try:
            ipaddress.ip_address(target)
            is_ip = True
        except ValueError:
            is_ip = False

        url = f"https://rdap.org/ip/{target}" if is_ip else f"https://rdap.org/domain/{target}"
        status, data, error = await net.get_json_status(url, timeout=25)
        if status == 0:
            result.ok = False
            result.errors.append(f"RDAP недоступен: {error}")
            return result
        if status == 404:
            result.findings.append(
                Finding(source="RDAP", status="not_found", details="объект не найден в RDAP")
            )
            return result
        if status != 200:
            result.ok = False
            result.errors.append(f"RDAP: {error or f'HTTP {status}'}")
            return result

        finding = parse_rdap_ip(data) if is_ip else parse_rdap_domain(data)
        if finding is None:
            result.ok = False
            result.errors.append("RDAP вернул данные в неизвестном формате")
            return result
        result.findings.append(finding)
        return result


register(RDAPPlugin())
