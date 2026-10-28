"""`python -m app` (from backend/): start the API with host/port/reload from backend/.env."""
import uvicorn

from app import settings

uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.API_RELOAD)
