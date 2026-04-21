"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api import tasks, results
from app.config import settings


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def _cleanup_old_tasks() -> None:
    """Remove task directories older than max_task_age_days on startup."""
    if not settings.storage_base_dir.exists():
        return
    import shutil
    import time
    from datetime import datetime, timedelta

    cutoff = datetime.now() - timedelta(days=settings.max_task_age_days)
    cutoff_ts = cutoff.timestamp()
    removed = 0

    for item in settings.storage_base_dir.iterdir():
        if not item.is_dir():
            continue
        # Only remove directories that look like task dirs (have status.json)
        if not (item / "status.json").exists():
            continue
        try:
            mtime = item.stat().st_mtime
            if mtime < cutoff_ts:
                shutil.rmtree(item)
                removed += 1
                print(f"[CLEANUP] Removed old task dir: {item.name}")
        except Exception as exc:
            print(f"[CLEANUP] Failed to remove {item.name}: {exc}")

    if removed:
        print(f"[CLEANUP] Total removed: {removed} task(s) older than {settings.max_task_age_days} days")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings.storage_base_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_tasks()
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
    app.mount("/", NoCacheStaticFiles(directory=str(frontend_dir), html=True), name="frontend")
