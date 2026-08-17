from importlib.metadata import version

import structlog
from fastapi import FastAPI

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.app.lifespan import lifespan
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.auth.callbacks import configured_store_integrations
from nativespeaker.api.config import raw_config_file
from nativespeaker.api.logs import RequestLoggingMiddleware
from nativespeaker.api.models.api import ErrorResponse
from nativespeaker.api.routers import (
              build_webhooks_router,
              chats_router,
              examples_router,
              health_router,
              root_router,
              users_router,
)

logger = structlog.get_logger()

# Public means zero authentication, and the only zero-authentication routes this specification
# allows are the probes. FastAPI's generated schema and documentation routes are therefore not
# registered at all rather than served anonymously: authentication is the default, and the
# allowlist stays as short as the specification names it.
# [impl->req~sessions-shared-entry-point-three-way-partition~1]
app = FastAPI(title="NativeSpeaker API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("ns-api-gateway"),
              lifespan=lifespan,
              openapi_url=None,
              docs_url=None,
              redoc_url=None,
              responses={
                  400: {"model": ErrorResponse, "description": "Invalid request"},
                  401: {"model": ErrorResponse, "description": "Unauthorized"},
                  404: {"model": ErrorResponse, "description": "Not found"},
                  422: {"model": ErrorResponse, "description": "Validation error"},
                  429: {"model": ErrorResponse, "description": "Rate limited"},
                  500: {"model": ErrorResponse, "description": "Internal error"},
                  503: {"model": ErrorResponse, "description": "Service unavailable"},
              })

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
app.include_router(users_router)
# A store's callback route is not registered at all while that store's integration is
# unconfigured, so the routes come from the registry filtered by the configured integrations.
# [impl->req~sessions-named-verifier-per-callback-route~1]
app.include_router(build_webhooks_router(configured_store_integrations(raw_config_file())))
register_exception_handlers(app)
# ty cannot match a BaseHTTPMiddleware subclass against Starlette's
# _MiddlewareFactory ParamSpec protocol; this is the documented usage.
# Middleware runs outermost-last, so the barrier is added after the request logger and
# therefore runs inside it: every authenticated route, declared or not, passes the shared
# pre-handler barrier before its handler is reached.
# [impl->req~shared-prehandler-barrier~1]
# [impl->req~shared-route-categories~1]
app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]
app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
