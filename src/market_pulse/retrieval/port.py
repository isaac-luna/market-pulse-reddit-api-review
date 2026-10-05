"""Review snapshot of Market Pulse's source boundary."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol

from ..domain.enums import StopReason
from ..lifecycle.cancellation import CancelToken


@dataclass(frozen=True)
class NormalizedPost:
    external_id: str
    permalink: str | None
    published_at: datetime
    community: str
    author_username: str | None
    title: str | None
    body: str | None
    engagement: dict
    available: bool
    kind: str = "post"


@dataclass
class RetrievalRequest:
    topic: str
    period_start: datetime
    period_end: datetime
    deadline: datetime
    max_calls: int
    cancel: CancelToken
    search_sort: str = "relevance"


@dataclass
class RetrievalReport:
    executed: bool
    stop_reason: StopReason | None
    errors: list[dict] = field(default_factory=list)
    calls_made: int = 0
    posts_per_day: list[int] = field(default_factory=lambda: [0] * 30)
    total_reported: int | None = None
    search_parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["stop_reason"] = self.stop_reason.value if self.stop_reason else None
        return data


class SourceAdapter(Protocol):
    source_name: str

    def retrieve(self, request: RetrievalRequest) -> tuple[list[NormalizedPost], RetrievalReport]:
        ...


_AUTH_PATTERN = re.compile(r"(authorization\s*[:=]\s*)(\S+(\s+\S+)?)", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"(bearer\s+)\S+", re.IGNORECASE)


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _AUTH_PATTERN.sub(r"\1[REDACTED]", text)
    return _BEARER_PATTERN.sub(r"\1[REDACTED]", text)


def sanitize_error(exc: BaseException, secrets: tuple[str, ...] = ()) -> dict:
    return {"type": type(exc).__name__, "message": scrub(str(exc), secrets)[:200]}
