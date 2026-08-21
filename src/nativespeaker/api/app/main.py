from importlib.metadata import version

import structlog
from fastapi import FastAPI

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.app.lifespan import lifespan
from nativespeaker.api.auth.barrier import AuthBarrierMiddleware
from nativespeaker.api.errors import ErrorResponse
from nativespeaker.api.logs import RequestLoggingMiddleware
from nativespeaker.api.routers import (
              chats_router,
              examples_router,
              health_router,
              root_router,
)

logger = structlog.get_logger()

app = FastAPI(title="NativeSpeaker API Gateway",
              description="API Gateway for linguistic analysis of phrases",
              version=version("ns-api-gateway"),
              lifespan=lifespan,
              # D-04: the four auto-registered documentation routes are turned off. §2.1 pins the
              # public allowlist to exactly the readiness probe, so /docs, /redoc, /openapi.json
              # and /docs/oauth2-redirect would each be an undeclared registered route -- and an
              # unauthenticated schema dump. app.openapi() still works as a method call.
              docs_url=None,
              redoc_url=None,
              openapi_url=None,
              responses={
                  400: {"model": ErrorResponse, "description": "Invalid request"},
                  # D-11 retired the v1.3 `unauthorized` code; `auth_required` is the only 401.
                  401: {"model": ErrorResponse, "description": "Authentication required"},
                  404: {"model": ErrorResponse, "description": "Not found"},
                  405: {"model": ErrorResponse, "description": "Method not allowed"},
                  422: {"model": ErrorResponse, "description": "Validation error"},
                  429: {"model": ErrorResponse, "description": "Rate limited"},
                  500: {"model": ErrorResponse, "description": "Internal error"},
                  503: {"model": ErrorResponse, "description": "Service unavailable"},
              })

# A trailing-slash request would otherwise collect an unauthenticated 307 from a branch that runs
# after the barrier already passed through on "no FULL match". GET /chats/ now returns 404.
app.router.redirect_slashes = False

app.include_router(root_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
register_exception_handlers(app)
# D-03 wants RequestLoggingMiddleware outermost and the barrier beneath it. add_middleware inserts
# at index 0, so the call order here is the inverse of the reading order: the LAST call is outermost.
app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
# ty cannot match a BaseHTTPMiddleware subclass against Starlette's
# _MiddlewareFactory ParamSpec protocol; this is the documented usage.
app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]
