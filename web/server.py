"""FastAPI app entrypoint.

Run: uvicorn web.server:app --reload
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.deps import state


DEV_ORIGINS = os.environ.get(
    "ELYOS_DEV_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await state.startup()
    yield
    await state.shutdown()


app = FastAPI(title="elyos-chat-web", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes registered in later tasks via app.include_router / direct decorators.

# Static SPA mount — only if web-ui/dist exists. Vite dev server handles this in dev.
SPA_DIR = Path(__file__).resolve().parents[1] / "web-ui" / "dist"
if SPA_DIR.exists():
    app.mount("/", StaticFiles(directory=str(SPA_DIR), html=True), name="spa")
