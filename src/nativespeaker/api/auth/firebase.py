"""The Firebase Admin integration: one named app per issuer, and one adapter method, never a [DEFAULT] app.

It also holds the two things that exist only to serve that lookup: the closed providerData classifier
with its email-copy rule, both applied inside the read itself, and the one retry policy -- three
attempts, then the unavailable rejection.

Never take the first recognized entry, never classify non-empty providerData as anonymous,
never read `firebase.sign_in_provider`. There is no declaration match here and no `required_flow` anywhere."""
from typing import NoReturn

import firebase_admin
import google.auth
import google.auth.exceptions
import structlog
from firebase_admin import auth, credentials, exceptions
from starlette.concurrency import run_in_threadpool
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt

from nativespeaker.api.auth.adapters import VerifiedProviderIdentity
from nativespeaker.api.errors import NotLinked, Unavailable, UserNotFound
from nativespeaker.api.tables.identities import IdentityProvider

logger = structlog.get_logger()

# An app-level option because the SDK exposes no per-call timeout: every call through the app inherits it.
FIREBASE_HTTP_TIMEOUT_SECONDS = 8

# The whole budget for one lookup: the initial call plus up to two more, spent on retryable outcomes only.
FIREBASE_LOOKUP_ATTEMPTS = 3


class RetryableLookupError(Exception):
    """The retry predicate's only target, always converted before it can escape."""


def build_admin_apps(config) -> dict[str, firebase_admin.App]:
    """One named Admin app per configured issuer, built once at boot. Never a `[DEFAULT]` one."""
    # ADC if the environment supplies it, else no app at all -- a supported state that boots
    credential = _application_default_credential()
    if credential is None:
        logger.warning("firebase_admin_credential_absent",
                       consequence="user creation fails closed as verification_temporarily_unavailable "
                                   "until Application Default Credentials are available in this environment")
        return {}
    # Explicit projectId and name, never inferred: with no [DEFAULT] app a forgotten app= fails loudly.
    app = firebase_admin.initialize_app(
        credential,
        {"projectId": config.jwt.project_id, "httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS},
        name=f"issuer:{config.jwt.issuer}",
    )
    return {config.jwt.issuer: app}


def _application_default_credential() -> credentials.ApplicationDefault | None:
    """ADC if the environment supplies it, `None` if it does not -- never a raise."""
    # Nothing configured is the ordinary case, not an error, and probing at boot avoids a late 503.
    try:
        google.auth.default()
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    logger.info("firebase_admin_using_application_default_credentials")
    return credentials.ApplicationDefault()


class FirebaseAdminLookup:
    """The `getUser` providerData read, and nothing else: token verification and revocation live elsewhere."""

    def __init__(self, apps: dict[str, firebase_admin.App]) -> None:
        self._apps = apps

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        """Read `subject`'s providerData through the app `issuer` selects: the identity, or a raise."""
        app = self._apps.get(issuer)
        if app is None:
            # Fails closed with no call made: there is no ambient app to fall back to, by design.
            raise Unavailable(stage="issuer_selection")
        # `firebase-admin` is built on `requests` and has no async client, so it runs off the loop.
        return await run_in_threadpool(self._read, app, subject)

    @staticmethod
    def _read(app: firebase_admin.App, subject: str) -> VerifiedProviderIdentity:
        """The synchronous body, run off the event loop. Everything that can raise happens here."""
        try:
            record = auth.get_user(subject, app=app)
            # A lazy property that raises on an empty rawId, so it is materialized inside this try.
            entries = tuple((entry.provider_id, entry.uid) for entry in record.provider_data)
            email = record.email  # read here so every field comes off this one getUser response
            email_verified = record.email_verified
        except auth.UserNotFoundError:
            # Definitive, spends no retry budget, and listed before the FirebaseError it subclasses.
            logger.info("firebase_get_user_not_found")
            raise UserNotFound(stage="provider_lookup") from None
        except ValueError as error:
            # A malformed or indeterminate response, which is retryable rather than definitive.
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            raise RetryableLookupError(str(error)) from error
        except google.auth.exceptions.GoogleAuthError as error:
            # Not a FirebaseError and raised before the request is sent; unhandled it means 500, not 503.
            logger.warning("firebase_credential_unavailable", detail=str(error))
            raise RetryableLookupError(str(error)) from error
        except exceptions.FirebaseError as error:
            # Outage or integration-auth failure; the provider's text is for the log, never a body.
            logger.warning("firebase_get_user_failed", code=error.code, detail=str(error))
            raise RetryableLookupError(str(error)) from error
        provider, provider_uid = _resolve_provider(entries)
        return VerifiedProviderIdentity(provider=provider,
                                        provider_uid=provider_uid,
                                        email=_verified_email(email, email_verified))


# Exactly two recognized provider ids. A third is a spec change: a new enum value and a migration.
_RECOGNIZED: dict[str, IdentityProvider] = {
    "google.com": IdentityProvider.google,
    "apple.com": IdentityProvider.apple,
}


def _resolve_provider(entries: tuple[tuple[str, str], ...]) -> tuple[IdentityProvider, str | None]:
    """Classify a providerData read. `provider_uid` is `None` exactly for anonymous; anything else rejects."""
    if not entries:
        return IdentityProvider.anonymous, None
    if len(entries) != 1:
        raise NotLinked(stage="provider_classification", cause="invalid-shape")
    provider_id, uid = entries[0]
    provider = _RECOGNIZED.get(provider_id)
    if provider is None:
        raise NotLinked(stage="provider_classification", cause="invalid-shape")
    if not uid:
        raise NotLinked(stage="provider_classification", cause="invalid-shape")
    return provider, uid


def _verified_email(email: str | None, email_verified: bool) -> str | None:
    """Copy the address only when it is both non-empty and verified. Never normalized.

    Evaluated in exactly one place, and `create_account` re-derives nothing from it.
    """
    if email is None or not email.strip():
        return None
    if not email_verified:
        return None
    return email


def _exhausted(retry_state) -> NoReturn:
    """Convert an exhausted budget into the rejection the client is owed.

    Without this, tenacity's default raises `RetryError`, which matches no handler and so answers a
    hard 500 where the caller is owed a retryable 503. `reraise=True` would not do either: it would
    surface `RetryableLookupError`, which is internal and declares no status or code.
    """
    raise Unavailable(stage="provider_lookup") from retry_state.outcome.exception()


async def lookup_with_retry(adapter, issuer: str, subject: str) -> VerifiedProviderIdentity:
    """Call the adapter up to `FIREBASE_LOOKUP_ATTEMPTS` times; return the identity or raise."""
    retrying = AsyncRetrying(
        stop=stop_after_attempt(FIREBASE_LOOKUP_ATTEMPTS),
        # Only the internal marker is retryable, so `UserNotFound` and `NotLinked` propagate after
        # one attempt rather than spending a budget on a fact the provider already stated.
        retry=retry_if_exception_type(RetryableLookupError),
        retry_error_callback=_exhausted,
    )
    return await retrying(adapter.get_user_provider_data, issuer, subject)
