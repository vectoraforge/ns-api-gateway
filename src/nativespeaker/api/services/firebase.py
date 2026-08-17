import asyncio

import structlog
from firebase_admin import auth

from nativespeaker.api.auth.integration import FirebaseIntegrations
from nativespeaker.api.models import SubscriptionPlan

logger = structlog.get_logger()


class FirebaseService:
    """Firebase Admin work for the one configured integration.

    Every Admin call selects its client through the integration, by the backend-verified
    issuer. There is no ambient, global or default Admin app to fall back to.
    """

    # [impl->req~shared-single-firebase-integration~1]
    def __init__(self, *, integrations: FirebaseIntegrations, issuer: str):
        self._integrations = integrations
        self._issuer = issuer

    async def set_plan_claim(self, firebase_uid: str, plan: SubscriptionPlan) -> None:
        """Sync plan tier to Firebase custom claims. Best-effort -- logs on failure."""
        try:
            admin_app = self._integrations.admin_client_for_issuer(self._issuer)
            await asyncio.to_thread(
                auth.set_custom_user_claims, firebase_uid, {"plan": plan}, app=admin_app
            )
        except Exception:
            logger.warning("firebase_claim_sync_failed",
                           firebase_uid=firebase_uid, plan=plan)
