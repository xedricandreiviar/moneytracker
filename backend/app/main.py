"""FastAPI application entry point with CORS and APScheduler lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.budgets import router as budgets_router
from app.api.daily_task import router as daily_task_router
from app.api.insights import router as insights_router
from app.api.notifications import router as notifications_router
from app.api.settings import router as settings_router
from app.api.transactions import router as transactions_router
from app.config import settings
from app.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan: start scheduler on startup, stop on shutdown."""
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register API routers
app.include_router(settings_router)
app.include_router(transactions_router)
app.include_router(daily_task_router)
app.include_router(budgets_router)
app.include_router(insights_router)
app.include_router(ai_router)
app.include_router(notifications_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
