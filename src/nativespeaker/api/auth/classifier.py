"""Closed providerData classifier and email-copy rule. Never take the first recognized entry,
never classify non-empty providerData as anonymous, never read `firebase.sign_in_provider`.
There is no declaration match here and no `required_flow` anywhere."""
from nativespeaker.api.auth.adapters import ProviderDataEntry, ProviderDataOutcome, ProviderDataResult
from nativespeaker.api.models.identities import IdentityProvider

# Exactly two recognized provider ids. A third is a spec change: a new enum value and a migration.
_RECOGNIZED: dict[str, IdentityProvider] = {
    "google.com": IdentityProvider.google,
    "apple.com": IdentityProvider.apple,
}


def classify_provider_data(entries: tuple[ProviderDataEntry, ...]) -> tuple[IdentityProvider, str | None] | None:
    """Classify a providerData read. `None` rejects; `provider_uid` is `None` exactly for anonymous."""
    if not entries:
        return IdentityProvider.anonymous, None
    if len(entries) != 1:
        return None
    provider = _RECOGNIZED.get(entries[0].provider_id)
    if provider is None:
        return None
    if not entries[0].uid:
        return None
    return provider, entries[0].uid


def email_to_persist(result: ProviderDataResult) -> str | None:
    """Copy the address only from an `ok` result with a non-empty, verified value. Never normalized."""
    if result.outcome is not ProviderDataOutcome.ok:
        return None
    if result.email is None or not result.email.strip():
        return None
    if not result.email_verified:
        return None
    return result.email
