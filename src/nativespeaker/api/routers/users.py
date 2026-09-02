"""The one user route: `/users/me` reports the caller's own profile, provider and store tokens."""
from fastapi import APIRouter, Depends
from starlette.responses import Response

from nativespeaker.api.app.dependencies import get_linked_identity, get_purchases_db
from nativespeaker.api.crud.purchases import PurchasesDB
from nativespeaker.api.schemas.auth import Identity, MeResponse, Profile

# Router-level auth protects an endpoint added later whose own Depends is forgotten; the same callable runs once.
router = APIRouter(tags=["users"], dependencies=[Depends(get_linked_identity)])


@router.get("/users/me",
            response_model=MeResponse,
            summary="Report the caller's own profile, registration state and store tokens",
            description="Reads the caller's profile fields and its purchase-attribution token per "
                        "store. Nothing is written.")
async def me(response: Response,
             identity: Identity = Depends(get_linked_identity),
             purchases: PurchasesDB = Depends(get_purchases_db)) -> MeResponse:
    """Report what the caller's own account holds at this request's instant."""
    purchase_tokens = await purchases.read_tokens(identity.user.id)
    # `no-store` rather than `no-cache`: the tokens are secrets, and a revalidatable copy is a copy.
    response.headers["Cache-Control"] = "no-store"
    return MeResponse(profile=Profile(email=identity.user.email,
                                      display_name=identity.user.display_name),
                      identity_provider=identity.identity.provider,
                      purchase_tokens=purchase_tokens)
