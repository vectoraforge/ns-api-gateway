from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.schema import UserProfileResponse
from app.models import User

router = APIRouter()


@router.get("/users/me", response_model=UserProfileResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserProfileResponse:
    return UserProfileResponse(email=user.email,
                               name=user.name,
                               plan=user.plan,
                               created_at=user.created_at)
