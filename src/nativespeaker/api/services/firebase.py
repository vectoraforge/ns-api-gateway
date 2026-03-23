import asyncio

import structlog
from firebase_admin import auth

from nativespeaker.api.models import SubscriptionPlan

logger = structlog.get_logger()


class FirebaseService:

    async def set_plan_claim(self, firebase_uid: str, plan: SubscriptionPlan) -> None:
        """Sync plan tier to Firebase custom claims. Best-effort -- logs on failure."""
        try:
            await asyncio.to_thread(
                auth.set_custom_user_claims, firebase_uid, {"plan": plan}
            )
        except Exception:
            logger.warning("firebase_claim_sync_failed",
                           firebase_uid=firebase_uid, plan=plan)
