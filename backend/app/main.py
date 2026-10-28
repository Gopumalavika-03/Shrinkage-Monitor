"""FastAPI app. Start with `python -m app` (from backend/; host/port from backend/.env). Serves the built frontend if present."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import settings
from app.api.routes import router

app = FastAPI(title="Shrinkage Detection API", version="1.0.0",
              description="Synthetic retail stock data, planted anomalies, rule-based shrinkage alerts and their evaluation.")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():   # `npm run build` -> one server for API + UI
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
