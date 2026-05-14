"""Systematic Elyos API probe.

Run: python scripts/probe_api.py
Reads ELYOS_API_BASE and ELYOS_API_KEY from env.

Prints findings as Markdown so the output can be piped or copied into
docs/api-findings.md. Each probe block is labeled with a category so
the operator can pick which to deepen.
"""
from __future__ import annotations
import asyncio
import os
import statistics
import time
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["ELYOS_API_BASE"]
KEY = os.environ["ELYOS_API_KEY"]
H = {"X-API-Key": KEY}


def section(title: str) -> None:
    print(f"\n## {title}\n")


async def show(client, label, method, path, params=None, headers=None):
    headers = headers if headers is not None else H
    t0 = time.perf_counter()
    try:
        resp = await client.get(f"{BASE}{path}", params=params, headers=headers)
        dt = (time.perf_counter() - t0) * 1000
        body = resp.text
        ctype = resp.headers.get("content-type", "")
        print(f"- **{label}** → {resp.status_code} `{ctype}` {dt:.0f}ms")
        print(f"  ```\n  {body[:300]}\n  ```")
    except Exception as e:
        print(f"- **{label}** → EXC {type(e).__name__}: {e}")


async def auth_probes(client):
    section("Auth")
    await show(client, "no key", "GET", "/weather", {"location": "London"}, headers={})
    await show(client, "wrong key", "GET", "/weather", {"location": "London"}, headers={"X-API-Key": "wrong"})
    await show(client, "lowercase header", "GET", "/weather", {"location": "London"}, headers={"x-api-key": KEY})


async def param_probes(client):
    section("Weather params")
    await show(client, "happy", "GET", "/weather", {"location": "London"})
    await show(client, "missing", "GET", "/weather", {})
    await show(client, "empty", "GET", "/weather", {"location": ""})
    await show(client, "unicode", "GET", "/weather", {"location": "São Paulo"})
    await show(client, "very long", "GET", "/weather", {"location": "A" * 500})
    await show(client, "whitespace", "GET", "/weather", {"location": "  London  "})
    await show(client, "unknown extra", "GET", "/weather", {"location": "London", "format": "json"})

    section("Research params")
    await show(client, "happy", "GET", "/research", {"topic": "solar energy"})
    await show(client, "missing", "GET", "/research", {})
    await show(client, "empty", "GET", "/research", {"topic": ""})
    await show(client, "encoded space", "GET", "/research", {"topic": "solar+energy"})
    await show(client, "unicode", "GET", "/research", {"topic": "café science"})


async def determinism_probes(client):
    section("Determinism — weather")
    for i in range(3):
        await show(client, f"London #{i+1}", "GET", "/weather", {"location": "London"})

    section("Determinism — research")
    for i in range(3):
        await show(client, f"solar #{i+1}", "GET", "/research", {"topic": "solar energy"})


async def timing_probe(client, path, params, n):
    section(f"Timing — {path} ({n} calls)")
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{BASE}{path}", params=params, headers=H)
            times.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            print(f"- EXC {e}")
    if times:
        print(f"- n={len(times)}, p50={statistics.median(times):.0f}ms, "
              f"min={min(times):.0f}ms, max={max(times):.0f}ms")


async def concurrency_probe(client):
    section("Concurrency — 5 parallel /research")
    t0 = time.perf_counter()
    tasks = [
        client.get(f"{BASE}/research", params={"topic": f"topic-{i}"}, headers=H)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    dt = (time.perf_counter() - t0) * 1000
    print(f"- total wall: {dt:.0f}ms")
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"  - task {i}: EXC {type(r).__name__}")
        else:
            print(f"  - task {i}: {r.status_code} {len(r.text)} bytes")


async def main():
    async with httpx.AsyncClient(timeout=30.0) as client:
        await auth_probes(client)
        await param_probes(client)
        await determinism_probes(client)
        await timing_probe(client, "/weather", {"location": "London"}, 5)
        await timing_probe(client, "/research", {"topic": "solar"}, 3)
        await concurrency_probe(client)


if __name__ == "__main__":
    asyncio.run(main())
