"""FastAPI Application entrypoint with production hardening."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.deps import get_repository
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.agents_gateway import router as agents_gateway_router
from app.api.v1.auth import router as auth_router
from app.api.v1.agentic import router as agentic_router
from app.api.v1.benchmark import router as benchmark_router
from app.api.v1.budgets import router as budgets_router
from app.api.v1.chat import router as chat_router
from app.api.v1.cockpit import router as cockpit_router
from app.api.v1.credentials import router as credentials_router
from app.api.v1.models import router as models_router
from app.api.v1.routing import router as routing_router
from app.core.config import settings
from app.core.errors import GatewayError
from app.core.rate_limiter import default_rate_limiter, extract_client_ip
from app.core.logging import (
    configure_logging,
    correlation_request_id,
    correlation_trace_id,
    get_logger,
)

configure_logging(settings.LOG_LEVEL)
logger = get_logger("app.main")

HTTP_422_CODE = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
HTTP_413_CODE = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing Smart AI Gateway services...")
    # Validate critical production security invariants
    settings.validate_production_security()
    repo = await get_repository()
    await repo.initialize()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down Smart AI Gateway...")


app = FastAPI(
    title="Smart AI Gateway",
    version="0.1.0",
    description="Modular AI Gateway with auto-routing, LLMOps, and agent evaluation.",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_limits_middleware(request: Request, call_next):
    # 0. Client Rate Limiting
    client_ip = extract_client_ip(request)
    is_allowed, retry_after = default_rate_limiter.check_rate_limit(client_ip)
    if not is_allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
            content={
                "error": {
                    "type": "rate_limited",
                    "message": f"Rate limit exceeded ({settings.RATE_LIMIT_RPM} RPM). Retry in {retry_after}s.",
                    "retryable": True,
                }
            },
        )

    # 1. Protection against large payload DoS
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
        return JSONResponse(
            status_code=HTTP_413_CODE,
            content={
                "error": {
                    "type": "invalid_request",
                    "message": f"Request body exceeds maximum size of {settings.MAX_REQUEST_BODY_BYTES} bytes",
                    "retryable": False,
                }
            },
        )

    # 2. Correlation IDs
    trace_id = request.headers.get("X-Trace-ID", "")
    req_id = request.headers.get("X-Request-ID", "")
    if trace_id:
        correlation_trace_id.set(trace_id)
    if req_id:
        correlation_request_id.set(req_id)

    response = await call_next(request)

    # 3. Security headers (HSTS, clickjacking, MIME sniffing protections)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    if trace_id:
        response.headers["X-Trace-ID"] = trace_id
    if req_id:
        response.headers["X-Request-ID"] = req_id

    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers or {}
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=headers)
    elif isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": "http_error",
                    "message": str(exc.detail),
                    "retryable": False,
                    "trace_id": correlation_trace_id.get(""),
                }
            },
            headers=headers,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": "http_error",
                "message": str(exc.detail),
                "retryable": False,
                "trace_id": correlation_trace_id.get(""),
            }
        },
        headers=headers,
    )


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "type": exc.error_type,
                "message": exc.message,
                "retryable": exc.retryable,
                "trace_id": exc.trace_id or correlation_trace_id.get(""),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=HTTP_422_CODE,
        content={
            "error": {
                "type": "invalid_request",
                "message": str(exc),
                "retryable": False,
                "trace_id": correlation_trace_id.get(""),
            }
        },
    )


app.include_router(health_router)
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(models_router)
app.include_router(analytics_router)
app.include_router(routing_router)
app.include_router(benchmark_router)
app.include_router(credentials_router)
app.include_router(budgets_router)
app.include_router(agentic_router)
app.include_router(agents_gateway_router)
app.include_router(cockpit_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
async def serve_chat_ui(request: Request, key: Optional[str] = None):
    """Serves the interactive web chat client with optional cookie initialization."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        response = FileResponse(html_path)
        if key and key.strip():
            response.set_cookie(
                key="smartai_gateway_key",
                value=key.strip(),
                max_age=86400 * 30,
                httponly=False,
                samesite="lax",
                secure=settings.APP_ENV == "production",
            )
        return response
    return JSONResponse({"status": "Gateway online", "docs": "/docs"})
