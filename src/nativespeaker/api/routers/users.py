from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.app.dependencies import get_current_user, get_db, get_identity_context
from nativespeaker.api.auth.barrier import VerifiedIdentityContext
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.sync import REGISTRATION_STATE_FIELD
from nativespeaker.api.auth.users_me import (
    ProfileRow,
    ReadOnlyUsersMeSession,
    users_me_response,
    users_me_state,
)
from nativespeaker.api.database import StorePurchaseTokensDB, UsageDB
from nativespeaker.api.database.usage import GrantsDB, current_period
from nativespeaker.api.models import User
from nativespeaker.api.models.api import UserProfileResponse

router = APIRouter(tags=["users"])

# What the profile reports when the user holds no effective access grant: no tier, no credits.
NO_TIER = "none"


@router.get("/users/me",
            response_model=UserProfileResponse,
            summary="Get current user profile",
            description="Returns the authenticated user's profile, subscription plan, and current month's usage.")
async def get_me(user: User = Depends(get_current_user),
                 context: VerifiedIdentityContext = Depends(get_identity_context),
                 db: AsyncSession = Depends(get_db)) -> UserProfileResponse:
    now = datetime.now(UTC)
    # Entitlement is the user's single effective access grant, and the numeric monthly limit is
    # its tier's — never a column on `core.users`.
    grant = await GrantsDB(db).effective_grant(user.id, now)
    if grant is None:
        tier_id, monthly_limit, requests_used = NO_TIER, 0, 0
    else:
        tier_id, monthly_limit = grant.tier_id, grant.monthly_credits
        requests_used = await UsageDB(db).get_usage(grant.grant_id, current_period(now))

    if now.month == 12:
        resets_at = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        resets_at = datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    # The endpoint's own two reads and its fixed response shape are decided by `auth.users_me`:
    # the profile fields, the stored registration state under the same `identity_provider` name
    # `POST /auth/sync` reports it under, and an entry for every store provider carrying that
    # store's persisted attribution token. Nothing here is conditioned on a client-supplied
    # signal, and no token is minted, rotated or replaced.
    # [impl->req~sessions-users-me-step-01~1]
    # [impl->req~sessions-users-me-step-02~1]
    # [impl->req~sessions-users-me-step-03~1]
    # [impl->req~sessions-api-users-me-fixed-response-shape~1]
    # [impl->req~sessions-api-users-me-purpose~1]
    session = ReadOnlyUsersMeSession(
        profile_row=ProfileRow(user_id=user.id, email=user.email,
                               display_name=user.display_name, created_at=user.created_at),
        store_tokens=await StorePurchaseTokensDB(db).tokens_for(user.id),
        # The stored `core.external_identities.provider` column the barrier already resolved.
        stored_provider=context.provider or IdentityProvider.anonymous)
    payload = users_me_response(users_me_state(context, session))

    return UserProfileResponse(email=user.email,
                               name=user.display_name,
                               subscription_plan=tier_id,
                               created_at=user.created_at,
                               requests_used=requests_used,
                               monthly_limit=monthly_limit,
                               resets_at=resets_at,
                               identity_provider=payload[REGISTRATION_STATE_FIELD],
                               store_purchase_tokens=payload["store_purchase_tokens"])
