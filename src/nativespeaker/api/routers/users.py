from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from nativespeaker.api.app.dependencies import get_current_user, get_db
from nativespeaker.api.database import UsageDB
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

    return UserProfileResponse(email=user.email,
                               name=user.display_name,
                               subscription_plan=tier_id,
                               created_at=user.created_at,
                               requests_used=requests_used,
                               monthly_limit=monthly_limit,
                               resets_at=resets_at)
