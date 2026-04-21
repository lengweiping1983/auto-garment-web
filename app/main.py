"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import tasks, results
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings.storage_base_dir.mkdir(parents=True, exist_ok=True)
    from app.core.neo_ai_client import NeoAIClient
    neo = NeoAIClient()
    print(f"[STARTUP] NeoAI token prefix: {neo.token[:20]}..." if neo.token else "[STARTUP] NeoAI token is EMPTY")
    yield
    # Shutdown


app = FastAPI(
    title="Auto Garment Producer API",
    description="Automated garment pattern generation from theme images",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}


# API routers
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(results.router, prefix="/api/v1", tags=["results"])

# Static frontend
frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
