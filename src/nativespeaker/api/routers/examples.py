from fastapi import APIRouter, Depends, Query

from nativespeaker.api.app.dependencies import get_chat_service, get_linked_identity
from nativespeaker.api.auth.context import LinkedIdentity
from nativespeaker.api.models.api import ExamplesResponse
from nativespeaker.api.services import ChatService

# Authentication is default-on for this router; see `root.py` for why both levels declare it.
router = APIRouter(tags=["examples"], dependencies=[Depends(get_linked_identity)])


@router.get("/examples",
            response_model=ExamplesResponse,
            summary="Get example phrases",
            description="Returns example phrases for a given language to help users get started.")
async def get_examples(lang: str = Query(..., description="Language code (e.g., 'en', 'es')"),
                       identity: LinkedIdentity = Depends(get_linked_identity),
                       service: ChatService = Depends(get_chat_service)) -> ExamplesResponse:
    return service.get_examples(lang)
