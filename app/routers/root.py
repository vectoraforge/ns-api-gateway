from importlib.metadata import version

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def root(request: Request):
    return {
        "name": "SpeakNative API Gateway",
        "version": version("sn-api-gateway"),
        "supported_languages": request.app.state.service.supported_languages,
    }
