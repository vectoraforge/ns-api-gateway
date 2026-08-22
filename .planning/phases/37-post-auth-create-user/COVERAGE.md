# Phase 37 — External API Coverage Matrix

**API:** Firebase Admin SDK for Python (`firebase-admin` 7.3.0 installed, `>=7.3.0` declared at `pyproject.toml:24`)
**Secondary API:** Google Identity Platform / Identity Toolkit REST v1 (test fixtures only)
**Detector:** `api-coverage.cjs --json` → `detected: true`

## Why most of this surface is a reasoned opt-out

`02-create-user.md` § *Firebase Admin confirmation* pins this endpoint's completion reads as **2 of the exactly 5 enumerated providerData read points in the whole system**. `SHARED-INVARIANTS.md` forbids any ambient, default, global, or fallback client. `01-foundation.md §7.1` assigns each remaining adapter capability to a named later phase. So the opt-outs below are not gaps discovered late — they are the specification's own partition, written down.

## `firebase_admin` app / credential surface

| capability | decision | reason |
|---|---|---|
| `firebase_admin.initialize_app(cred, options, name=...)` | INTEGRATE | One named app per configured issuer (D-07, D-08). |
| `firebase_admin.credentials.Certificate(dict)` | INTEGRATE | Service-account JSON loaded inline from the gitignored `.env` (D-08). |
| `firebase_admin.get_app(name)` / named `App` handles | INTEGRATE | Every call site passes `app=`; issuer→app selection is an explicit dict lookup that fails closed. |
| `firebase_admin.initialize_app()` with no credential (`[DEFAULT]` app / ADC) | OPT-OUT | Forbidden by SHARED-INVARIANTS § Wire contract and D-08 — ADC silently picks up local gcloud user credentials. No `[DEFAULT]` app is created at all, so a call site that forgets `app=` fails loudly. |
| `credentials.ApplicationDefault` / `credentials.RefreshToken` | OPT-OUT | Same ambient-client prohibition as above. |
| `firebase_admin.delete_app` | OPT-OUT | Apps live for the process lifetime; the lifespan creates them once at boot and never tears one down mid-run. |
| `httpTimeout` app option | INTEGRATE | `adapters.py:14-20` mandates a fixed 5–10 s per-attempt timeout; this SDK has no per-call knob, so it is set once at app level. |

## `firebase_admin.auth` capability surface

| capability | decision | reason |
|---|---|---|
| `auth.get_user(uid, app=)` | INTEGRATE | §02 step 8's mandatory fail-closed providerData read on every completion. The single Phase 37 call. |
| `UserRecord.provider_data` | INTEGRATE | Materialized inside the threadpool call into foundation's `ProviderDataEntry` tuple (Pitfall 3). |
| `UserRecord.email` / `.email_verified` | INTEGRATE | §02 step 10 copies `email` only when the same successful response carries a non-empty address AND `emailVerified = true`. |
| `UserRecord.display_name` | OPT-OUT | §02 DELETIONS: `display_name` is NEVER populated. |
| `UserRecord.custom_claims`, `.tokens_valid_after_timestamp`, `.user_metadata`, `.tenant_id`, `.disabled` | OPT-OUT | No Phase 37 branch reads them; admission state comes from `core.users.active` + `core.external_identities.identity_state`, never from Firebase. |
| `firebase.sign_in_provider` token claim | OPT-OUT | §02 step 9: "never read `firebase.sign_in_provider`". The stored `provider` column is the sole classifier. |
| `auth.verify_id_token()` | OPT-OUT | The barrier's JWKS-backed `TokenVerifier` (`auth/verification.py`) is the only verification path in the service, and §02's hardenings forbid a handler re-implementing verification. `FirebaseAdminAdapter` declares the method; Phase 37's concrete class does not implement it (see 37-05-PLAN.md flagged assumption A-37-05-1). |
| `auth.verify_id_token(check_revoked=True)` | OPT-OUT | §02 DELETIONS: "no per-request Firebase revocation check (`checkRevoked` off)". |
| `auth.revoke_refresh_tokens()` | OPT-OUT | §7.1 assigns the revocation adapter, its retry budget, and any in-flight coalescing to the sign-out-all phase (Phase 46). Building it here would be building another phase's adapter. |
| `auth.get_user_by_email` / `get_user_by_phone_number` | OPT-OUT | Identity is `(issuer, subject)` only. An email- or phone-keyed lookup would be a second identity path §1.4 exists to make unrepresentable. |
| `auth.get_users()` (bulk) / `auth.list_users()` | OPT-OUT | Nothing in v2.0 enumerates the Firebase user directory; the enumerated read points are per-subject only. |
| `auth.create_user()` | OPT-OUT | Clients create their own Firebase user via the client SDK; the backend links an already-verified `(issuer, subject)` and never mints a provider account. |
| `auth.update_user()` | OPT-OUT | Backend never writes to Firebase. Firebase is the source of truth for provider linkage; the backend's copy is a projection. |
| `auth.delete_user()` / `auth.delete_users()` | OPT-OUT | SHARED-INVARIANTS retains identity rows as permanent tombstones and deletes no purge job; account deletion is not a v2.0 operation. (Note: the D-09 anonymous e2e fixture deliberately does **not** clean up — see 37-10-PLAN.md accepted cost.) |
| `auth.set_custom_user_claims()` | OPT-OUT | §02 step 14 and SHARED-INVARIANTS § Tokens: no backend-minted token, session, or claim tier exists. Authorization is read from the database, never from a token claim. |
| `auth.create_custom_token()` | OPT-OUT | Same: no backend token tier. |
| `auth.create_session_cookie()` / `verify_session_cookie()` | OPT-OUT | No cookie transport. `Authorization: Bearer` is the sole identity carrier (§02 hardenings). |
| `auth.generate_password_reset_link()` / `generate_email_verification_link()` / `generate_sign_in_with_email_link()` | OPT-OUT | Credential lifecycle is entirely client-side Firebase; the backend sends no mail and mints no links. |
| `auth.import_users()` | OPT-OUT | No migration source — pre-launch, zero existing users. |
| `auth.create_oidc_provider_config()` / `create_saml_provider_config()` / the `*_provider_config` family | OPT-OUT | The closed classifier recognizes exactly `google.com` and `apple.com`; provider configuration is console-managed, not code-managed. |
| `firebase_admin.tenant_mgt` (multi-tenancy) | OPT-OUT | Single Firebase project, single issuer. Multi-tenancy would change the identity model, not just the client. |
| `auth.ActionCodeSettings` | OPT-OUT | Depends on the link-generation family above, all opted out. |

## Identity Toolkit REST v1 (test fixtures only, `tests/e2e/conftest.py`)

| capability | decision | reason |
|---|---|---|
| `accounts:signUp` (no email/password → anonymous user) | INTEGRATE | D-09's real-anonymous e2e fixture. The only shape the closed classifier accepts as `anonymous`. |
| `accounts:signInWithPassword` | INTEGRATE | Already present; retained for the barrier/admission modules. Cannot drive a successful create-user completion (Pitfall 8) — its `providerData == [{providerId: "password"}]` is the rejection arm. |
| `accounts:signInWithIdp` (Google/Apple federated sign-in) | OPT-OUT | D-09: a real Google- or Apple-linked account cannot be scripted reproducibly in shared CI. The registered flow is covered by a substituted `FirebaseAdminAdapter` returning synthetic `ProviderDataResult`s. Revisit only if the fake drifts from the real SDK's shape (recorded in 37-CONTEXT.md § Deferred Ideas). |
| `accounts:delete` | OPT-OUT | No cleanup path exists by design; anonymous test users accumulate in the shared test project. Accepted. |
| every other Identity Toolkit method | OPT-OUT | Test infrastructure only needs a token minted for a subject of a known providerData shape. |

## Second-integration note

Phases 40, 41, 42 and 46 each consume the same `FirebaseAdminAdapter` seam. Per the full-coverage rule, each of those phases starts from **this same full-coverage baseline**, not from Phase 37's opt-out list. In particular `auth.revoke_refresh_tokens` is opted out here and is expected to flip to INTEGRATE in Phase 46.
