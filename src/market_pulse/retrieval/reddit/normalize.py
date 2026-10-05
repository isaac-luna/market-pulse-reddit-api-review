"""Review snapshot of Reddit result normalization."""

from __future__ import annotations

from datetime import UTC, datetime

from ..permalink import validate_permalink
from ..port import NormalizedPost

REMOVED_MARKERS = frozenset({"[removed]", "[deleted]"})
DELETED_AUTHOR = "[deleted]"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def is_unavailable(data: dict) -> bool:
    return bool(data.get("removed_by_category")) or data.get("selftext") in REMOVED_MARKERS


def normalize_post(data: dict) -> NormalizedPost:
    crosspost = _text(data.get("crosspost_parent"))
    external_id = crosspost or _text(data.get("name")) or f"t3_{data['id']}"
    available = not is_unavailable(data)

    author = _text(data.get("author"))
    if author == DELETED_AUTHOR:
        author = None

    engagement = {
        key: data[key]
        for key in ("score", "num_comments")
        if isinstance(data.get(key), int)
    }

    return NormalizedPost(
        external_id=external_id,
        permalink=validate_permalink(data.get("permalink")),
        published_at=datetime.fromtimestamp(float(data["created_utc"]), tz=UTC),
        community=str(data.get("subreddit") or ""),
        author_username=author if available else None,
        title=_text(data.get("title")) if available else None,
        body=_text(data.get("selftext")) if available else None,
        engagement=engagement if available else {},
        available=available,
    )
