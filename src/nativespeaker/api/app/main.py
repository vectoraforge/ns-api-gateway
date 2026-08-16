from importlib.metadata import version

import structlog
from fastapi import FastAPI

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.app.lifespan import lifespan
from nativespeaker.api.logs import RequestLoggingMiddleware
from nativespeaker.api.models.api import ErrorResponse
from nativespeaker.api.routers import (
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
app.include_router(webhooks_router)
register_exception_handlers(app)
app.add_middleware(RequestLoggingMiddleware)
