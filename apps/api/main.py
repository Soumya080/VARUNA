"""
VARUNA GRID — FastAPI Application.

M3.5 Productized Backend API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apps.api.middleware.auth import AuthMiddleware
from apps.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.middleware.correlation import CorrelationIdMiddleware

from apps.api.config import settings
from apps.api.errors import register_error_handlers
from apps.api.routers import cases, events, health, readiness, missions, prahari, alerts, dashboard, replay, auth, run_stream, reports, chhaya

app = FastAPI(
    title=settings.api_title,
    description="Oil spill attribution — EXPERIMENTAL, M2.1 provisional results",
    version=settings.api_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)

register_error_handlers(app)

app.include_router(cases.router)
app.include_router(events.router)
app.include_router(health.router)
app.include_router(readiness.router)
app.include_router(missions.router)
app.include_router(prahari.router)
app.include_router(alerts.router)
app.include_router(alerts.cases_router)
app.include_router(dashboard.router)
app.include_router(replay.router)
app.include_router(auth.router)
app.include_router(run_stream.router)
app.include_router(reports.router)
app.include_router(chhaya.router)
