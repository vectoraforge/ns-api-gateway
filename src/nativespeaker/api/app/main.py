from importlib.metadata import version

import structlog
from fastapi import FastAPI

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.app.lifespan import lifespan
from nativespeaker.api.errors import ErrorResponse
from nativespeaker.api.logs import RequestLoggingMiddleware
from nativespeaker.api.routers import (
              auth_router,
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
              # and /docs/oauth2-redirect would each be an unauthenticated schema dump.
              #
              # **This matters more under 37.1 D-07, not less.** Authentication is now a
              # router-level dependency, and FastAPI registers the documentation routes on
              # `app.router` directly -- they belong to no `APIRouter` and would therefore carry no
              # dependency at all. Turning any of these back on makes it genuinely public.
              # app.openapi() still works as a method call.
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

# A trailing-slash redirect is a response produced by the router itself, before any route matches
# and therefore before any route's dependencies run -- so `GET /chats/` would collect an
# unauthenticated 307 naming a real path. It returns 404 instead.
app.router.redirect_slashes = False

# Each router carries its own authentication declaration (D-07): `root`, `examples` and `chats`
# declare `Depends(get_linked_identity)`, `auth` declares `Depends(get_request_context)`, and
# `health` deliberately declares nothing -- the readiness probe is the whole public allowlist.
app.include_router(root_router)
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(examples_router)
app.include_router(health_router)
register_exception_handlers(app)
# ty cannot match a BaseHTTPMiddleware subclass against Starlette's
# _MiddlewareFactory ParamSpec protocol; this is the documented usage.
app.add_middleware(RequestLoggingMiddleware)  # ty: ignore[invalid-argument-type]
