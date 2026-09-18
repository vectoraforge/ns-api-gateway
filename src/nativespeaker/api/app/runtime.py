from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from nativespeaker.api.auth.app_store import AppStoreNotifications
from nativespeaker.api.auth.devicecheck import AppleDeviceCheck
from nativespeaker.api.auth.firebase import FirebaseAdminLookup
from nativespeaker.api.auth.google_play import GooglePlayNotifications
from nativespeaker.api.auth.jwt_verifier import JWTVerifier
from nativespeaker.api.config import AppConfig
from nativespeaker.api.services import LLMService


@dataclass(frozen=True, slots=True)
class Runtime:
    """The eight objects the lifespan built, in the order it builds them.
    No field has a default: boot produced all eight or the pod did not start."""

    config: AppConfig
    session_factory: async_sessionmaker[SQLModelAsyncSession]
    jwt_verifier: JWTVerifier
    firebase_adapter: FirebaseAdminLookup
    devicecheck_adapter: AppleDeviceCheck
    app_store_notifications: AppStoreNotifications
    google_play_notifications: GooglePlayNotifications
    llm_service: LLMService
