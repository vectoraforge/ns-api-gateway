"""The single Firebase integration: issuer-matched verification and Admin client selection."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from nativespeaker.api.auth.tokens import (
    IdTokenVerifier,
    InvalidExternalJwtError,
    JwtRejectionReason,
    VerifiedClaims,
)

# Firebase sign-in providers the pinned project is allowed to enable, and the closed
# `providerData` classifier that backstops any other shape.
PROVIDER_ID_TO_PROVIDER = {
    "google.com": "google",
    "apple.com": "apple",
}
ALLOWED_SIGN_IN_PROVIDERS = frozenset({"anonymous", "google", "apple"})


class FirebaseIntegrationConfigError(RuntimeError):
    """Startup configuration error: the integration set is not exactly one integration."""


class UnrecognizedProviderError(RuntimeError):
    """The Admin `providerData` shape is not one of the enabled sign-in providers."""


@dataclass(frozen=True, slots=True)
class FirebaseIntegration:
    """One configured Firebase project: its expected issuer, audience and Admin client."""
    issuer: str
    project_id: str
    verifier: IdTokenVerifier
    admin_client: Any


class FirebaseIntegrations:
    """Holds exactly one integration. There is no ambient, global or default Admin client:
    every Admin call selects its client here, by the backend-verified issuer."""

    # [impl->req~shared-single-firebase-integration~1]
    def __init__(self, integrations: Sequence[FirebaseIntegration]):
        if len(integrations) != 1:
            raise FirebaseIntegrationConfigError(
                f"exactly one Firebase integration is required, got {len(integrations)}")
        self._integration = integrations[0]

    @property
    def sole(self) -> FirebaseIntegration:
        return self._integration

    def verify_id_token(self, token: str) -> VerifiedClaims:
        """Verify against the sole integration. Issuer acceptance is equality against its issuer."""
        return self._integration.verifier.verify_id_token(token)

    def admin_client_for_issuer(self, issuer: str) -> Any:
        """Select the Admin client by matched issuer. A mismatch fails as an
        `invalid_external_jwt`/`issuer_mismatch` rejection before any Firebase Admin lookup;
        there is no fallback client."""
        if issuer != self._integration.issuer:
            raise InvalidExternalJwtError(JwtRejectionReason.issuer_mismatch)
        return self._integration.admin_client

    @staticmethod
    def classify_provider(provider_data: Sequence[Any]) -> str:
        """Closed backstop classifier over an Admin `providerData` response. No provider is
        accepted merely because it appeared in a successful Admin response."""
        provider_ids = [str(getattr(entry, "provider_id", None) or "") for entry in provider_data]
        recognized = {PROVIDER_ID_TO_PROVIDER[pid] for pid in provider_ids
                      if pid in PROVIDER_ID_TO_PROVIDER}
        if not provider_ids:
            return "anonymous"
        if len(recognized) != 1 or len(provider_ids) != len(recognized):
            raise UnrecognizedProviderError("unrecognized providerData shape")
        return recognized.pop()
