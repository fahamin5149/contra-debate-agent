from fastapi.testclient import TestClient

from contra.config.models import Config
from contra.ui.server import create_app


async def fake_on_offer(sdp: str, sdp_type: str) -> dict[str, str]:
    return {"sdp": "v=0\r\nfake-answer", "type": "answer"}


def test_health_returns_ok():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_offer_returns_answer():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.post("/api/webrtc/offer", json={"sdp": "v=0\r\n", "type": "offer"})
    assert r.status_code == 200
    assert r.json()["type"] == "answer"


def test_offer_rejects_missing_sdp():
    client = TestClient(create_app(Config(), fake_on_offer))
    assert client.post("/api/webrtc/offer", json={"type": "offer"}).status_code == 422


def test_index_is_served():
    client = TestClient(create_app(Config(), fake_on_offer))
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
