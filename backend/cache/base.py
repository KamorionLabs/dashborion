"""
Cache interfaces for Dashborion backend.
"""

from typing import Any, Iterable, Optional, Protocol


class CacheBackend(Protocol):
    def get(self, pk: str, sk: str) -> Optional[Any]:
        ...

    def set(self, pk: str, sk: str, value: Any, ttl_seconds: int, tags: Optional[Iterable[str]] = None) -> None:
        ...

    def invalidate_prefix(self, pk: str, sk_prefix: str) -> int:
        ...
