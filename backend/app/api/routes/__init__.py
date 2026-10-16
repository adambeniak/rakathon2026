"""Feature routers, auto-discovered: add `app/api/routes/<feature>.py` exposing `router: APIRouter`.

No central list to edit (fewer merge conflicts). Routers are included in module-name order under `/api`.
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import APIRouter


def discover_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []
    for module_info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        router = getattr(module, "router", None)
        if not isinstance(router, APIRouter):
            raise RuntimeError(f"{module.__name__} must expose `router: APIRouter`")
        routers.append(router)
    return routers
