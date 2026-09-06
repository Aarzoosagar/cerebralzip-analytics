"""FastAPI application entrypoint.

Step 0 scope: minimal app exposing GET /health only. The dashboard router
and /query endpoint are wired in once their underlying features exist.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.routes import router as api_router

app = FastAPI(
    title="CerebralZip E-Commerce Sales Analytics Chatbot",
    description="AI-assisted analytics over the Olist Brazilian e-commerce dataset.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"), "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(dashboard_router)
