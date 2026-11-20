from __future__ import annotations

import importlib
import pkgutil

from bot.core.plugin import REGISTRY, OSINTPlugin


def load_plugins() -> dict[str, OSINTPlugin]:
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")
    return dict(REGISTRY)


__all__ = ["load_plugins", "REGISTRY"]
