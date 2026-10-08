from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.patient_auth import router as patient_auth_router
from app.api.appointments import (
    coordinator_router as coordinator_appointments_router,
    patient_router as patient_appointments_router,
)
from app.api.conversations import (
    coordinator_router as coordinator_conversations_router,
    faq_router,
    patient_router as patient_conversations_router,
)
from app.api.participants import router as patients_router
from app.config import settings
from app.database import check_database, check_vector_extension
from app.dependencies import check_redis
from app.logging_config import configure_logging
from app.services.audit_service import AuditService

configure_logging()
app = FastAPI(title=settings.PROJECT_NAME, version=settings.APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)
audit_service = AuditService()
logger = structlog.get_logger("api")
app.include_router(patient_auth_router, prefix="/api/v1")
app.include_router(patient_appointments_router, prefix="/api/v1")
app.include_router(coordinator_appointments_router, prefix="/api/v1")
app.include_router(patient_conversations_router, prefix="/api/v1")
app.include_router(coordinator_conversations_router, prefix="/api/v1")
app.include_router(faq_router, prefix="/api/v1")
app.include_router(patients_router, prefix="/api/v1/patients")
app.include_router(
    patients_router,
    prefix="/api/v1/participants",
    include_in_schema=False,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    start = time.perf_counter()
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        correlation_id=correlation_id,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": jsonable_encoder(exc.errors()),
            "correlation_id": correlation_id,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An internal error occurred.",
            "correlation_id": correlation_id,
        },
    )


@app.get("/api/v1/health")
async def health(request: Request) -> dict[str, Any]:
    audit_service.record_event("system_check", endpoint="health")
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "correlation_id": request.state.correlation_id,
    }


@app.get("/api/v1/readiness")
async def readiness(request: Request) -> dict[str, Any]:
    db_ok, db_message = await check_database()
    vector_ok, vector_message = await check_vector_extension()
    redis_ok, redis_message = await check_redis()
    ready = db_ok and redis_ok and (vector_ok or not settings.REQUIRE_PGVECTOR)
    audit_service.record_event("readiness_check", ready=ready, database=db_ok, vector=vector_ok, redis=redis_ok)
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "database": {"ok": db_ok, "message": db_message},
        "pgvector": {"ok": vector_ok, "message": vector_message},
        "redis": {"ok": redis_ok, "message": redis_message},
        "correlation_id": request.state.correlation_id,
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.PROJECT_NAME, "status": "ok"}
