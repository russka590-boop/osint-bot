from __future__ import annotations

import asyncio
import json
import socket
from urllib.parse import quote

from bot.core import net
from bot.core.plugin import Finding, OSINTPlugin, PluginResult, TargetKind, register

MAX_SUBDOMAINS = 40


def parse_crtsh(text: str) -> list[Finding]:
    try:
        data = json.loads(text) if text.strip().startswith("[") else []
    except json.JSONDecodeError:
        return []
    findings: list[Finding] = []
    seen: set[str] = set()
    for record in data:
        if not isinstance(record, dict):
            continue
        names = str(record.get("name_value") or "").splitlines()
        issuer = str(record.get("issuer_name") or "")
        issued = str(record.get("not_before") or "")[:10]
        for name in names:
            host = name.strip().lower().lstrip("*.")
            if not host or host in seen:
                continue
            seen.add(host)
            details = " · ".join(part for part in (issued, issuer[:60]) if part)
            findings.append(
                Finding(source="crt.sh", status="found", url=f"https://{host}", details=details or None)
            )
            if len(findings) >= MAX_SUBDOMAINS:
                return findings
    return findings


async def _dns_records(domain: str) -> tuple[list[Finding], str]:
    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(
            loop.getaddrinfo(domain, None, type=socket.SOCK_STREAM), timeout=8
        )
        addresses = sorted({info[4][0] for info in infos})
    except (socket.gaierror, asyncio.TimeoutError, OSError) as exc:
        return [], f"A/AAAA: {type(exc).__name__}"

    findings = [
        Finding(source="DNS", status="found", details=f"A/AAAA: {address}") for address in addresses
    ]

    try:
        import dns.asyncresolver  # type: ignore
    except ImportError:
        return findings, ""

    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 8
    for record_type in ("MX", "NS", "TXT"):
        try:
            answer = await resolver.resolve(domain, record_type)
            for item in answer:
                findings.append(
                    Finding(source="DNS", status="found", details=f"{record_type}: {str(item)[:120]}")
                )
        except Exception:  # noqa: BLE001
            continue
    return findings, ""


class DomainsPlugin(OSINTPlugin):
    name = "domains"
    title = "Домен: DNS и сертификаты (crt.sh)"
    description = "Собирает DNS-записи и поддомены из публичных логов Certificate Transparency."
    input_types = (TargetKind.DOMAIN,)
    default_timeout = 75

    async def run(self, target: str) -> PluginResult:
        result = PluginResult(plugin=self.name, title=self.title, target=target)
        dns_findings, dns_error = await _dns_records(target)
        result.findings.extend(dns_findings)
        if dns_error:
            result.errors.append(dns_error)

        text, error = await net.get_text(
            f"https://crt.sh/?q={quote('%25.' + target)}&output=json", timeout=45
        )
        if error:
            result.errors.append(f"crt.sh: {error}")
        else:
            subdomains = parse_crtsh(text)
            result.findings.extend(subdomains)
            if not subdomains:
                result.errors.append("crt.sh: сертификатов не найдено")

        if not result.findings:
            result.ok = False
            result.errors.append("домен не разрешается и нет публичных сертификатов")
        return result


register(DomainsPlugin())
