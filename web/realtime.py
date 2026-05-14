"""OpenAI Realtime API client wrapper.

Defines an abstract RealtimeWS interface so the voice relay can be unit-tested
with a FakeRealtimeWS. The real implementation connects to
wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview
"""
from __future__ import annotations
import json
import os
from typing import AsyncIterator, Protocol

import websockets


REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"


class RealtimeWS(Protocol):
    async def send_json(self, msg: dict) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def recv(self) -> dict | bytes: ...
    async def close(self) -> None: ...


class OpenAIRealtimeWS:
    """Real Realtime WebSocket connection.

    Sends JSON control messages (audio chunks are base64-encoded JSON in
    Realtime's protocol). Receives JSON events; audio comes back base64-encoded
    in `response.audio.delta` events.
    """
    def __init__(self, ws):
        self._ws = ws

    @classmethod
    async def connect(cls, voice: str = "alloy", tools: list[dict] | None = None) -> "OpenAIRealtimeWS":
        api_key = os.environ["OPENAI_API_KEY"]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        ws = await websockets.connect(
            REALTIME_URL,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
        )
        self = cls(ws)
        await self.send_json({
            "type": "session.update",
            "session": {
                "voice": voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {"type": "server_vad"},
                "tools": tools or [],
                "tool_choice": "auto",
            },
        })
        return self

    async def send_json(self, msg: dict) -> None:
        await self._ws.send(json.dumps(msg))

    async def send_bytes(self, data: bytes) -> None:
        """Send PCM16 audio. Realtime wraps it in a JSON event."""
        import base64
        await self.send_json({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(data).decode("ascii"),
        })

    async def recv(self) -> dict | bytes:
        """Returns dict for JSON events; for audio delta events, returns the dict
        (relay handles base64 decoding to bytes for downstream playback)."""
        raw = await self._ws.recv()
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw

    async def close(self) -> None:
        await self._ws.close()
