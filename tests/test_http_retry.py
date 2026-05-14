import httpx
import pytest
import respx

from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient


BASE = "https://example.test"


@pytest.fixture
async def client():
    c = ToolHttpClient(base_url=BASE, api_key="k", max_attempts=3, base_backoff=0.001)
    yield c
    await c.aclose()


@respx.mock
async def test_happy_path_returns_ok(client):
    respx.get(f"{BASE}/weather", params={"location": "London"}).mock(
        return_value=httpx.Response(200, json={"temp_c": 12})
    )
    result = await client.get("/weather", {"location": "London"}, CancelToken())
    assert result.is_ok
    assert result.value == {"temp_c": 12}


@respx.mock
async def test_retries_503_then_succeeds(client):
    route = respx.get(f"{BASE}/research").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"summary": "ok"}),
        ]
    )
    result = await client.get("/research", {"topic": "solar"}, CancelToken())
    assert result.is_ok
    assert route.call_count == 2


@respx.mock
async def test_gives_up_after_max_attempts(client):
    respx.get(f"{BASE}/research").mock(return_value=httpx.Response(503))
    result = await client.get("/research", {"topic": "x"}, CancelToken())
    assert result.is_err
    assert result.is_transient is True


@respx.mock
async def test_4xx_is_not_retried(client):
    route = respx.get(f"{BASE}/weather").mock(return_value=httpx.Response(400, json={"error": "bad"}))
    result = await client.get("/weather", {"location": ""}, CancelToken())
    assert result.is_err
    assert route.call_count == 1
    assert result.is_transient is False


@respx.mock
async def test_non_json_body_surfaces_as_error(client):
    respx.get(f"{BASE}/weather").mock(
        return_value=httpx.Response(200, content=b"<html>oops</html>", headers={"content-type": "text/html"})
    )
    result = await client.get("/weather", {"location": "x"}, CancelToken())
    assert result.is_err
    assert "non-json" in result.error.lower()


@respx.mock
async def test_cancel_aborts_between_retries(client):
    respx.get(f"{BASE}/research").mock(return_value=httpx.Response(503))
    token = CancelToken()
    token.cancel()  # already cancelled before any call
    result = await client.get("/research", {"topic": "x"}, token)
    assert result.is_err
    assert "cancel" in result.error.lower()


@respx.mock
async def test_sends_x_api_key_header(client):
    route = respx.get(f"{BASE}/weather").mock(return_value=httpx.Response(200, json={}))
    await client.get("/weather", {"location": "x"}, CancelToken())
    assert route.calls[0].request.headers["X-API-Key"] == "k"
