"""FastAPI application entry point.

Dev:   uvicorn app.main:app --reload --port 8000      (run inside backend/)
Prod:  the Docker image serves the built React app from STATIC_DIR on the same port.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai.llm import get_ai_client
from .api.routes import router
from .config import VERSION, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("qsim")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="OSCOWL Q-Sim API", version=VERSION, docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json",
                  description="Tensor-network quantum circuit simulation with AI-assisted, verified debugging.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix="/api")

    static = Path(s.static_dir)
    if (static / "index.html").is_file():
        if (static / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = (static / path).resolve()
            if path and target.is_file() and static.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(static / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {"service": "OSCOWL Q-Sim API", "docs": "/api/docs",
                    "ui": "Run the React dev server (frontend/) or build it into backend/static."}

    ai = get_ai_client().status()
    log.info("OSCOWL Q-Sim %s | AI mode: %s | Gemma: %s | array backend: %s", VERSION, ai["mode"], ai["gemma_provider"], s.array_backend)
    return app


app = create_app()
