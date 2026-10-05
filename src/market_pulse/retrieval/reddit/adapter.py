"""Review snapshot of Market Pulse's Reddit Data API adapter.

Live use remains gated pending approved Reddit Data API access and confirmation
that the intended analytical use is permitted.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import praw
import prawcore
from prawcore.const import WINDOW_SIZE

from ...config import Settings
from ...domain.enums import StopReason
from ...domain.window import AnalysisWindow
from ...lifecycle.cancellation import Cancelled
from ...store.db import utcnow
from ..port import NormalizedPost, RetrievalReport, RetrievalRequest, sanitize_error
from .normalize import normalize_post

OPERATION_CAP_S = 10.0
PAGE_SIZE = 100
LISTING_CAP = 1000
READ_CHUNK = 64 * 1024
RETRYABLE_STATUSES = frozenset({401, 408, 500, 502, 503, 504, 520, 522})


class OperationBudgetExceeded(Exception):
    pass


class SourceRequestFailed(Exception):
    pass


class OperationBudget:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.monotonic = monotonic
        self.deadline: float | None = None
        self.ratelimit: tuple[float, int, int, int] | None = None

    def begin(self, seconds: float) -> None:
        self.deadline = self.monotonic() + seconds

    def end(self) -> None:
        self.deadline = None

    def remaining(self) -> float:
        if self.deadline is None:
            raise OperationBudgetExceeded("no source operation is active")
        return self.deadline - self.monotonic()

    def observe(self, headers: Any) -> None:
        try:
            remaining = int(float(headers["x-ratelimit-remaining"]))
            used = int(headers["x-ratelimit-used"])
            reset = int(headers["x-ratelimit-reset"])
        except (KeyError, TypeError, ValueError):
            return
        self.ratelimit = (self.monotonic(), remaining, used, reset)

    def predicted_wait(self) -> float:
        if self.ratelimit is None:
            return 0.0
        observed_at, remaining, used, reset = self.ratelimit
        if remaining <= 0:
            wait = max(1.0, float(reset))
        else:
            wait = min(
                float(reset),
                max(reset - (WINDOW_SIZE - WINDOW_SIZE / (remaining + used) * used), 0.0),
                10.0,
            )
        return max(0.0, observed_at + wait - self.monotonic())


class BoundedRequestor(prawcore.Requestor):
    def __init__(self, *args: Any, budget: OperationBudget, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.budget = budget

    def request(self, *args: Any, timeout: float | None = None, **kwargs: Any):
        remaining = self.budget.remaining()
        if remaining <= 0:
            raise OperationBudgetExceeded("operation budget exhausted before the request")
        kwargs["stream"] = True
        try:
            response = self._http.request(*args, timeout=(remaining, remaining), **kwargs)
            body = self._read_body(response)
        except (OperationBudgetExceeded, SourceRequestFailed):
            raise
        except Exception as exc:
            raise SourceRequestFailed(type(exc).__name__) from None

        response._content = body
        response._content_consumed = True
        self.budget.observe(response.headers)

        if response.status_code in RETRYABLE_STATUSES:
            raise SourceRequestFailed(f"HTTP {response.status_code}")
        return response

    def _read_body(self, response) -> bytes:
        raw = response.raw
        sock = getattr(getattr(raw, "connection", None), "sock", None)
        reader = getattr(raw, "read1", None) or raw.read
        chunks: list[bytes] = []

        while True:
            remaining = self.budget.remaining()
            if remaining <= 0:
                response.close()
                raise OperationBudgetExceeded("operation budget exhausted while reading the response")
            if sock is not None:
                sock.settimeout(remaining)
            chunk = reader(READ_CHUNK)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


class RedditAdapter:
    source_name = "reddit"

    def __init__(
        self,
        settings: Settings,
        *,
        session: Any = None,
        clock: Callable[[], datetime] = utcnow,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.session = session
        self.clock = clock
        self.monotonic = monotonic
        self.budget = OperationBudget(monotonic)

    @property
    def has_credentials(self) -> bool:
        s = self.settings
        return bool(s.reddit_client_id and s.reddit_client_secret and s.reddit_user_agent)

    def build_reddit(self) -> praw.Reddit:
        requestor_kwargs: dict[str, Any] = {"budget": self.budget}
        if self.session is not None:
            requestor_kwargs["session"] = self.session

        return praw.Reddit(
            client_id=self.settings.reddit_client_id,
            client_secret=self.settings.reddit_client_secret,
            user_agent=self.settings.reddit_user_agent,
            requestor_class=BoundedRequestor,
            requestor_kwargs=requestor_kwargs,
            check_for_updates=False,
            check_for_async=False,
            ratelimit_seconds=0,
            timeout=int(OPERATION_CAP_S),
        )

    def _seconds_left(self, request: RetrievalRequest) -> float:
        return (request.deadline - self.clock()).total_seconds()

    def retrieve(self, request: RetrievalRequest) -> tuple[list[NormalizedPost], RetrievalReport]:
        report = RetrievalReport(
            executed=False,
            stop_reason=None,
            total_reported=None,
            search_parameters={
                "query": request.topic,
                "sort": request.search_sort,
                "time_filter": "month",
                "subreddit": "all",
                "type": "link",
            },
        )

        if not self.has_credentials:
            report.errors.append(
                {"type": "MissingCredentials", "message": "Reddit credentials are not configured"}
            )
            return [], report

        window = AnalysisWindow(request.period_start, request.period_end)
        reddit = self.build_reddit()
        posts: list[NormalizedPost] = []
        after: str | None = None
        seen = 0

        while True:
            request.cancel.check()
            left = self._seconds_left(request)
            if left <= 0:
                stop = StopReason.DEADLINE
                break
            if report.calls_made >= request.max_calls:
                stop = StopReason.CALL_BUDGET
                break

            wait = self.budget.predicted_wait()
            if wait >= left:
                stop = StopReason.RATE_LIMITED
                break
            if wait > 0 and request.cancel.event.wait(wait):
                raise Cancelled()

            params: dict[str, Any] = {
                "q": request.topic,
                "sort": request.search_sort,
                "t": "month",
                "type": "link",
                "limit": PAGE_SIZE,
            }
            if after:
                params["after"] = after

            report.calls_made += 1
            self.budget.begin(min(OPERATION_CAP_S, self._seconds_left(request)))
            try:
                data = reddit.request(method="GET", path="r/all/search", params=params)
            except prawcore.exceptions.TooManyRequests as exc:
                report.errors.append(sanitize_error(exc, self.settings.secrets))
                stop = StopReason.RATE_LIMITED
                break
            except Exception as exc:
                report.errors.append(sanitize_error(exc, self.settings.secrets))
                stop = (
                    StopReason.DEADLINE
                    if self._seconds_left(request) <= 0
                    else StopReason.ERRORS
                )
                break
            finally:
                self.budget.end()

            report.executed = True
            listing = data.get("data", {}) if isinstance(data, dict) else {}
            children = listing.get("children") or []
            seen += len(children)

            for child in children:
                if not isinstance(child, dict) or child.get("kind") != "t3":
                    continue
                post = normalize_post(child.get("data") or {})
                if window.contains(post.published_at):
                    posts.append(post)
                    report.posts_per_day[window.day_index(post.published_at)] += 1

            request.cancel.check()
            after = listing.get("after")
            if not after:
                stop = StopReason.SOURCE_TRUNCATED if seen >= LISTING_CAP else StopReason.EXHAUSTED
                break

        report.stop_reason = stop
        return posts, report
