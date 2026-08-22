"""§7.1's concrete issuer-selected Firebase Admin integration -- the codebase's first adapter.

Lives **outside** `auth/adapters.py` on purpose: that module declares the seams and implements
nothing, and `tests/unit/test_adapter_interfaces.py` fails the moment an implementation appears
there. This module is the implementation, and it is named in that file's `ADAPTER_IMPLEMENTORS`
allow-list for `get_user_provider_data` and for no other adapter method.

**No `[DEFAULT]` app is ever created.** Calling `firebase_admin.initialize_app` with no credential
argument falls back to Application Default Credentials, which in local development silently picks
up the developer's own gcloud identity -- and SHARED-INVARIANTS' wire contract is explicit that "no
ambient, default, global, or fallback client exists" (D-08). Every call below passes an explicit
`credentials.Certificate` and a `name=`, and every `get_user` passes `app=`. Not creating a
`[DEFAULT]` app at all is what makes a call site that forgets `app=` fail loudly instead of quietly
reading some other project's users (T-37-14).

**Selection is an exact dict lookup on the request-verified issuer, and a miss fails closed.** It
never falls back to "the app we do have": that would be answering a question about one Firebase
project with another project's data (T-37-19).

**One method, not three.** `FirebaseAdminAdapter` declares three; this class implements only
`get_user_provider_data`, and the two omissions are decisions rather than gaps:

* **The token-verification method is not implemented.** The barrier's JWKS-backed `TokenVerifier`
  (`auth/verification.py`) is the service's only verification path and §02's hardenings forbid a
  handler re-implementing verification, so an implementation here would be unreachable structure --
  exactly what D-03 refuses.
* **The refresh-token revocation method is not implemented.** §7.1 assigns the revocation adapter,
  its retry budget and any in-flight coalescing to the sign-out-all phase (Phase 46); building it
  here would be building another phase's adapter. **Phase 46 note:** adding it to this module means
  widening this module's one-method `ADAPTER_IMPLEMENTORS` entry in
  `tests/unit/test_adapter_interfaces.py` deliberately -- the src-wide scan reports it first, which
  is the point. `tests/unit/test_firebase_adapter.py` pins both absences by name; that scan reads
  only `src/`, so the two identifiers are spelled there rather than here.

The Protocol is structural and not `@runtime_checkable`, so nothing breaks at runtime; this class
is deliberately not annotated as `FirebaseAdminAdapter` anywhere, because it does not satisfy the
whole Protocol and must not claim to.
"""
import firebase_admin
import structlog
from firebase_admin import auth, credentials, exceptions
from starlette.concurrency import run_in_threadpool

from nativespeaker.api.auth.adapters import (
    ProviderDataEntry,
    ProviderDataOutcome,
    ProviderDataResult,
)

logger = structlog.get_logger()

# §7's preamble: "every outbound call carries a fixed configured per-attempt timeout on the order of
# 5-10 seconds" (`adapters.py:16-17`). `httpTimeout` is an **app-level** option because this SDK
# exposes no per-call timeout knob -- it is set once, here, and every call through the app inherits
# it. RESEARCH A5: the option's application to `get_user` is documented but not separately measured;
# a slow test is the detector.
FIREBASE_HTTP_TIMEOUT_SECONDS = 8


def build_admin_apps(config) -> dict[str, firebase_admin.App]:
    """One named Admin app per configured issuer, built once at boot. Never a `[DEFAULT]` one.

    Returns `{}` when no service-account credential is configured. That is a **supported** state
    (37-03's `FirebaseConfig`): the service boots, prepare mode and every substituted-adapter path
    runs unaffected, and a real completion fails closed at the selection arm below --
    `selection_failure`, which §7.1 maps to `verification_temporarily_unavailable`. The credential
    was already parsed and validated once at configuration load, so this reads the parsed dict
    rather than re-parsing a secret.
    """
    credential_dict = config.firebase.credential_dict()
    if credential_dict is None:
        logger.warning("firebase_admin_credential_absent",
                       consequence="user creation fails closed as verification_temporarily_unavailable "
                                   "until FIREBASE_SERVICE_ACCOUNT_JSON is set")
        return {}
    app = firebase_admin.initialize_app(
        credentials.Certificate(credential_dict),
        {"projectId": config.jwt.project_id, "httpTimeout": FIREBASE_HTTP_TIMEOUT_SECONDS},
        name=f"issuer:{config.jwt.issuer}",
    )
    return {config.jwt.issuer: app}


class FirebaseAdminLookup:
    """The §7.1 `getUser` providerData read, and nothing else. See the module docstring for why."""

    def __init__(self, apps: dict[str, firebase_admin.App]) -> None:
        self._apps = apps

    async def get_user_provider_data(self, issuer: str, subject: str) -> ProviderDataResult:
        """Read `subject`'s providerData through the app `issuer` selects. Never raises.

        Returns a closed `ProviderDataResult` under every outcome, which is what lets
        `auth/retry.py`'s result-based policy count attempts. An issuer with no configured app
        returns `selection_failure` **before** any call.
        """
        app = self._apps.get(issuer)
        if app is None:
            return ProviderDataResult(ProviderDataOutcome.selection_failure)
        # 35-12's house rule: any synchronous call on the request path that can perform I/O is
        # awaited through `run_in_threadpool`, never called inline. `firebase-admin` is built on
        # `requests` and has no async auth client (D-07).
        return await run_in_threadpool(self._read, app, subject)

    @staticmethod
    def _read(app: firebase_admin.App, subject: str) -> ProviderDataResult:
        """The synchronous body, run off the event loop. Everything that can raise happens here.

        `record.provider_data` is a **lazy property**: it constructs `ProviderUserInfo` per entry,
        and that constructor raises `ValueError('User ID must not be None or empty.')` on an empty
        `rawId`. Materializing it inside this `try` is load-bearing -- touched after the threadpool
        call returns, the exception escapes the retry policy entirely and becomes an unhandled 500
        (T-37-17).

        `record.email` and `record.email_verified` are plain dict reads that cannot raise the way
        `provider_data` can, but they are read **here** regardless: §02 step 10 pins the copy to
        "the same successful `getUser` response", and a field read after the threadpool returns --
        or worse, on a second lookup -- is a different response. The copy *rule* is not evaluated
        here; the adapter reports what the provider said and `classifier.email_to_persist` judges
        it, so there are never two sites that can disagree.
        """
        try:
            record = auth.get_user(subject, app=app)
            entries = tuple(ProviderDataEntry(provider_id=entry.provider_id, uid=entry.uid)
                            for entry in record.provider_data)
            email = record.email
            email_verified = record.email_verified
        except auth.UserNotFoundError:
            # Definitive and non-retryable: it spends no retry budget (`adapters.py:52-54`) and
            # maps to `firebase_user_unresolved` -> `auth_required`. Listed before the
            # `FirebaseError` arm below, which it subclasses -- reordered, it would misclassify.
            logger.info("firebase_get_user_not_found")
            return ProviderDataResult(ProviderDataOutcome.user_not_found)
        except ValueError as error:
            # A malformed or indeterminate response -- §02 step 8 classifies that as retryable.
            logger.warning("firebase_provider_data_malformed", detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        except exceptions.FirebaseError as error:
            # Outage or integration-auth failure. The provider's text is diagnostic material for
            # the log and never for the response body (`adapters.py:19-20`, T-37-16) -- which is
            # why it is logged here and why the returned result has nowhere to carry it.
            logger.warning("firebase_get_user_failed", code=error.code, detail=str(error))
            return ProviderDataResult(ProviderDataOutcome.retryable_failure)
        return ProviderDataResult(ProviderDataOutcome.ok, entries,
                                  email=email, email_verified=email_verified)
