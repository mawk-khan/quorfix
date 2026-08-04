"""Generic extension-point registries used to keep Professional modules optional.

Community code depends only on these registries, never on Professional
modules directly. A Professional app registers its providers here, typically
from its AppConfig.ready(). Community code must treat an unregistered key as
"capability not available" rather than raising, so Community stays fully
functional when Professional apps are absent or disabled.
"""

from __future__ import annotations

from typing import Any


class Registry:
    def __init__(self, name: str) -> None:
        self._name = name
        self._providers: dict[str, Any] = {}

    def register(self, key: str, provider: Any) -> None:
        if key in self._providers:
            raise ValueError(f"{self._name}: a provider is already registered for '{key}'")
        self._providers[key] = provider

    def unregister(self, key: str) -> None:
        self._providers.pop(key, None)

    def get(self, key: str) -> Any | None:
        return self._providers.get(key)

    def is_registered(self, key: str) -> bool:
        return key in self._providers

    def keys(self) -> list[str]:
        return list(self._providers)


capability_registry = Registry("capability_registry")
workflow_registry = Registry("workflow_registry")
analytics_registry = Registry("analytics_registry")
integration_registry = Registry("integration_registry")
automation_registry = Registry("automation_registry")
