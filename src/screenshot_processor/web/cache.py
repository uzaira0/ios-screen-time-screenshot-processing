"""Simple in-memory TTL cache for expensive, rarely-changing query results.

Used by the stats and groups endpoints to avoid 6+ COUNT queries per request.
Cache is invalidated explicitly when screenshots are uploaded, annotated, or
have their status changed.

This is intentionally simple: a module-level dict + monotonic timestamp.
No Redis, no external dependencies.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default TTL in seconds, overridable via env var
_DEFAULT_TTL = 10.0


def _get_ttl() -> float:
    """Read TTL from environment, falling back to default."""
    raw = os.environ.get("STATS_CACHE_TTL_SECONDS")
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (ValueError, TypeError):
            logger.warning("Invalid STATS_CACHE_TTL_SECONDS=%r, using default %s", raw, _DEFAULT_TTL)
    return _DEFAULT_TTL


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)


class TTLCache:
    """Thread-safe, in-memory TTL cache with explicit invalidation.

    Each key stores a single value that expires after ``ttl`` seconds.
    The TTL is read once at construction from ``STATS_CACHE_TTL_SECONDS``
    (env var) or falls back to 10 seconds.

    Usage::

        cache = TTLCache()

        # Try cache first
        cached = cache.get("stats")
        if cached is not None:
            return cached

        # Compute expensive result
        result = await repo.get_stats()
        cache.set("stats", result)
        return result

        # Invalidate on mutation
        cache.invalidate("stats")
        cache.invalidate("groups")
    """

    def __init__(self, ttl: float | None = None) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._ttl = ttl if ttl is not None else _get_ttl()

    @property
    def ttl(self) -> float:
        return self._ttl

    def get(self, key: str) -> Any | None:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() >= entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any) -> None:
        """Store a value with the configured TTL."""
        now = time.monotonic()
        with self._lock:
            self._store[key] = _CacheEntry(value=value, expires_at=now + self._ttl, created_at=now)

    def invalidate(self, key: str) -> None:
        """Remove a single key from the cache."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_all(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Module-level singleton used by routes
# ---------------------------------------------------------------------------

stats_cache = TTLCache()

# Well-known cache keys
STATS_KEY = "stats"
GROUPS_KEY = "groups"


def invalidate_stats_and_groups() -> None:
    """Convenience helper — call after any mutation that affects counts."""
    stats_cache.invalidate(STATS_KEY)
    stats_cache.invalidate(GROUPS_KEY)
    logger.debug("Stats/groups cache invalidated")
