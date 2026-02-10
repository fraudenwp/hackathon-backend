import time
from contextlib import asynccontextmanager
from datetime import date
from os import environ as env

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id.context import correlation_id
from fastapi import FastAPI, Request, Response
from fastapi.responses import ORJSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from uvicorn.protocols.utils import get_path_with_query_string

from src import routers
from src.constants.env import DEVELOPMENT
from src.models.database import Database
from src.utils.logger import log_error, logger, setup_logging
from src.utils.managers.websocket_manager import WebSocketManager


class ErrorMonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            log_error(
                logger,
                f"Error in endpoint {request.url.path}",
                e.with_traceback(e.__traceback__),
                endpoint=request.url.path,
                method=request.method,
                headers=dict(request.headers),
                request_type="http",
            )
            raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up the application", date=date.today())
    yield
    # Shutdown
    logger.info("Shutting down the application")

    # Close WebSocket connections first
    ws_manager = WebSocketManager()
    await ws_manager.close()
    logger.info("WebSocket connections closed")

    # Then close database connections
    await Database().close_all_connections()
    logger.info("Database connections closed")


app = FastAPI(
    debug=False,
    title="TalenterAI API",
    description="TalenterAI API Documentation",
    version=env.get("APP_VERSION", "1.0.0"),
    docs_url="/docs" if DEVELOPMENT else None,
    redoc_url="/redoc" if DEVELOPMENT else None,
    middleware=[],
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)

setup_logging()

app.add_middleware(ErrorMonitoringMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    structlog.contextvars.clear_contextvars()

    # Get or generate correlation ID
    request_id = correlation_id.get()

    # Bind web_trace_id to structlog context
    structlog.contextvars.bind_contextvars(
        web_trace_id=request_id,
    )

    # Add correlation ID to response headers
    response = Response(status_code=500)
    response.headers["X-Correlation-ID"] = request_id

    start_time = time.perf_counter_ns()
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = (
            request_id  # Ensure it's in successful responses too
        )
        return response
    except Exception as e:
        # Add error context
        structlog.stdlib.get_logger("api.error").exception("Uncaught exception")
        logger.error(
            "Logging middleware caught an exception",
            error=str(e),
            error_type=type(e).__name__,
            traceback=str(e.__traceback__),
        )
        raise
    finally:
        process_time = time.perf_counter_ns() - start_time
        status_code = response.status_code
        url = get_path_with_query_string(request.scope)
        client_host = request.client.host
        client_port = request.client.port
        http_method = request.method
        http_version = request.scope["http_version"]
        logger.info(
            f"""{client_host}:{client_port} - "{http_method} {url} HTTP/{http_version}" {status_code}""",
            http={
                "url": str(request.url),
                "status_code": status_code,
                "method": http_method,
                "request_id": request_id,
                "version": http_version,
            },
            network={"client": {"ip": client_host, "port": client_port}},
            duration=process_time,
        )
        response.headers["X-Process-Time"] = str(process_time / 10**9)
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for webhooks and widget embedding
    allow_credentials=False,  # Disabled to allow "*" origin (webhooks use Bearer token)
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)

for router in routers.__all__:
    app.include_router(**getattr(routers, router).__dict__)


@app.get("/")
def index():
    return f"TalenterAI API v{env.get('APP_VERSION', '1.0.0')}"


@app.get("/health")
async def health():
    return {"message": "healthy"}
