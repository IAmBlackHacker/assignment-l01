import asyncio
import pytest

from elyos_chat.chat.cancel import CancelToken


async def test_token_starts_uncancelled():
    token = CancelToken()
    assert token.cancelled() is False


async def test_cancel_sets_flag():
    token = CancelToken()
    token.cancel()
    assert token.cancelled() is True


async def test_wait_unblocks_when_cancelled():
    token = CancelToken()

    async def cancel_soon():
        await asyncio.sleep(0.01)
        token.cancel()

    await asyncio.gather(cancel_soon(), token.wait())
    assert token.cancelled() is True


async def test_cancel_is_idempotent():
    token = CancelToken()
    token.cancel()
    token.cancel()
    assert token.cancelled() is True
