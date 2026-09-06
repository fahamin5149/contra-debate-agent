from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from contra.config.models import Config

STATIC_DIR = Path(__file__).parent / "static"


class Offer(BaseModel):
    sdp: str
    type: str


OnOffer = Callable[[str, str], Awaitable[dict[str, str]]]


def create_app(config: Config, on_offer: OnOffer) -> FastAPI:
    """Build the FastAPI app.

    Binds to loopback only — enforced upstream by UiConfig (NFR-S-03).
    """
    app = FastAPI(title="Contra", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/webrtc/offer")
    async def webrtc_offer(offer: Offer) -> dict[str, str]:
        return await on_offer(offer.sdp, offer.type)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
