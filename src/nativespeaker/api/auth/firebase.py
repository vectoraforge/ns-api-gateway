"""The Firebase Admin integration: one named app per issuer, and one adapter method, never a [DEFAULT] app."""
import firebase_admin
import google.auth
import google.auth.exceptions
import structlog
from firebase_admin import auth, credentials, exceptions
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)

logger = structlog.get_logger()

# An app-level option because the SDK exposes no per-call timeout: every call through the app inherits it.
FIREBASE_HTTP_TIMEOUT_SECONDS = 8


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

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        """Read `subject`'s providerData through the app `issuer` selects; returns a result, never raises."""
        app = self._apps.get(issuer)
        if app is None:
            return ProviderDataResult(ProviderDataOutcome.selection_failure)
        # `firebase-admin` is built on `requests` and has no async client, so it runs off the loop.
        return await run_in_threadpool(self._read, app, subject)

    @staticmethod
    def _read(app: firebase_admin.App, subject: str) -> ProviderDataResult:
        """The synchronous body, run off the event loop. Everything that can raise happens here."""
        try:
            record = auth.get_user(subject, app=app)
            # A lazy property that raises on an empty rawId, so it is materialized inside this try.
            entries = tuple(ProviderDataEntry(provider_id=entry.provider_id, uid=entry.uid)
                            for entry in record.provider_data)
            email = record.email  # read here so every field comes off this one getUser response
            email_verified = record.email_verified
        except auth.UserNotFoundError:
            # Definitive, spends no retry budget, and listed before the FirebaseError it subclasses.
            logger.info("firebase_get_user_not_found")
            return ProviderDataResult(ProviderDataOutcome.user_not_found)
        except ValueError as error:
            # A malformed or indeterminate response, which is retryable rather than definitive.
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except google.auth.exceptions.GoogleAuthError as error:
            # Not a FirebaseError and raised before the request is sent; unhandled it means 500, not 503.
            logger.warning("firebase_credential_unavailable", detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except exceptions.FirebaseError as error:
            # Outage or integration-auth failure; the provider's text is for the log, never a body.
            logger.warning("firebase_get_user_failed", code=error.code, detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        return ProviderDataResult(ProviderDataOutcome.ok, entries,
                                  email=email, email_verified=email_verified)
