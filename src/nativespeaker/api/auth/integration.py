"""The single Firebase integration: issuer-matched verification and Admin client selection."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nativespeaker.api.auth.tokens import (
    CachedGoogleSigningKeys,
    FirebaseIdTokenVerifier,
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


class AdminCallSite(StrEnum):
    """The Firebase Admin call sites, each with the integration-selection rule it follows."""
    provider_data_read = "provider_data_read"
    sign_out_all_revocation = "sign_out_all_revocation"
    operator_block_revocation = "operator_block_revocation"
    identity_retirement_revocation = "identity_retirement_revocation"


# Request-driven Admin work: every enumerated `providerData` read point and the refresh-token
# revocation `POST /auth/sign-out-all` performs. Each selects the integration by the issuer
# verified for the current request — the same issuer that passed external-JWT acceptance and keys
# the identity lookup.
REQUEST_DRIVEN_ADMIN_SITES: frozenset[AdminCallSite] = frozenset({
    AdminCallSite.provider_data_read,
    AdminCallSite.sign_out_all_revocation,
})

# Administrative Admin work: operator block and identity retirement, which also revoke refresh
# tokens. Each selects the integration by the `issuer` stored on the identity row being acted on.
ADMINISTRATIVE_ADMIN_SITES: frozenset[AdminCallSite] = frozenset({
    AdminCallSite.operator_block_revocation,
    AdminCallSite.identity_retirement_revocation,
})


class AdminSelectionSiteError(RuntimeError):
    """An Admin call site was selected under the wrong selection rule."""


@dataclass(frozen=True, slots=True)
class FirebaseIntegration:
    """One configured Firebase project: its expected issuer, audience and Admin client."""
    issuer: str
    project_id: str
    verifier: IdTokenVerifier
    admin_client: Any


class FirebaseIntegrations:
    """Holds exactly one integration. There is no ambient, global or default Admin client:
    every Admin call selects its client here, by the backend-verified issuer.

    Configuration carries exactly one Firebase integration record, held as this single unit: the
    expected token `iss`, the project audience that pins JWT acceptance, and the Admin
    credentials and app for that same project. Multiple concurrent Firebase projects are out of
    scope, and the later per-issuer map of token pinning plus Admin client is deliberately not
    built here."""

    # [impl->req~shared-single-firebase-integration~1]
    # [impl->req~sessions-single-firebase-integration-record~1]
    def __init__(self, integrations: Sequence[FirebaseIntegration]):
        if len(integrations) != 1:
            raise FirebaseIntegrationConfigError(
                f"exactly one Firebase integration is required, got {len(integrations)}")
        self._integration = integrations[0]

    @property
    def sole(self) -> FirebaseIntegration:
        return self._integration

    @property
    def configured_issuer(self) -> str:
        """The one configured integration's issuer. Because exactly one integration exists, a
        stored `issuer` always equals this value, and identity lookup stays keyed on
        `(issuer, subject)` with no additional ownership key."""
        # [impl->req~sessions-stored-issuer-equals-configured~1]
        return self._integration.issuer

    def verify_id_token(self, token: str) -> VerifiedClaims:
        """Verify against the sole integration. Issuer acceptance is equality against its issuer."""
        return self._integration.verifier.verify_id_token(token)

    def admin_client_for_issuer(self, issuer: str) -> Any:
        """Select the Admin client by matched issuer. A mismatch fails as an
        `invalid_external_jwt`/`issuer_mismatch` rejection before any Firebase Admin lookup;
        there is no fallback client.

        Selection is by issuer equality and by nothing else: this is the only selector, it takes
        no `subject`, no provider and no client-supplied value, and it never falls back to
        another project or to a default Admin client."""
        # [impl->req~sessions-admin-client-by-issuer-match~1]
        # [impl->req~sessions-integration-selection-fails-closed~1]
        if issuer != self._integration.issuer:
            raise InvalidExternalJwtError(JwtRejectionReason.issuer_mismatch)
        return self._integration.admin_client

    def admin_client_for_request(self, *, verified_issuer: str, site: AdminCallSite) -> Any:
        """Request-driven Admin work — every enumerated `providerData` read point and the
        `POST /auth/sign-out-all` refresh-token revocation — selects the integration by the issuer
        verified for the current request."""
        # [impl->req~sessions-integration-select-request-driven~1]
        if site not in REQUEST_DRIVEN_ADMIN_SITES:
            raise AdminSelectionSiteError(f"{site} is not a request-driven Admin call site")
        return self.admin_client_for_issuer(verified_issuer)

    def admin_client_for_stored_issuer(self, *, stored_issuer: str, site: AdminCallSite) -> Any:
        """Operator block and identity retirement select the integration by the `issuer` stored on
        the `core.external_identities` row being acted on; the row already stores `issuer` beside
        `subject`, so no schema change is needed. A stored issuer that no longer matches the
        configured one is a hard error here, never a revocation against another project."""
        # [impl->req~sessions-integration-select-administrative~1]
        # [impl->req~sessions-integration-selection-fails-closed~1]
        # [impl->req~sessions-stored-issuer-equals-configured~1]
        if site not in ADMINISTRATIVE_ADMIN_SITES:
            raise AdminSelectionSiteError(f"{site} is not an administrative Admin call site")
        return self.admin_client_for_issuer(stored_issuer)

    @staticmethod
    def classify_provider(provider_data: Sequence[Any]) -> str:
        """Closed backstop classifier over an Admin `providerData` response. No provider is
        accepted merely because it appeared in a successful Admin response.

        A `providerData` response is the only input: `provider` and the anonymous-versus-
        registered classification are never derived from a header, a token claim, client input
        or an optional untrusted profile field.

        That no other provider kind — password, phone, SAML, OIDC or custom auth — reaches this
        classifier is guaranteed by the pinned Firebase project, which enables only the three
        sign-in providers below. No further shape-refusal machinery is added: the rejection of any
        unrecognized shape here is the only backstop."""
        # [impl->req~sessions-provider-only-from-providerdata~1]
        # [impl->req~sessions-classifier-closed-mapping~1]
        # [impl->req~sessions-pinned-project-bounds-provider-kinds~1]
        provider_ids = [str(getattr(entry, "provider_id", None) or "") for entry in provider_data]
        recognized = {PROVIDER_ID_TO_PROVIDER[pid] for pid in provider_ids
                      if pid in PROVIDER_ID_TO_PROVIDER}
        # No entries classifies as `anonymous`, and a non-empty result never does.
        # [impl->req~sessions-classify-no-entries-anonymous~1]
        if not provider_ids:
            return "anonymous"
        # Exactly one entry, `google.com`, classifies as `google`; exactly one entry,
        # `apple.com`, classifies as `apple`. Entries for both providers, several entries, and any
        # entry that is neither recognized value all reject with no persistence — the first
        # recognized entry is never taken and additional entries are never discarded.
        # [impl->req~sessions-classify-google~1]
        # [impl->req~sessions-classify-apple~1]
        # [impl->req~sessions-classify-both-providers-reject~1]
        # [impl->req~sessions-classify-other-shape-reject~1]
        # [impl->req~sessions-classifier-no-first-entry-shortcut~1]
        if len(recognized) != 1 or len(provider_ids) != len(recognized):
            raise UnrecognizedProviderError("unrecognized providerData shape")
        return recognized.pop()


def build_firebase_integrations(*,
                                issuer: str,
                                project_id: str,
                                jwks_url: str,
                                admin_client: Any,
                                leeway: int = 30,
                                jwks_cache_ttl_seconds: float = 3600.0,
                                warm: bool = True) -> FirebaseIntegrations:
    """The one configured Firebase integration: its expected issuer, its project ID as the
    accepted audience, a JWKS-backed verifier over the cached Google signing keys, and the
    named Admin client every Admin call for that issuer selects. There is no default client.

    One configured Firebase project pins both values, so the project, the issuer and the
    audience the backend accepts cannot drift apart, and the gateway's `jwt_authn` filter has a
    single source of truth to be configured against."""
    # [impl->req~shared-single-firebase-integration~1]
    # [impl->req~sessions-gateway-backend-same-project-pin~1]
    keys = CachedGoogleSigningKeys(jwks_url=jwks_url, cache_ttl_seconds=jwks_cache_ttl_seconds)
    if warm:
        keys.warm()
    verifier = FirebaseIdTokenVerifier(issuer=issuer, audience=project_id,
                                       key_resolver=keys, leeway=leeway)
    return FirebaseIntegrations([FirebaseIntegration(issuer=issuer,
                                                     project_id=project_id,
                                                     verifier=verifier,
                                                     admin_client=admin_client)])
