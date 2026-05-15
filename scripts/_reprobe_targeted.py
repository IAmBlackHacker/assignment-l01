"""Targeted re-probe with spacing to avoid rate limiting.

Captures: research body shape, determinism, empty topic, unicode topic.
Outputs to stdout so we can capture or review.
"""
from __future__ import annotations
import asyncio
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["ELYOS_API_BASE"]
KEY = os.environ["ELYOS_API_KEY"]
H = {"X-API-Key": KEY}

DELAY = 12  # seconds between requests


async def show(client, label: str, path: str, params: dict | None = None, headers: dict | None = None):
    if headers is None:
        headers = H
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"{BASE}{path}", params=params or {}, headers=headers)
        dt = (time.perf_counter() - t0) * 1000
        body = resp.text
        ctype = resp.headers.get("content-type", "?")
        print(f"\n### {label}")
        print(f"Status: {resp.status_code}  Content-Type: {ctype}  Time: {dt:.0f}ms")
        print(f"Body: {body[:500]}")
    except Exception as e:
        print(f"\n### {label}")
        print(f"EXC: {type(e).__name__}: {e}")


async def main():
    print(f"# Targeted re-probe — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# Delay between requests: {DELAY}s")

    async with httpx.AsyncClient(timeout=30.0) as client:

        # 1. Research happy path — first call
        await show(client, "research/solar #1", "/research", {"topic": "solar energy"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 2. Research happy path — second call (check determinism)
        await show(client, "research/solar #2", "/research", {"topic": "solar energy"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 3. Research happy path — third call (check determinism)
        await show(client, "research/solar #3", "/research", {"topic": "solar energy"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 4. Research empty topic
        await show(client, "research/empty", "/research", {"topic": ""})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 5. Research unicode topic
        await show(client, "research/unicode café", "/research", {"topic": "café science"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 6. Weather London (verify multi-condition)
        await show(client, "weather/London", "/weather", {"location": "London"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 7. Weather Tokyo (check response shape variability)
        await show(client, "weather/Tokyo", "/weather", {"location": "Tokyo"})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 8. Weather whitespace location
        await show(client, "weather/whitespace-location", "/weather", {"location": "  London  "})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 9. Research missing param (FastAPI 422 shape)
        await show(client, "research/missing-param", "/research", {})
        print(f"\n[sleeping {DELAY}s]")
        await asyncio.sleep(DELAY)

        # 10. Research unknown extra param
        await show(client, "research/extra-param", "/research", {"topic": "solar energy", "depth": "deep"})

    print("\n# Done")


if __name__ == "__main__":
    asyncio.run(main())
