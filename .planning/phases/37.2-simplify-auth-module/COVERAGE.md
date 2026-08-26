# Phase 37.2 — External API Coverage Matrix

**API:** Firebase Admin SDK for Python (`firebase-admin >=7.3.0`, `pyproject.toml:24`) — **re-decided**
**Secondary API:** OpenAI Chat Completions via LangChain `with_structured_output` (default `gpt-4o-mini`)
**Test-only API:** Identity Toolkit REST v1 (`tests/e2e/conftest.py`)
**Detector:** `api-coverage.cjs --json` → `detected: true`, signal `(surface) sdk`

## Why this phase gets its own matrix

Phase 37.2 is a simplification phase, not a new integration — but simplification *is* a coverage
decision when it deletes a capability. Two rows of Phase 37's matrix are inverted here, one row it
recorded as an opt-out was in fact already integrated, and one opt-out changed in kind. Per the
full-coverage rule, this matrix restarts from the full baseline rather than inheriting Phase 37's
subtractions.

**The credential reversal is already decided and recorded**, in `37.2-CONTEXT.md` D-06, D-07, and
D-08. D-08 is filed as a FLAGGED CONFLICT against `SHARED-INVARIANTS.md`'s no-ambient-credential
rule and explicitly supersedes Phase 37's D-08. Its reasoning: production runs on GKE where ADC is
Workload Identity — strictly better than a mounted service-account key — and the sub-$5/month
threat model does not justify maintaining a parallel credential path. Reversible; the deleted
branch is ~30 lines in git history. This file records that decision's coverage consequences in the
shape the seal gate reads; it does not re-open it.

## `firebase_admin` app / credential surface

| capability | decision | reason |
|---|---|---|
| `firebase_admin.initialize_app(cred, options, name=)` | INTEGRATE | Unchanged. One named app per issuer; `firebase.py:47-52` passes explicit `projectId` and `name`. |
| `credentials.ApplicationDefault` | INTEGRATE | Flipped from OPT-OUT. Now the only credential path (`firebase.py:55-63`), per D-06/D-08. See the note above. |
| `google.auth.default()` ADC probe | INTEGRATE | New. Probed once at boot so an absent credential is a warning plus an empty app dict (D-07), not a late 503. |
| `credentials.Certificate(dict)` | OPT-OUT | Flipped from INTEGRATE. Deleted by D-06 with `FirebaseConfig`, `AppConfig.firebase`, and the `.env.example` key line. |
| `credentials.RefreshToken` | OPT-OUT | Unchanged. A user-credential path is the ambient-credential risk D-08 accepts only in its Workload Identity form. |
| `initialize_app()` with no credential (`[DEFAULT]` app) | OPT-OUT | Unchanged and load-bearing. No `[DEFAULT]` app exists, so a call site that forgets `app=` fails loudly. |
| `firebase_admin.get_app(name)` | OPT-OUT | Was INTEGRATE. Apps now live in the dict from `build_admin_apps`; the process-global registry is never read back. |
| `firebase_admin.delete_app` | INTEGRATE | Was OPT-OUT, wrongly. `lifespan.py:65-66` tears down every named app at shutdown. See the correction note below. |
| `httpTimeout` app option | INTEGRATE | Unchanged. `FIREBASE_HTTP_TIMEOUT_SECONDS = 8`, set at app level because the SDK has no per-call knob. |

**Correction to Phase 37's `delete_app` row.** Phase 37 opted out on the grounds that "apps live
for the process lifetime; the lifespan creates them once at boot and never tears one down mid-run."
That was already false when written. `firebase_admin` keeps named apps in a process-global registry
and `initialize_app` raises on a repeated name, so the e2e suite's second boot in one process dies
at startup without the teardown. It stayed invisible only while no credential was configured, since
`build_admin_apps` then returned `{}` and registered nothing. Corrected here rather than carried
forward as a stale row.

## `firebase_admin.auth` capability surface

Carried forward from Phase 37 and re-checked against shipped code. One row changed in kind.

| capability | decision | reason |
|---|---|---|
| `auth.get_user(uid, app=)` | INTEGRATE | Unchanged. Still the single call, in `FirebaseAdminLookup._read`. |
| `UserRecord.provider_data` | INTEGRATE | Unchanged. Materialized inside the threadpool `try` — a lazy property that raises on an empty rawId. |
| `UserRecord.email` / `.email_verified` | INTEGRATE | Unchanged. Read off the same `getUser` response; only a non-empty verified address is copied. |
| `auth.verify_id_token()` | OPT-OUT | Changed in kind. Phase 37 left it declared on the Protocol with no implementation; plan 04 deleted the declaration too. |
| `auth.verify_id_token(check_revoked=True)` | OPT-OUT | Unchanged. No per-request Firebase revocation check. |
| `auth.revoke_refresh_tokens()` | OPT-OUT | Unchanged. Assigned to the sign-out-all phase (46), which re-decides from this baseline. |
| `UserRecord.display_name` | OPT-OUT | Unchanged. Never populated. |
| `UserRecord.custom_claims` | OPT-OUT | Unchanged. Authorization is read from the database, never from a Firebase claim. |
| `UserRecord.disabled` / `.tokens_valid_after_timestamp` | OPT-OUT | Unchanged. Admission state is `core.users.active` plus `identity_state`, never Firebase. |
| `UserRecord.user_metadata` / `.tenant_id` | OPT-OUT | Unchanged. No branch reads them. |
| `firebase.sign_in_provider` token claim | OPT-OUT | Unchanged. The stored `provider` column is the sole classifier (`google.com`, `apple.com`). |
| `auth.get_user_by_email` / `get_user_by_phone_number` | OPT-OUT | Unchanged. Identity is `(issuer, subject)` only; a second key would be a second identity path. |
| `auth.get_users()` / `auth.list_users()` | OPT-OUT | Unchanged. Nothing enumerates the Firebase directory; reads are per-subject. |
| `auth.create_user()` / `auth.update_user()` | OPT-OUT | Unchanged. The backend never writes to Firebase; its copy is a projection. |
| `auth.delete_user()` / `auth.delete_users()` | OPT-OUT | Unchanged. Identity rows are permanent tombstones; account deletion is not a v2.0 operation. |
| `auth.set_custom_user_claims()` | OPT-OUT | Unchanged. No backend-minted claim tier exists. |
| `auth.create_custom_token()` | OPT-OUT | Unchanged. No backend token tier. |
| `auth.create_session_cookie()` | OPT-OUT | Unchanged. No cookie transport; `Authorization: Bearer` is the sole identity carrier. |
| `auth.verify_session_cookie()` | OPT-OUT | Unchanged. Same — no cookie transport. |
| `auth.generate_password_reset_link()` | OPT-OUT | Unchanged. Credential lifecycle is client-side; the backend sends no mail. |
| `auth.generate_email_verification_link()` | OPT-OUT | Unchanged. Same client-side credential lifecycle. |
| `auth.generate_sign_in_with_email_link()` | OPT-OUT | Unchanged. Same; no email-link sign-in flow exists. |
| `auth.ActionCodeSettings` | OPT-OUT | Unchanged. Depends on the link-generation family, all opted out. |
| `auth.import_users()` | OPT-OUT | Unchanged. No migration source — pre-launch, zero users. |
| `auth.create_oidc_provider_config()` | OPT-OUT | Unchanged. Provider configuration is console-managed, not code-managed. |
| `auth.create_saml_provider_config()` | OPT-OUT | Unchanged. No SAML issuer; the classifier is closed to two provider ids. |
| the remaining `auth.*_provider_config` family | OPT-OUT | Unchanged. Same console-managed provider configuration. |
| `firebase_admin.tenant_mgt` | OPT-OUT | Unchanged. Single project, single issuer; multi-tenancy would change the identity model. |

## LLM structured-output surface (plan 37.2-03, folded todo)

Plan 03 shipped inside this phase and sits outside the five ROADMAP directives, but it changed how
the provider is called, so its choices are recorded. This is the first coverage decision on this
surface — Phase 35's `COVERAGE.md` declares no external integration, and the chat chain predates
GSD tracking.

| capability | decision | reason |
|---|---|---|
| `with_structured_output(schema, method="json_schema", strict=True)` | INTEGRATE | `services/llm.py::create_chain`. The schema rides on the call, so the provider cannot omit a declared key. |
| flat root schema (`ChatModelResponse`) | INTEGRATE | Load-bearing: strict conversion forces properties `required` but does not descend into a root-level union. |
| `method="function_calling"` | OPT-OUT | Tool-call transport for a response that is not a tool call; `json_schema` is the direct route here. |
| `method="json_mode"` | OPT-OUT | Guarantees valid JSON but not the schema — the exact failure this change exists to close. |
| `include_raw=True` | OPT-OUT | Not needed on the request path; the one place raw provider JSON matters is the e2e gate, which reads it directly. |
| post-hoc validation into the three mode models | INTEGRATE | Kept. `ChatService.ask_llm` still dispatches on `resolved_mode` and re-validates; the client contract is unchanged. |
| streaming responses | OPT-OUT | The product is one synchronous chat turn returning one JSON object. No route streams. |
| tool / function calling | OPT-OUT | No tool surface is specified in v2.0. |
| embeddings, assistants, files, images, moderation, batch, fine-tuning | OPT-OUT | None is reachable from any registered route; no provider-side state is persisted. |

**Known open item on this surface:** `37.2-REVIEW.md` WR-11 — a model refusal currently trips the
shared circuit breaker as a provider-health failure rather than mapping to `out_of_scope`. Recorded
in `37.2-VERIFICATION.md` as a follow-up candidate, not closed here.

## Identity Toolkit REST v1 (test fixtures only)

Unchanged this phase — `tests/e2e/conftest.py` still uses exactly two methods.

| capability | decision | reason |
|---|---|---|
| `accounts:signUp` (no email/password → anonymous) | INTEGRATE | The real-anonymous e2e fixture (D-09, Phase 37); the only shape the classifier accepts as `anonymous`. |
| `accounts:signInWithPassword` | INTEGRATE | Drives the barrier/admission modules. Its `providerData` is the rejection arm, so it cannot complete a create-user. |
| `accounts:signInWithIdp` | OPT-OUT | A real Google/Apple-linked account is not reproducibly scriptable in shared CI; covered by a substituted adapter. |
| `accounts:delete` | OPT-OUT | No cleanup path by design; anonymous test users accumulate in the shared test project. Accepted in Phase 37. |
| every other Identity Toolkit method | OPT-OUT | Test infrastructure only needs a token minted for a subject of a known providerData shape. |

## Second-integration note

Phases 40, 41, 42 and 46 each consume the `FirebaseAdminAdapter` seam and start from **this**
full-coverage baseline, not from these opt-outs. `auth.revoke_refresh_tokens` is expected to flip
to INTEGRATE in Phase 46. Phase 46 must also re-decide the credential rows above rather than assume
D-08 still holds under whatever threat model applies then.
