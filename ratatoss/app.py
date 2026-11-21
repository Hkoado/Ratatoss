"""Read-only HTTP surface for the loopback node starter."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse

from .settings import DEFAULT_NODE_PORT, LOOPBACK

STATIC = Path(__file__).with_name("static")


def create_app(port: int = DEFAULT_NODE_PORT) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    authority = f"{LOOPBACK}:{port}"
    authorities = {authority, LOOPBACK} if port == 80 else {authority}
    loopback_origins = {f"http://{host}" for host in authorities}

    @app.middleware("http")
    async def protect_loopback(request: Request, call_next):
        origins = request.headers.getlist("origin")
        hosts = request.headers.getlist("host")
        if (request.client is None or request.client.host != LOOPBACK
                or len(hosts) != 1 or hosts[0] not in authorities):
            return PlainTextResponse("Forbidden", status_code=403)
        if origins and (len(origins) != 1 or origins[0] not in loopback_origins):
            return PlainTextResponse("Forbidden", status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    async def home():
        return FileResponse(STATIC / "index.html", media_type="text/html; charset=utf-8")

    @app.get("/style.css")
    async def stylesheet():
        return FileResponse(STATIC / "style.css", media_type="text/css; charset=utf-8")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "mode": "starter", "transport_enabled": False}

    return app
