"""FastAPI application entry point with CORS, onboarding gate, and APScheduler lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.ai import router as ai_router
from app.api.budgets import router as budgets_router
from app.api.daily_task import router as daily_task_router
from app.api.dashboard import router as dashboard_router
from app.api.insights import router as insights_router
from app.api.notifications import router as notifications_router
from app.api.profile import router as profile_router
from app.api.settings import router as settings_router
from app.api.transactions import router as transactions_router
from app.api.weights import router as weights_router
from app.config import settings
from app.database import get_db, SessionLocal
from app.models.user import User
from app.scheduler import shutdown_scheduler, start_scheduler

# Routes exempt from the profile onboarding gate
ONBOARDING_EXEMPT_PATHS = (
    "/api/profile",
    "/api/settings/locale",
    "/api/weights",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class ProfileOnboardingGateMiddleware(BaseHTTPMiddleware):
    """Middleware that blocks access to protected routes until profile onboarding is complete.

    If user.profile_completed is False and the route is not /api/profile or
    /api/settings/locale, returns 403 with message "Profile onboarding required".

    Requirements covered: 15.1
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow exempt paths (profile, locale settings, health, docs)
        if any(path.startswith(exempt) for exempt in ONBOARDING_EXEMPT_PATHS):
            return await call_next(request)

        # Check profile_completed for the current user
        # Use the dependency override if available (for testability), else SessionLocal
        db_override = request.app.dependency_overrides.get(get_db)
        if db_override:
            db_gen = db_override()
            db = next(db_gen)
            should_close = False
        else:
            db = SessionLocal()
            should_close = True

        try:
            user = db.query(User).filter(User.id == 1).first()
            if user and not user.profile_completed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Profile onboarding required"},
                )
        finally:
            if should_close:
                db.close()

        return await call_next(request)


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

# Profile onboarding gate middleware (Requirement 15.1)
app.add_middleware(ProfileOnboardingGateMiddleware)


# Register API routers
app.include_router(profile_router)
app.include_router(settings_router)
app.include_router(transactions_router)
app.include_router(daily_task_router)
app.include_router(budgets_router)
app.include_router(insights_router)
app.include_router(ai_router)
app.include_router(notifications_router)
app.include_router(weights_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
