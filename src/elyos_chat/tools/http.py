"""Single shared HTTP client for all tool endpoints.

Retry policy: 3 attempts max, exponential backoff with jitter, honor Retry-After.
Returns Result objects — never raises out to callers. All errors surface as
data the LLM can read and reason about.
"""
from __future__ import annotations
import asyncio
import random
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

import httpx

from elyos_chat.chat.cancel import CancelToken

T = TypeVar("T")

TRANSIENT_STATUSES = {429, 502, 503, 504}


@dataclass
class Result(Generic[T]):
    value: Optional[T] = None
    error: Optional[str] = None
    is_transient: bool = False

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_err(self) -> bool:
        return self.error is not None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def err(cls, msg: str, transient: bool = False) -> "Result[T]":
        return cls(error=msg, is_transient=transient)


class ToolHttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_attempts: int = 3,
        base_backoff: float = 0.25,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0),
            headers={"X-API-Key": api_key},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict, cancel: CancelToken) -> "Result[dict]":
        url = f"{self.base_url}{path}"
        last_err = "unknown"
        for attempt in range(self.max_attempts):
            if cancel.cancelled():
                return Result.err("cancelled", transient=False)
            try:
                resp = await self._client.get(url, params=params)
            except httpx.ReadTimeout:
                last_err = "read-timeout"
                if not await self._sleep_or_cancel(attempt, None, cancel):
                    return Result.err("cancelled", transient=False)
                continue
            except httpx.ConnectError as e:
                last_err = f"connect-error: {e}"
                if not await self._sleep_or_cancel(attempt, None, cancel):
                    return Result.err("cancelled", transient=False)
                continue
            except httpx.HTTPError as e:
                return Result.err(f"http-error: {e}", transient=False)

            if resp.status_code in TRANSIENT_STATUSES:
                last_err = f"transient-status:{resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if not await self._sleep_or_cancel(attempt, retry_after, cancel):
                    return Result.err("cancelled", transient=False)
                continue

            if resp.status_code >= 400:
                return Result.err(f"http-{resp.status_code}: {resp.text[:200]}", transient=False)

            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype:
                return Result.err(f"non-json:{resp.text[:200]}", transient=False)
            try:
                return Result.ok(resp.json())
            except ValueError as e:
                return Result.err(f"invalid-json:{e}", transient=False)

        return Result.err(f"exhausted retries: {last_err}", transient=True)

    async def _sleep_or_cancel(self, attempt: int, retry_after: Optional[str], cancel: CancelToken) -> bool:
        """Sleep between retries. Returns False if cancelled during sleep."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self.base_backoff * (2 ** attempt)
        else:
            delay = self.base_backoff * (2 ** attempt) + random.uniform(0, self.base_backoff)
        try:
            await asyncio.wait_for(cancel.wait(), timeout=delay)
            return False  # cancel fired during sleep
        except asyncio.TimeoutError:
            return True   # slept fully
