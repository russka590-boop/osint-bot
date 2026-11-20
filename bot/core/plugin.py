from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class TargetKind(str, Enum):
    USERNAME = "username"
    EMAIL = "email"
    DOMAIN = "domain"
    URL = "url"
    IP = "ip"
    PHONE = "phone"

    @property
    def title(self) -> str:
        return _KIND_TITLES[self]


_KIND_TITLES = {
    TargetKind.USERNAME: "Имя пользователя",
    TargetKind.EMAIL: "Email",
    TargetKind.DOMAIN: "Домен",
    TargetKind.URL: "URL",
    TargetKind.IP: "IP-адрес",
    TargetKind.PHONE: "Телефон",
}


@dataclass(slots=True)
class Finding:
    source: str
    status: str
    url: str | None = None
    details: str | None = None


@dataclass(slots=True)
class PluginResult:
    plugin: str
    title: str
    target: str
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    ok: bool = True

    @property
    def found(self) -> list[Finding]:
        return [item for item in self.findings if item.status == "found"]

    @property
    def checked(self) -> int:
        return len([item for item in self.findings if item.status in ("found", "not_found")])


class OSINTPlugin:
    name: ClassVar[str] = ""
    title: ClassVar[str] = ""
    description: ClassVar[str] = ""
    input_types: ClassVar[tuple[TargetKind, ...]] = ()
    requires_binary: ClassVar[str | None] = None
    default_timeout: ClassVar[int] = 120

    async def ready(self) -> tuple[bool, str]:
        return True, ""

    async def run(self, target: str) -> PluginResult:
        raise NotImplementedError


REGISTRY: dict[str, OSINTPlugin] = {}


def register(plugin: OSINTPlugin) -> OSINTPlugin:
    if not plugin.name:
        raise ValueError("plugin.name is required")
    if plugin.name in REGISTRY:
        raise ValueError(f"duplicate plugin name: {plugin.name}")
    REGISTRY[plugin.name] = plugin
    return plugin


def plugins_for(kind: TargetKind) -> list[OSINTPlugin]:
    return [item for item in REGISTRY.values() if kind in item.input_types]
