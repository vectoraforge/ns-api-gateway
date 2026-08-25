from importlib.metadata import version

from fastapi import APIRouter, Depends

from nativespeaker.api.app.dependencies import get_chat_service, get_linked_identity
from nativespeaker.api.auth.context import LinkedIdentity
from nativespeaker.api.services import ChatService

# Authentication is default-on for this router (D-07). The router-level declaration is what makes
# an endpoint added here later authenticated even if whoever adds it forgets the per-endpoint
# `Depends`, and the per-endpoint declaration below names the identical callable so FastAPI's
# per-request cache resolves both to one execution.
router = APIRouter(tags=["root"], dependencies=[Depends(get_linked_identity)])


@router.get("/",
            summary="API information",
            description="Returns API name, version, and supported languages.")
async def root(identity: LinkedIdentity = Depends(get_linked_identity),
               service: ChatService = Depends(get_chat_service)):
    return {
        "name": "NativeSpeaker API Gateway",
        "version": version("ns-api-gateway"),
        "supported_languages": service.supported_languages,
    }
