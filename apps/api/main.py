"""
VARUNA GRID — FastAPI Application.

M3.5 Productized Backend API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import settings
from apps.api.errors import register_error_handlers
from apps.api.routers import cases, events, health

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

register_error_handlers(app)

app.include_router(cases.router)
app.include_router(events.router)
app.include_router(health.router)

