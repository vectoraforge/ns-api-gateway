# Phase 44: POST /webhooks/google-play/rtdn - Pattern Map

**Mapped:** 2026-09-05
**Files analyzed:** 23 new/modified
**Analogs found:** 22 / 23

Every analog below is git-tracked source in `ns-api-gateway`, verified with `git ls-files`.
Line numbers are as of commit `64b3b1a`.

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/auth/google_play.py` | NEW | adapter (external-SDK seam) | request-response | `src/nativespeaker/api/auth/devicecheck.py` + `auth/app_store.py` | role-match (two analogs; see below) |
| `src/nativespeaker/api/auth/store_notifications.py` | NEW | schema (value type) | transform | `src/nativespeaker/api/auth/app_store.py:15-31` | exact (a pure move) |
| `src/nativespeaker/api/auth/app_store.py` | edit | adapter | transform | itself + `auth/devicecheck.py:26-27,89-96` (module-level map + classify helper) | exact |
| `src/nativespeaker/api/auth/jwt_verifier.py` | edit | adapter | transform | itself, `:70-75` and `:139-167` | exact |
| `src/nativespeaker/api/app/dependencies.py` | edit | dependency | request-response | `dependencies.py:145-149` (sync analog) + `:45-62` (async/threadpool analog) | exact |
| `src/nativespeaker/api/app/lifespan.py` | edit | config/wiring | batch (boot) | `lifespan.py:33-45` and `:75-83`; `auth/firebase.py:48-55` | exact |
| `src/nativespeaker/api/config.py` | edit | config | transform | `config.py:71-98` (`AppStoreConfig`) | exact |
| `src/nativespeaker/api/routers/webhooks.py` | edit | route/handler | request-response | `routers/webhooks.py:17-29` | exact |
| `src/nativespeaker/api/schemas/webhooks.py` | edit | schema | request-response | `schemas/webhooks.py:5-8` | exact |
| `src/nativespeaker/api/services/subscriptions.py` | edit | service | CRUD | itself, `:17-33`, `:81-96`, `:108` | exact |
| `pyproject.toml` | edit | config | — | its own `dependencies` list (`httpx`, `PyJWT[crypto]`, `firebase-admin`) | exact |
| `config/config.yaml` | edit | config | — | the `app_store: products:` block at the file's end | exact |
| `.env.example` | edit | config | — | `.env.example:83-110` (the `APP_STORE_*` block) | exact |
| `k8s/templates/httproute-webhooks.yaml` | edit | config (gateway) | request-response | itself, `:12-20` | exact |
| `tests/unit/test_app_wiring.py` | edit | test (unit) | — | itself, `:18`, `:83-109` | exact |
| `tests/unit/test_google_play_notifications.py` | NEW | test (unit) | — | `tests/unit/test_jwks_offload.py:26-62` (JWKS harness) + `tests/unit/test_app_store_notifications.py` (shape) | role-match |
| `tests/unit/test_app_store_notifications.py` | edit | test (unit) | — | itself | exact |
| `tests/unit/test_config.py` | edit | test (unit) | — | `test_config.py:245-264` | exact |
| `tests/unit/test_auth_package_shape.py` | edit | test (unit) | — | itself, `:13` | exact |
| `tests/unit/test_subscription_attribution.py` | edit | test (unit) | — | itself (`VerifiedNotification(...)` keyword construction) | exact |
| `tests/e2e/conftest.py` | edit | test fixture | — | `tests/e2e/conftest.py:267-307` | exact |
| `tests/e2e/test_google_play_webhook.py` | NEW | test (e2e) | — | `tests/e2e/test_app_store_webhook.py` | exact |
| `tests/schema/test_subscription_ingestion.py` | edit | test (schema) | — | itself, `:36-56` | exact |

**No analog found:** the Play Developer API response model inside `auth/google_play.py`. This
repository has no Pydantic model of a vendor JSON response anywhere — `auth/devicecheck.py:98-110`
reads Apple's body as a plain `dict` and never models it. RESEARCH § F-09 is the field list; use
it. Everything else on the list has a real analog.

---

## Pattern Assignments

### `src/nativespeaker/api/auth/store_notifications.py` (NEW — value type)

**Analog:** `src/nativespeaker/api/auth/app_store.py:1-31`. D-06 is a move, not a rewrite.

Move the dataclass verbatim, minus `revoked_at` / `in_billing_retry` (RESEARCH P-02) and plus
`status: SubscriptionStatus` and `tier_id: str` (D-11, D-16). The frozen/slots shape and the
one-line docstring must survive the move:

```python
@dataclass(frozen=True, slots=True)
class VerifiedNotification:
    """One store notification after verification, in this project's own field names."""

    provider: PurchaseProvider
    notification_uuid: str
    event_type: str
    external_id: str | None
    ...
```

The module docstring must carry `app_store.py:1-2`'s no-logger rule forward — it is what
RESEARCH § Anti-Patterns cites:

```python
"""The App Store Server Notifications integration: one envelope and its two nested payloads, verified.
A signed payload carries an attribution token: this module holds no logger, so none is logged."""
```

---

### `src/nativespeaker/api/auth/google_play.py` (NEW — adapter, request-response)

Two analogs, both needed. `auth/app_store.py` gives the **module shape**;
`auth/devicecheck.py` gives the **httpx-over-a-vendor-API shape**.

**Module constants pattern** — `auth/devicecheck.py:15-27`. Host, path template and timeout are
module constants above the classes, each with its one-line reason:

```python
# Production only: the development host is not a config field, so no client input can select it.
DEVICECHECK_HOST = "https://api.devicecheck.apple.com"
QUERY_PATH = "/v1/query_two_bits"

# A per-request option because every call mints its own bearer and sends one body.
DEVICECHECK_HTTP_TIMEOUT_SECONDS = 8
```

`DEVICECHECK_HTTP_TIMEOUT_SECONDS` is exported and consumed in `lifespan.py:69`
(`httpx.AsyncClient(timeout=...)`). Do the same for the Play client — RESEARCH § V9 requires an
explicit timeout.

**Protocol pattern** (D-07) — `auth/app_store.py:34-39` / `auth/devicecheck.py:42-51`:

```python
class DeviceCheckAdapter(Protocol):
    """The device-gate seam: one read of both bits, and one write of both."""

    async def read_bits(self, device_token: str) -> BitState:
        """The query call: the device's bit state, or a raise."""
        ...
```

**Class pattern: injected client, private attributes, `None` means unavailable** —
`auth/devicecheck.py:113-121` and `auth/app_store.py:72-78`. The `None`-checked construction and
the `Unavailable(stage=...)` raise is the D-14/D-18 503 shape:

```python
class AppStoreNotifications:
    def __init__(self, *, verifier: SignedDataVerifier | None) -> None:
        self._verifier = verifier

    def verify(self, signed_payload: str) -> VerifiedNotification:
        if self._verifier is None:
            raise Unavailable(stage="app_store_verify")
```

**Bearer-per-call + HTTP-error conversion pattern** — `auth/devicecheck.py:134-141`. Copy the
try/except-around-the-single-call shape for the Play GET:

```python
    async def _post(self, path: str, body: dict, *, stage: str) -> httpx.Response:
        """Send one signed request; a transport failure is retryable and carries no request material."""
        bearer = _service_jwt(self._key_id, self._team_id, self._private_key, stage=stage)
        try:
            return await self._client.post(f"{DEVICECHECK_HOST}{path}", json=body,
                                           headers={"Authorization": f"Bearer {bearer}"})
        except httpx.HTTPError as failure:
            raise RetryableDeviceCheckError(type(failure).__name__) from failure
```

**Status-classification pattern** — `auth/devicecheck.py:89-96`. One function, arms in an order
that lets nothing fall through to a default. This is the shape for OQ-5's 404/410 arm:

```python
def _reject_or_retry(response: httpx.Response, *, stage: str) -> None:
    """Raise on the two non-success arms: a definitive 400, then everything else retryable."""
    if response.status_code == 400:
        # Definitive: Apple refused the token itself, so no further attempt can change the answer.
        raise ProofRejected(stage=stage, cause="rejected")
    if response.status_code // 100 != 2:
        raise RetryableDeviceCheckError(f"status {response.status_code}")
```

**Timestamp helper pattern** — `auth/app_store.py:42-44` is the precedent RESEARCH names for a
one-line `eventTimeMillis` converter:

```python
def _instant(milliseconds: int | None) -> datetime | None:
    """Convert one of Apple's UNIX-millisecond stamps, keeping an absent one absent."""
    return None if milliseconds is None else datetime.fromtimestamp(milliseconds / 1000, UTC)
```

**Value-type assembly pattern** — `auth/app_store.py:47-66` (`_crossed`). One module function,
keyword arguments in field order, an inline one-line comment only where a field choice is
non-obvious:

```python
        # The raw string, never `notificationType`: the typed attribute is None for an unknown type.
        event_type=payload.rawNotificationType,
        ...
        # The envelope's own instant: neither nested payload carries a signing date.
        signed_at=_instant(payload.signedDate),
```

**Errors to raise** — all exist in `src/nativespeaker/api/errors.py`, none new:
`NotificationRejected` (401, `auth_required`), `Unavailable` (503,
`verification_temporarily_unavailable`), `UnmappedStoreProduct` (500), `AttributionConflict` (500),
`InternalError` (500). `NotificationRejected` carries the reason in `stage` only:

```python
raise NotificationRejected(stage=failure.status.name) from failure    # auth/app_store.py:83
```

**Log-field discipline** — `errors.py:272-274` and `:288-290`. Do not widen these:

```python
    def log_fields(self) -> dict[str, str | None]:
        # The store product id is a server-side catalogue value, so it is admissible; a token is not.
        return {"provider": str(self.provider), "product_id": self.product_id}
```

---

### `src/nativespeaker/api/auth/jwt_verifier.py` (edit — D-09)

**Analog:** itself. The two touch points are `:38-46` and `:70-75`.

```python
@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Exactly the verified `iss` and `sub`, never reconstructed from transport metadata."""
    issuer: str
    subject: str


# A bounded reason is never client-visible: it reaches the security log and nowhere else.
VerificationResult = tuple[VerifiedClaims | None, BoundedReason | None]


def claims_from_payload(payload: dict) -> VerificationResult:
    """Turn an already-verified payload into claims, enforcing the non-empty-`sub` rule."""
    subject = payload.get("sub")
    if not subject:
        return None, BoundedReason.empty_subject
    return VerifiedClaims(issuer=str(payload["iss"]), subject=str(subject)), None
```

The constructor's keyword-only, all-defaulted signature is what P-04 requires be preserved
(`:81-89`); add `required_claims` as one more defaulted keyword-only argument. The
never-raises structure at `:161-165` must not gain a new escape:

```python
        except PyJWTError as exc:
            return None, bounded_reason_for(exc)
        except Exception:
            # What makes "never raises" structural -- an escape would 500 a caller owed a 401.
            return None, BoundedReason.bad_signature
```

Do not add a `BoundedReason` member (`:22-29` is a five-member closed set that `errors.py`
imports).

---

### `src/nativespeaker/api/app/dependencies.py` (edit — `verify_google_play_notification`)

**Analog for the shape:** `dependencies.py:145-149`.

```python
def verify_app_store_notification(request: Request,
                                  body: AppStoreNotificationRequest) -> VerifiedNotification:
    """Turn the posted envelope into a verified notification, before the handler and before `get_db`."""
    # Never `run_in_threadpool`: with online checks off, no code path in the seam performs I/O.
    return request.app.state.app_store_notifications.verify(body.signedPayload)
```

**Analog for the async/threadpool half:** `dependencies.py:52-54`. The comment states the rule
the Google token check and the `credential.refresh` both follow:

```python
    # `verify` is synchronous and can block on a JWKS fetch, so it never runs on the event loop.
    claims, reason = await run_in_threadpool(request.app.state.jwt_verifier.verify,
                                             credential.credentials)
    if claims is None:
        raise InvalidExternalJwt(bounded_reason=reason)
```

**`app.state` accessor pattern** — `dependencies.py:104-112`, for reaching either Google class
without taking `Request` in the handler:

```python
def get_firebase_adapter(request: Request):
    """The provider seam the lifespan built, deliberately unannotated."""
    # The concrete class implements the Protocol's one reachable method asynchronously, not synchronously.
    return request.app.state.firebase_adapter
```

**Edit to `get_subscriptions_service`** (D-16 drops `products`), `:137-142`:

```python
def get_subscriptions_service(db: AsyncSession = Depends(get_db),
                              config: AppConfig = Depends(get_config),
                              evaluated_at: datetime = Depends(get_evaluated_at),
                              ) -> SubscriptionsService:
    return SubscriptionsService(db=db, evaluated_at=evaluated_at,
                                products=config.app_store.products)
```

Note the file-ordering rule at `:83` — `# Defined below the dependencies it declares, because its
`Depends()` defaults are evaluated at definition time.`

Also edit the import at `:10` (`from nativespeaker.api.auth.app_store import VerifiedNotification`)
for D-06.

---

### `src/nativespeaker/api/app/lifespan.py` (edit — build the two Google classes)

**Builder pattern, incl. the F-04 guard shape:** `lifespan.py:33-45`.

```python
def build_app_store_verifier(store: AppStoreConfig) -> SignedDataVerifier | None:
    """The one verifier, or `None` when this deployment cannot build one."""
    root = Path(store.root_certificate_path) if store.root_certificate_path else None
    # Production needs the app id too: the library raises ValueError without it, and that would stop boot.
    if not (store.bundle_id and store.environment and root and root.is_file()) or (
            store.environment is StoreEnvironment.production and store.app_apple_id is None):
        return None
    return SignedDataVerifier(...)
```

**Warn-then-set-unconditionally pattern:** `lifespan.py:75-83`. The second comment is load-bearing
and must be reproduced for the Google pair:

```python
    app_store_verifier = build_app_store_verifier(config.app_store)
    if app_store_verifier is None:
        logger.warning("app_store_configuration_absent",
                       consequence="POST /webhooks/app-store fails closed as "
                                   "verification_temporarily_unavailable until the App Store bundle "
                                   "id, environment, app id and root certificate are available in "
                                   "this environment")
    # Set unconditionally, so the route set is the same in every environment.
    app.state.app_store_notifications = AppStoreNotifications(verifier=app_store_verifier)
```

**httpx client owned by the lifespan and closed on shutdown:** `lifespan.py:69` and `:104`. Copy
both halves for the Play client:

```python
    devicecheck_client = httpx.AsyncClient(timeout=DEVICECHECK_HTTP_TIMEOUT_SECONDS)
    ...
    await devicecheck_client.aclose()
```

**ADC probe pattern (D-14):** `auth/firebase.py:48-55`, and its warning at `:35-38`.

```python
def _application_default_credential() -> credentials.ApplicationDefault | None:
    """ADC if the environment supplies it, `None` if it does not -- never a raise."""
    try:
        google.auth.default()
    except google.auth.exceptions.DefaultCredentialsError:
        return None
    logger.info("firebase_admin_using_application_default_credentials")
    return credentials.ApplicationDefault()
```

```python
        logger.warning("firebase_admin_credential_absent",
                       consequence="user creation fails closed as verification_temporarily_unavailable "
                                   "until Application Default Credentials are available in this environment")
```

`import google.auth` / `import google.auth.exceptions` already appear at `auth/firebase.py:8-9`.

---

### `src/nativespeaker/api/config.py` (edit — `GooglePlayConfig`)

**Analog:** `config.py:71-98`, copied field-for-field in structure.

```python
class AppStoreConfig(BaseModel):
    """The App Store Server Notifications settings the JWS verifier is built from."""
    # All five optional, like DeviceCheckConfig: an absent value lets boot proceed and the route fail closed.
    bundle_id: str | None = Field(default=None, description="The app's bundle ID")
    ...
    products: dict[str, str] = Field(default_factory=dict,
                                     description="Store product ID to core.access_tiers.id")

    # Degrading beats raising: absence is already the fail-closed path this route answers 503 from,
    # and `lifespan` logs the same app_store_configuration_absent warning for it either way.
    @field_validator("app_apple_id", mode="before")
    @classmethod
    def _numeric_or_absent(cls, value):
        """Keep an int or an all-digit string, and read anything else as absent."""
```

Registration on `AppConfig`, `config.py:116`:

```python
    app_store: AppStoreConfig = Field(default_factory=AppStoreConfig)
```

The nesting rule that RESEARCH A5 says must be proved empirically lives at `config.py:20-22`:

```python
    model_config = SettingsConfigDict(env_nested_delimiter="_",
                                      env_nested_max_split=1,
                                      hide_input_in_errors=True)
```

---

### `src/nativespeaker/api/routers/webhooks.py` (edit — second route, no router gate)

**Analog:** the file itself, `:1-29`.

```python
"""The one store-callback route: `/webhooks/app-store` ingests Apple's signed notifications."""
...
# Membership of this router is the provider-callback partition; no other router declares the verifier.
router = APIRouter(tags=["webhooks"],
                   dependencies=[Depends(verify_app_store_notification)])


@router.post("/webhooks/app-store",
             status_code=200,
             summary="Ingest one App Store Server Notification",
             description="Verifies Apple's signed envelope and both nested payloads against the "
                         "pinned Apple root, then records the subscription and its event. It reads "
                         "no Authorization header.")
async def app_store_notification(
        notification: VerifiedNotification = Depends(verify_app_store_notification),
        service: SubscriptionsService = Depends(get_subscriptions_service)) -> Response:
    """Record one verified notification, or answer 200 having written nothing."""
    await service.ingest(notification)
    # An empty body: Apple reads the status code and nothing else.
    return Response(status_code=200)
```

D-01 deletes the `dependencies=[...]` argument (and rewrites the comment above it); the
verifier-first parameter order in the handler is already what the Apple route has, so the Google
handler copies it exactly. Both routes then keep `Depends()`-only bodies per `AGENTS.md`.

D-04/D-05 mean the Google handler must tolerate a `notification` that is `None` (nothing to
ingest, still 200) — the closest in-repo precedent for a verified-but-unwritable delivery is
`services/subscriptions.py:51-55`, which returns rather than raising.

---

### `src/nativespeaker/api/schemas/webhooks.py` (edit — the Pub/Sub envelope)

**Analog:** the whole file, `:1-8`.

```python
"""The store-callback request bodies. `signedPayload` keeps Apple's camelCase spelling as sent."""
from pydantic import BaseModel, Field


class AppStoreNotificationRequest(BaseModel):
    """The App Store notification body: the signed envelope, and nothing else."""
    # Required and non-empty, so an unusable body is the framework's 422 rather than a verification 401.
    signedPayload: str = Field(..., min_length=1)
```

Keep Google's camelCase (`messageId`, `data`) as sent, per the module docstring's own rule, and
keep `min_length=1` on `message.data` per D-04.

---

### `src/nativespeaker/api/services/subscriptions.py` (edit — D-11, D-12, D-16)

**Analog:** the file itself. Three exact edits.

Delete `status_at` (`:17-33`) and its call site (`:108`):

```python
def status_at(notification: VerifiedNotification,
              evaluated_at: datetime) -> SubscriptionStatus:
    """The subscription's status from its dates alone. The notification type is only recorded."""
    ...
```
```python
        status = status_at(notification, self.evaluated_at)
```
→ `status = notification.status`.

Drop `products` from `__init__` (`:38-46`) and the product lookup (`:57-60`); `tier_id` comes
off the notification:

```python
        tier_id = self.products.get(notification.product_id)
        if tier_id is None:
            # Refused before any write: `core.subscriptions.tier_id` is NOT NULL and has no default.
            raise UnmappedStoreProduct(notification.provider, notification.product_id)
```

Raise the log level at `:93` (D-12) and reword the comment above the guard at `:84`, which names
Apple alone:

```python
        if (stored is not None and stored.store_signed_at is not None
                and notification.signed_at is not None
                and notification.signed_at < stored.store_signed_at):
            # Apple guarantees no delivery order, and `notification_uuid` only catches the same payload twice.
            ...
            logger.info("store_notification_superseded", event_type=notification.event_type)
```

Leave `:152-154` alone but read it before writing the Google class — it is RESEARCH P-01:

```python
                # During grace the term is Apple's grace window, because the paid term has lapsed.
                ends_at=(notification.grace_period_expires_at
                         if status is SubscriptionStatus.grace_period else notification.expires_at),
```

Everything else in `ingest()` is called as-is. `crud/subscriptions.py` and `crud/purchases.py` are
untouched — `PurchasesDB.resolve_user` (`crud/purchases.py:28-34`) already takes the provider.

---

### `k8s/templates/httproute-webhooks.yaml` (edit — D-19)

**Analog:** the file itself, `:11-20`. Add one more `matches` entry under the same `rules` list,
and amend the comment because the Google route *does* carry an Authorization header:

```yaml
  # This route is outside the JWT SecurityPolicy. Apple sends no Authorization header.
  rules:
  - matches:
    - path:
        type: Exact
        value: /webhooks/app-store
      method: POST
    backendRefs:
    - name: {{ include "ns-api-gateway.fullname" . }}
      port: {{ .Values.service.port }}
```

---

### `.env.example` (edit) and `config/config.yaml` (edit)

**Analog:** `.env.example:83-110`. The block explains where each value is read, why it is not a
secret, why it does not live in the tracked YAML, and what happens when it is absent — then ships
the variables commented out with parsing values:

```
# So uncomment and fill all three, or leave all three out. They ship commented out, with values
# that parse if you uncomment them, because a copied line is read at boot by the whole service.
#APP_STORE_BUNDLE_ID=com.example.yourapp
#APP_STORE_APP_APPLE_ID=6001234567
#APP_STORE_ENVIRONMENT=sandbox
```

RESEARCH P-05 (the Android client must send `obfuscatedExternalAccountId`) goes here.

**Analog for the products map:** the tail of `config/config.yaml`:

```yaml
# An operator edits this map; a verified product id absent from it is a 500 and Apple's next retry succeeds.
app_store:
  products:
    com.nativespeaker.subscription.monthly: paid
```

---

### `tests/unit/test_app_wiring.py` (edit — D-02, D-03)

**Analog:** the file itself. The literal at `:15-18` and the class at `:83-109`:

```python
# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
PROVIDER_CALLBACK_PATHS = {"/webhooks/app-store"}
```

```python
def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]
```

```python
class TestTheProviderCallbackPartition:
    """Membership is the set of routes on the webhooks router, counted here against one literal."""

    def test_the_partition_is_exactly_the_routes_on_the_webhooks_router(self):
        from nativespeaker.api.routers import webhooks_router

        assert {route.path for route in webhooks_router.routes} == PROVIDER_CALLBACK_PATHS

    @pytest.mark.parametrize("path", sorted(PROVIDER_CALLBACK_PATHS))
    def test_each_callback_route_declares_the_verifier_and_neither_identity(self, path):
        """Named rather than left to a generic case, which would also pass if the route were absent."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        for calls in declared:
            assert verify_app_store_notification in calls
            assert get_identity not in calls
            assert get_linked_identity not in calls
```

The two cases that hard-code `verify_app_store_notification` (`:92-99`, `:101-105`) become
map-driven over `PROVIDER_CALLBACK_VERIFIERS.items()` (RESEARCH F-06). The two cases in
`TestEveryRouteIsAuthenticated` that read `PROVIDER_CALLBACK_PATHS` (`:33-38`, `:67-72`) widen by
the literal edit alone. Every class in this file carries a docstring saying what a silent
widening would look like — keep that voice for the two new D-02 cases.

---

### `tests/unit/test_google_play_notifications.py` (NEW — unit)

**Analog A — the JWKS harness to import, not re-create:** `tests/unit/test_jwks_offload.py:26-62`.

```python
def jwks_body(kid: str = KNOWN_KID) -> bytes:
    """A one-key JWKS document served under whatever `kid` is asked for; `PyJWKSet` rejects an empty key list."""
    key = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(PUBLIC_KEY_PEM)
    jwk = json.loads(RSAAlgorithm.to_jwk(key))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return json.dumps({"keys": [jwk]}).encode()


class CountedJwksTransport:
    """A counted, optionally slow, optionally failing stand-in for PyJWT's one blocking call."""

    def urlopen(self, request, timeout=None, context=None):  # noqa: ARG002 - urlopen's signature
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def install_counted_transport(monkeypatch) -> CountedJwksTransport:
    """Put a counted transport under a real `PyJWKClient`, and hand back the counter."""
    transport = CountedJwksTransport()
    monkeypatch.setattr("urllib.request.urlopen", transport.urlopen)
    return transport
```

`transport.error` is exactly what proves F-04's warm-up guard returns `None` instead of raising.
`make_token`, `PUBLIC_KEY_PEM`, `TEST_ISSUER` come from `unit/conftest.py` (imported as
`from unit.conftest import ...`, see `test_jwks_offload.py:16`).

**Analog B — module docstring and "untested by construction" honesty:**
`tests/unit/test_app_store_notifications.py:1-3`:

```python
"""The Apple chain walk, both OID checks, the ES256 rule and the signature check, all run for real here.
A throwaway root, intermediate and leaf mint the payloads, and the vendored Apple root refuses them.
Untested by construction: only whether Apple's live notifications match Apple's own declared shapes."""
```

---

### `tests/e2e/conftest.py` (edit — two Google fixtures)

**Analog:** `tests/e2e/conftest.py:267-307`, copied twice (scripted, and unconfigured).

```python
class FakeAppStoreNotifications:
    """A scriptable stand-in for the store-callback seam, recording every payload it was given."""

    def __init__(self) -> None:
        # No default answer: every case scripts the notification it wants verified or refused.
        self.answer: BaseException | VerifiedNotification | None = None
        self.calls: list[str] = []

    def script(self, answer: BaseException | VerifiedNotification) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted notification is returned."""
        self.answer = answer

    def verify(self, signed_payload: str) -> VerifiedNotification:
        self.calls.append(signed_payload)
        if isinstance(self.answer, BaseException):
            raise self.answer
        assert self.answer is not None, "the seam was called before a case scripted it"
        return self.answer


@pytest.fixture
def scripted_app_store_notifications(_app_lifespan):
    """Swap app.state.app_store_notifications for a scripted fake, scripted per case."""
    original = _app_lifespan.state.app_store_notifications
    notifications = FakeAppStoreNotifications()
    _app_lifespan.state.app_store_notifications = notifications
    try:
        yield notifications
    finally:
        _app_lifespan.state.app_store_notifications = original


@pytest.fixture
def unconfigured_app_store_notifications(_app_lifespan):
    """Swap app.state.app_store_notifications for one holding no verifier, as an incomplete config leaves it."""
    original = _app_lifespan.state.app_store_notifications
    _app_lifespan.state.app_store_notifications = AppStoreNotifications(verifier=None)
    try:
        yield _app_lifespan.state.app_store_notifications
    finally:
        _app_lifespan.state.app_store_notifications = original
```

The Google fake must be `async def` for the Play half (D-08's second class does I/O), which is the
one difference from the shape above; `FakeDeviceCheckAdapter` (`conftest.py:~240-252`) is the async
scripted-fake precedent in the same file.

---

### `tests/e2e/test_google_play_webhook.py` (NEW — e2e)

**Analog:** `tests/e2e/test_app_store_webhook.py:1-140`, near-copyable.

```python
pytestmark = pytest.mark.e2e

PATH = "/webhooks/app-store"

# The one body every verification failure answers with, compared by equality so a richer field fails here.
REJECTED = {"code": "auth_required"}

# The same body as raw bytes, so the refusals are compared on the wire and not after parsing.
REJECTED_BODY = b'{"code":"auth_required"}'

# The 503 an incomplete configuration answers, and the 500 both refusal leaves share.
UNAVAILABLE = {"code": "verification_temporarily_unavailable"}
INTERNAL = {"code": "internal_error"}
```

```python
# Every value a log record must never carry: the payload, both attribution tokens and the store token.
SENSITIVE_VALUES = (ENVELOPE, TOKEN, OTHER_TOKEN, STORE_TOKEN)

_LOGGERS = ("nativespeaker.api.app.error_handlers.logger",
            "nativespeaker.api.services.subscriptions.logger")


def _spy_on(monkeypatch, targets: tuple[str, ...], levels: tuple[str, ...]) -> _LogSpy:
    """A spy, not `capture_logs`: the module-level logger caches its binding, so capture sees nothing."""
```

```python
@pytest_asyncio.fixture(loop_scope="module")
async def webhook_client(_app_lifespan):
    """A client over the real started app that sends no Authorization header."""
    transport = ASGITransport(app=_app_lifespan)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

The Google client sends `Authorization: Bearer <oidc token>`, so that fixture's docstring is the
one line that changes. The `SENSITIVE_VALUES` walk must add the purchase token — D-10 persists it,
and RESEARCH § Anti-Patterns still forbids logging it.

---

### `tests/schema/test_subscription_ingestion.py` (edit)

**Analog:** `:36-56` — the keyword-built notification factory every case overrides.

```python
def _notification(*, external_id: str, token: str | None, purchased_at: datetime,
                  expires_at: datetime | None, revoked_at: datetime | None = None,
                  grace_period_expires_at: datetime | None = None,
                  signed_at: datetime | None = None, event_type: str = "DID_RENEW",
                  notification_uuid: str | None = None) -> VerifiedNotification:
    """One verified notification carrying the transaction part every write needs."""
    return VerifiedNotification(
        provider=PurchaseProvider.apple,
        notification_uuid=notification_uuid or f"notification-{uuid.uuid4()}",
        ...
        # The purchase instant unless a case places it: two deliveries otherwise share one signing date.
        signed_at=purchased_at if signed_at is None else signed_at,
        ...)
```

This factory changes shape twice: `revoked_at` / `in_billing_retry` disappear (P-02) and
`status` / `tier_id` appear (D-11, D-16). A `provider=PurchaseProvider.google_play` variant is the
new-case pattern; `PurchaseProvider.google_play` already exists in `tables/purchases.py`.

---

### `tests/unit/test_config.py` (edit)

**Analog:** `:245-264` — copy the class verbatim in structure for `GOOGLE_PLAY_*`. It is where
RESEARCH A5 (`env_nested_max_split=1`) is falsified cheaply:

```python
class TestTheThreeDeployerVariablesLandOnTheConfig:
    """P-13, P-14. The deployer supplies three variables and the tracked file supplies the product map."""

    def test_the_tracked_product_map_merges_with_the_environment_nesting(self):
        """D-16, P-13: the partial `app_store:` block coexists with APP_STORE_*, as `db:` does with DB_*."""
        store = load_tracked_config(_APP_STORE_ENV).app_store
        assert store.products
        assert set(store.products.values()) <= {"anonymous", "registered", "paid"}

    def test_the_model_declares_no_sibling_field_that_would_make_a_variable_ambiguous(self):
        """P-14: a field named `appstore` beside `app_store` was measured to stop APP_STORE_APP_APPLE_ID landing."""
        assert "appstore" not in AppConfig.model_fields
        assert "app_store" in AppConfig.model_fields
```

The second case is the direct ancestor of the `google` / `google_play` ambiguity check.

---

### `tests/unit/test_auth_package_shape.py` (edit — easily missed)

**Analog:** itself, `:12-13`. Two new modules in `auth/` fail this test until the literal is
updated. It is not named in CONTEXT.md or RESEARCH.md.

```python
# What it measures now: modules, classes, functions.
CURRENT = (6, 15, 40)
```

The docstring states why the literal exists — a derived count would agree with anything:

```python
"""How big the auth package is, as a number rather than a claim.

The shape is a literal: derived from the package, it would measure itself and agree with anything.
"""
```

`tests/unit/test_docstring_bar.py:30` walks `*.py` under the source tree, so both new modules
also come under the docstring/comment bar automatically.

---

## Shared Patterns

### Module docstrings and comments (`AGENTS.md`, D-23)

**Source:** `auth/app_store.py:1-2`, `auth/devicecheck.py:1-2`, `services/subscriptions.py:1`.
**Apply to:** every new and edited file.

One or two lines, stating what the entity does plus at most one rule the reader would otherwise
break. Comments are one line each, sit directly above the lines they explain, and give the reason
rather than the design:

```python
"""Store-subscription ingestion: one verified notification, one transaction, one commit."""
```
```python
        # Read before the transaction writes, so no token read happens under a lock.
```

`tests/unit/test_docstring_bar.py` enforces this over `src/`.

### The `None`-means-unavailable → 503 chain

**Source:** `config.py:73` (optional fields) → `lifespan.py:33-45` (`build_*` returns `None`) →
`lifespan.py:76-83` (one warning, set unconditionally) → `auth/app_store.py:77-78`
(`raise Unavailable(stage=...)`).
**Apply to:** `GooglePlayConfig`, both Google classes, both lifespan builders.

The single invariant across all four: an incomplete deployment boots, logs one named warning, and
registers the same route set as a complete one.

### Refusal answers: one class, one body, the reason in `stage`

**Source:** `errors.py:457-461` and `auth/app_store.py:83`.
**Apply to:** every Google refusal arm.

```python
class NotificationRejected(ProviderLookupError):
    """The store notification did not verify: the signature, the chain, the app or the environment."""
    # One class for every arm, so the answer tells a caller nothing about which check refused it.
    status = 401
    code = "auth_required"
```

Byte-identical bodies are asserted in `tests/e2e/test_app_store_webhook.py:33-36`.

### Structured-log labels from a closed set

**Source:** `services/subscriptions.py:167-168` and `errors.py:272-274`.
**Apply to:** every new log line, including D-04's ERROR and D-05's INFO.

```python
        # Labels come from a closed set only: the store's own name, never a payload value.
        logger.warning("store_notification_race_lost", provider=str(notification.provider))
```

### `run_in_threadpool` for any blocking vendor call

**Source:** `app/dependencies.py:52-53`, `auth/firebase.py:70-71`.
**Apply to:** the Google token verification and `credential.refresh()`.

```python
        # `firebase-admin` is built on `requests` and has no async client, so it runs off the loop.
        return await run_in_threadpool(self._read, app, subject)
```

### `Depends()`-only handlers, `app.state` classes built in lifespan

**Source:** `routers/webhooks.py:23-27`, `dependencies.py:99-112`, `lifespan.py:57-83`.
**Apply to:** the Google route and its dependency.

No handler constructs a database or vendor class; the accessor exists so the handler never takes
`Request` itself.

---

## No Analog Found

| File / element | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| The `purchases.subscriptionsv2` response model in `auth/google_play.py` | schema | transform | No vendor JSON response is modelled anywhere in this repo. `auth/devicecheck.py:98-110` reads Apple's body as a plain `dict`. Use RESEARCH § F-09's field table and this project's normal Pydantic style (`schemas/webhooks.py`) instead. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/{auth,app,routers,schemas,services,crud,tables}/`,
`config/`, `k8s/templates/`, `tests/{unit,e2e,schema}/`.
**Files read this session:** 20.
**Tracked-source check:** `git ls-files` run over every path cited above; all 27 returned.
**Pattern extraction date:** 2026-09-05
</content>
</invoke>
