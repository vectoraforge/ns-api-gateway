from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nativespeaker.api.app.dependencies import get_config, get_current_user, get_db
from nativespeaker.api.config import AppConfig
from nativespeaker.api.schema import UserProfileResponse
from nativespeaker.api.database import UsageDB
from nativespeaker.api.models import User

router = APIRouter()


@router.get("/users/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db),
                 config: AppConfig = Depends(get_config)) -> UserProfileResponse:
    usage_db = UsageDB(db)
    month = datetime.now(UTC).strftime("%Y-%m")
    requests_used = await usage_db.get_usage(user.id, month)
    monthly_limit = config.quotas[user.subscription_plan]

    now = datetime.now(UTC)
    if now.month == 12:
        resets_at = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        resets_at = datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    return UserProfileResponse(email=user.email,
                               name=user.name,
                               subscription_plan=user.subscription_plan,
                               created_at=user.created_at,
                               requests_used=requests_used,
                               monthly_limit=monthly_limit,
                               resets_at=resets_at)
