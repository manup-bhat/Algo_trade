"""
engine/core/registry.py — Generic plugin/provider registry.

The single extensibility mechanism used everywhere the architecture plans say
"a handful of types" — capabilities, UI panels, brokers, notification channels,
risk rules, and node types all use this one pattern so adding a new *kind* of
thing never requires editing the registry consumer.

Pattern: Plugin / Extension Point (same as VS Code extensions, pytest plugins,
Django's app registry).  A new implementation is added by:
  1. Writing one class that satisfies the registered Protocol.
  2. Calling registry.register(key, instance) once at startup.
  3. Zero edits to anything that calls registry.get().

Usage:
    capability_registry: Registry[CapabilityProvider] = Registry("capability")
    capability_registry.register("volume_sma", VolumeSmaProvider())
    capability_registry.register("option_chain", OptionChainProvider())

    provider = capability_registry.get("volume_sma")   # raises if missing
    provider = capability_registry.get_or_none("unknown")  # None if missing
    keys = capability_registry.list_keys()             # ["volume_sma", "option_chain"]
"""

from __future__ import annotations

from typing import Generic, TypeVar

import structlog

T = TypeVar("T")
log = structlog.get_logger(__name__)


class Registry(Generic[T]):
    """
    Thread-safe-by-asyncio (single event loop) generic registry.

    Keys are arbitrary strings (namespaced by convention, e.g.
    "indicator.volume_sma", "broker.zerodha").  Keys are case-sensitive.

    Duplicate registration raises ValueError — deliberate: a startup-time
    collision is always a programming error, not a runtime condition to swallow.
    """

    def __init__(self, name: str = "registry") -> None:
        """
        Args:
            name: Human-readable registry name used in log messages.
        """
        self._name = name
        self._store: dict[str, T] = {}

    # ── Write API ─────────────────────────────────────────────────────────────

    def register(self, key: str, provider: T) -> None:
        """
        Register *provider* under *key*.

        Raises:
            ValueError: If *key* is already registered.
            TypeError:  If *key* is not a non-empty string.
        """
        if not isinstance(key, str) or not key:
            raise TypeError(f"Registry key must be a non-empty string, got {key!r}")
        if key in self._store:
            raise ValueError(
                f"[{self._name}] key {key!r} is already registered "
                f"(existing={type(self._store[key]).__name__!r}). "
                "Duplicate registration is always a programming error."
            )
        self._store[key] = provider
        log.debug("registry_registered", registry=self._name, key=key, type=type(provider).__name__)

    def unregister(self, key: str) -> None:
        """
        Remove *key* from the registry.

        Safe to call even if *key* was never registered (no-op with a warning).
        Use-case: test teardown, hot-disable of a capability.
        """
        if key not in self._store:
            log.warning("registry_unregister_unknown_key", registry=self._name, key=key)
            return
        del self._store[key]
        log.debug("registry_unregistered", registry=self._name, key=key)

    # ── Read API ──────────────────────────────────────────────────────────────

    def get(self, key: str) -> T:
        """
        Return the provider registered under *key*.

        Raises:
            KeyError: If *key* is not registered (hard fail — callers should
                      always know which keys they need; a missing key is a
                      configuration/startup-ordering bug, not a runtime edge case).
        """
        try:
            return self._store[key]
        except KeyError:
            available = sorted(self._store.keys())
            raise KeyError(
                f"[{self._name}] key {key!r} not registered. "
                f"Available keys: {available}"
            ) from None

    def get_or_none(self, key: str) -> T | None:
        """
        Return the provider or None if *key* is not registered.

        Prefer this over try/except get() in code that has a meaningful fallback.
        """
        return self._store.get(key)

    def list_keys(self) -> list[str]:
        """Return a sorted snapshot of all registered keys."""
        return sorted(self._store.keys())

    def has(self, key: str) -> bool:
        """Return True if *key* is registered."""
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"Registry({self._name!r}, keys={self.list_keys()})"
