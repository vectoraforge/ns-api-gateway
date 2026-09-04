from importlib.metadata import version

import structlog
from fastapi import FastAPI

from nativespeaker.api.app.error_handlers import register_exception_handlers
from nativespeaker.api.app.lifespan import lifespan
from nativespeaker.api.errors import ErrorResponse
from nativespeaker.api.logs import RequestLoggingMiddleware
from nativespeaker.api.routers import (
              auth_router,
              chats_router,
              examples_router,
              health_router,
              root_router,
              users_router,
              webhooks_router,
)

logger = structlog.get_logger()

app = FastAPI(title="NativeSpeaker API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("ns-api-gateway"),
              lifespan=lifespan,
              # Off because FastAPI registers these on the app router directly, bypassing router-level auth.
              docs_url=None,
              redoc_url=None,
              openapi_url=None,
              responses={
                  400: {"model": ErrorResponse, "description": "Invalid request"},
                  401: {"model": ErrorResponse, "description": "Authentication required"},
                  404: {"model": ErrorResponse, "description": "Not found"},
                  405: {"model": ErrorResponse, "description": "Method not allowed"},
                  422: {"model": ErrorResponse, "description": "Validation error"},
                  429: {"model": ErrorResponse, "description": "Rate limited"},
                  500: {"model": ErrorResponse, "description": "Internal error"},
                  503: {"model": ErrorResponse, "description": "Service unavailable"},
              })

# A redirect is produced before any route matches, so `GET /chats/` would be an unauthenticated 307.
app.router.redirect_slashes = False

# Each router declares its own auth dependency; health declares none, being the whole public allowlist.
app.include_router(root_router)
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(users_router)
app.include_router(webhooks_router)
app.include_router(health_router)
register_exception_handlers(app)
# ty cannot match a BaseHTTPMiddleware subclass against Starlette's _MiddlewareFactory protocol.
app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]
