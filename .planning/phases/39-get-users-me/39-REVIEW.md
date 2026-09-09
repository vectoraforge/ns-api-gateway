---
phase: 39-get-users-me
reviewed: 2026-09-09T21:50:37Z
depth: standard
files_reviewed: 139
files_reviewed_list:
  - .env.example
  - .gitignore
  - AGENTS.md
  - Dockerfile
  - config/config.yaml
  - docker-compose.yml
  - k8s/templates/NOTES.txt
  - k8s/templates/deployment.yaml
  - k8s/templates/httproute-auth.yaml
  - k8s/templates/httproute-webhooks.yaml
  - k8s/templates/security-policy.yaml
  - k8s/values.yaml
  - migrations/20260818_01_initial-release.sql
  - pyproject.toml
  - src/nativespeaker/api/app/dependencies.py
  - src/nativespeaker/api/app/error_handlers.py
  - src/nativespeaker/api/app/lifespan.py
  - src/nativespeaker/api/app/main.py
  - src/nativespeaker/api/auth/adapters.py
  - src/nativespeaker/api/auth/app_store.py
  - src/nativespeaker/api/auth/devicecheck.py
  - src/nativespeaker/api/auth/firebase.py
  - src/nativespeaker/api/auth/google_play.py
  - src/nativespeaker/api/auth/jwt_verifier.py
  - src/nativespeaker/api/auth/store_notifications.py
  - src/nativespeaker/api/config.py
  - src/nativespeaker/api/crud/__init__.py
  - src/nativespeaker/api/crud/chats.py
  - src/nativespeaker/api/crud/grants.py
  - src/nativespeaker/api/crud/identities.py
  - src/nativespeaker/api/crud/purchases.py
  - src/nativespeaker/api/crud/subscriptions.py
  - src/nativespeaker/api/crud/violations.py
  - src/nativespeaker/api/errors.py
  - src/nativespeaker/api/logs.py
  - src/nativespeaker/api/resilience.py
  - src/nativespeaker/api/routers/__init__.py
  - src/nativespeaker/api/routers/auth.py
  - src/nativespeaker/api/routers/chats.py
  - src/nativespeaker/api/routers/examples.py
  - src/nativespeaker/api/routers/root.py
  - src/nativespeaker/api/routers/users.py
  - src/nativespeaker/api/routers/webhooks.py
  - src/nativespeaker/api/schemas/api.py
  - src/nativespeaker/api/schemas/auth.py
  - src/nativespeaker/api/schemas/llm.py
  - src/nativespeaker/api/schemas/webhooks.py
  - src/nativespeaker/api/services/__init__.py
  - src/nativespeaker/api/services/auth.py
  - src/nativespeaker/api/services/chats.py
  - src/nativespeaker/api/services/quota.py
  - src/nativespeaker/api/services/restore.py
  - src/nativespeaker/api/services/subscriptions.py
  - src/nativespeaker/api/services/sync.py
  - src/nativespeaker/api/tables/__init__.py
  - src/nativespeaker/api/tables/auth.py
  - src/nativespeaker/api/tables/chats.py
  - src/nativespeaker/api/tables/grants.py
  - src/nativespeaker/api/tables/purchases.py
  - tests/e2e/conftest.py
  - tests/e2e/test_app_store_webhook.py
  - tests/e2e/test_challenge_store.py
  - tests/e2e/test_chats.py
  - tests/e2e/test_claim_anonymous_grant.py
  - tests/e2e/test_claim_registered_grant.py
  - tests/e2e/test_create_user.py
  - tests/e2e/test_flows.py
  - tests/e2e/test_google_play_webhook.py
  - tests/e2e/test_quota.py
  - tests/e2e/test_restore_subscription.py
  - tests/e2e/test_sign_out_all.py
  - tests/e2e/test_sync.py
  - tests/e2e/test_upgrade_anonymous.py
  - tests/schema/conftest.py
  - tests/schema/helpers.py
  - tests/schema/test_apply_rollback.py
  - tests/schema/test_claim_race.py
  - tests/schema/test_constraints.py
  - tests/schema/test_create_atomicity.py
  - tests/schema/test_create_race.py
  - tests/schema/test_grant_locks.py
  - tests/schema/test_inventory.py
  - tests/schema/test_registration_pairing.py
  - tests/schema/test_restore_race.py
  - tests/schema/test_subscription_ingestion.py
  - tests/schema/test_subscription_race.py
  - tests/schema/test_sync_lock_freedom.py
  - tests/unit/conftest.py
  - tests/unit/error_tree.py
  - tests/unit/test_adapter_interfaces.py
  - tests/unit/test_app_store_notifications.py
  - tests/unit/test_app_wiring.py
  - tests/unit/test_auth_package_shape.py
  - tests/unit/test_auth_security.py
  - tests/unit/test_challenge_endpoint.py
  - tests/unit/test_chats_crud.py
  - tests/unit/test_claim_ordering.py
  - tests/unit/test_claim_precedence.py
  - tests/unit/test_claim_precedence_registered.py
  - tests/unit/test_config.py
  - tests/unit/test_conflict_classification.py
  - tests/unit/test_conversion_carries_usage.py
  - tests/unit/test_create_user_body.py
  - tests/unit/test_create_user_precedence.py
  - tests/unit/test_create_user_rollback.py
  - tests/unit/test_devicecheck_adapter.py
  - tests/unit/test_error_contract.py
  - tests/unit/test_error_registry.py
  - tests/unit/test_exception_handlers.py
  - tests/unit/test_firebase_adapter.py
  - tests/unit/test_firebase_retry.py
  - tests/unit/test_google_play_notifications.py
  - tests/unit/test_grant_sources.py
  - tests/unit/test_identities_crud.py
  - tests/unit/test_identity_accessors.py
  - tests/unit/test_identity_flip.py
  - tests/unit/test_jwks_offload.py
  - tests/unit/test_jwt_security.py
  - tests/unit/test_logging.py
  - tests/unit/test_models.py
  - tests/unit/test_monthly_period.py
  - tests/unit/test_purchases_crud.py
  - tests/unit/test_quota_resolver.py
  - tests/unit/test_quota_seam.py
  - tests/unit/test_rejection_vocabulary.py
  - tests/unit/test_resilience_retry.py
  - tests/unit/test_restore_proof.py
  - tests/unit/test_services.py
  - tests/unit/test_spent_free_grant_refusal.py
  - tests/unit/test_subscription_attribution.py
  - tests/unit/test_subscription_grant_write.py
  - tests/unit/test_subscription_store_clock.py
  - tests/unit/test_sync_clock_capture.py
  - tests/unit/test_sync_resolver.py
  - tests/unit/test_tables_metadata.py
  - tests/unit/test_upgrade_precedence.py
  - tests/unit/test_users.py
  - tests/unit/test_users_me.py
  - uv.lock
findings:
  critical: 0
  warning: 13
  info: 25
  total: 38
status: issues_found
---

# Phase 39: Code Review Report

**Reviewed:** 2026-09-09T21:50:37Z
**Depth:** standard
**Files Reviewed:** 139
**Status:** issues_found

## Summary

This is an incremental re-review of phase 39 (`GET /users/me`). The workflow scoped it to
everything that changed since the phase's previous review commit `1e6d57c`, which is
`1e6d57c..HEAD` at `a6ff85f` — 139 files, the accumulated output of the phase 35 through 38
review-and-fix passes. Because that scope is far larger than one reviewer can hold at
standard depth, the identical scope was split by module across six parallel
`gsd-code-reviewer` agents with disjoint finding-ID blocks, and their reports are merged
below without narrowing.

**No Critical finding survived verification.** `GET /users/me` itself is clean: the subject is
taken only from the authenticated dependency, the route accepts no client input on any
channel, tenant scoping holds on every read it performs, and no store proof, JWT or device
attestation reaches a response or error body. The 13 warnings are in surrounding code —
store ingestion, quota, resilience, deployment configuration, and guard strength in the test
suites.

Reviewers checked `.planning/REQUIREMENTS.md` and the phase decision records before filing.
Candidates already settled by a ratified decision were dropped with a citation; they are
listed under "Dropped (ratified decisions)" at the end of this report.

### Review split

| Reviewer | Slice | Files | ID block | C / W / I |
|---|---|---|---|---|
| R1 | app wiring, auth adapters, top-level modules | 15 | 01-19 | 0 / 3 / 6 |
| R2 | crud, tables, schemas, migration DDL | 17 | 20-39 | 0 / 1 / 5 |
| R3 | routers and services | 14 | 40-59 | 0 / 3 / 4 |
| R4 | deployment, packaging, configuration | 14 | 60-69 | 0 / 2 / 7 |
| R5 | unit test suite | 51 | 70-89 | 0 / 2 / 1 |
| R6 | e2e and schema test suites | 28 | 90-109 | 0 / 2 / 2 |

### Per-slice assessment

**R1 — app wiring, auth adapters, top-level modules**

I reviewed the app wiring (`main.py`, `lifespan.py`, `dependencies.py`, `error_handlers.py`), the six
auth adapters, and the four top-level modules (`config.py`, `errors.py`, `logs.py`, `resilience.py`)
at standard depth, reading each file in full and cross-referencing callers, the installed
`appstoreserverlibrary`, `firebase_admin`, `pydantic-settings` and `structlog`, and the binding
specs. No Critical finding survived verification: the three warnings are an observability defect,
a fail-safe whose guard does not hold the property its comment states, and a dead config field
that silently ignores an operator's setting.

Traced and **VERIFIED CLEAN**, each by reading the code and, where marked, by executing it:

- **Signature-skipping App Store environments are genuinely unreachable.** `signed_data_verifier.py:159-162`
  returns the payload *undecoded and unverified* for `Environment.XCODE`/`LOCAL_TESTING`.
  `AppStoreConfig._named_or_absent` (`config.py:103-109`) admits only the two `StoreEnvironment`
  members and `_STORE_ENVIRONMENTS` (`lifespan.py:47-48`) has exactly two arms with no case
  transform, so neither library member is constructible from any config value.
- **No client-controlled value reaches a URL path unescaped.** `PLAY_URL.format(...)` uses
  `quote(..., safe="")`; the one residue `quote` leaves is the dot, and `_names_one_path_segment`
  refuses a dots-only purchase token on both entry points (`google_play.py:177-179, 248, 309`).
- **No secret reaches a log.** I walked every `logger.*` call site in the seven auth modules:
  `app_store.py`, `devicecheck.py` and `store_notifications.py` hold no logger at all; `google_play.py`
  logs only exception class names, status codes and a length; `jwt_verifier.py` logs one bare event
  name with no exception text (the `PyJWKClientError` message embeds the `kid` and the JWKS URL and
  is never rendered); `errors.py::log_fields` emits only server-side catalogue values and row ids.
  `_QUIETED_LIBRARIES` does not name `langchain_openai`, but I read its four log sites — image-token
  counting only, no prompt material — so the omission is harmless.
- **An entitled store status with no term cannot mint an unbounded grant.** The comment at
  `app_store.py:52-53` claims `SubscriptionsService.ingest` refuses it; verified at
  `services/subscriptions.py:117-127`, which refuses an absent, inverted, or already-closed term.
- **An Apple test/summary notification cannot write a NULL `external_id`.** `_crossed(payload, None, None, ...)`
  (`app_store.py:127, 143`) produces `external_id=None`, and the webhook handler calls `ingest`
  unconditionally; `services/subscriptions.py:32-36` returns early on that shape.
- **No DB-pool starvation across the LLM call.** `get_identity` (`dependencies.py:86-89`) closes its
  own session before returning, and `ChatService.create_chat`/`send_message` commit the request
  session (`services/chats.py:94, 127`) before `admission()`, so no request pins a connection
  across a provider call under `pool_size=5, max_overflow=0`.
- **Detached-instance reads are safe.** `Session.close()` expunges without expiring, so every
  `identity.user.*` / `identity.identity.*` read in the routers and services is a loaded column
  attribute; no relationship attribute is touched off the object `get_identity` produced.
- **The error registry is total.** Executed: every `AppError` subclass's `code` is a member of the
  `ErrorCode` Literal, exactly one `answers_framework_status` class exists per status with no
  duplicates, and `camel_to_snake` yields 63 distinct event names with zero collisions.
- **Nested env binding actually works.** Executed with `env_nested_max_split=1`:
  `DEVICECHECK_PRIVATE_KEY_PATH`, `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`,
  `APP_STORE_ROOT_CERTIFICATE_PATH`, `APP_STORE_APP_APPLE_ID` and `JWT_JWKS_CACHE_TTL_SECONDS` all
  resolve, so no multi-underscore leaf is silently unconfigurable.
- **Both `JWTVerifier` builders' single-exception guards hold.** `__init__` converts every non-PyJWT
  warm-up failure (`JSONDecodeError`, `AttributeError`, `ValueError` from a malformed URL) into
  `PyJWKClientError`, so `build_google_push_verifier`'s `except PyJWTError` cannot leak and
  crashloop the pod.
- **`PyJWKClient.get_signing_key` refreshes the JWKS before raising the definitive-miss error**, so
  the negative `kid` cache cannot black-hole a freshly rotated Google key.
- **Every route carries an auth or verifier declaration.** `main.py` includes seven routers; the
  provider-callback partition, verifier-at-index-0 ordering, verifier-before-`get_db` ordering, and
  the exactly-`/health/ready` public allowlist are all asserted structurally in
  `tests/unit/test_app_wiring.py`.
- `ruff check src tests` clean; `ty check src` reports the documented 3 baseline diagnostics (all
  `dict.get` narrowing noise in `devicecheck.py:127` and friends), not new ones.

One thing I considered and deliberately did **not** file: with `enable_online_checks=False`, the
App Store library derives the chain-validity instant from the payload's own *unverified* `signedDate`
(`signed_data_verifier.py:172-174`) and performs no OCSP check, so an expired or revoked Apple leaf
key could be replayed with a backdated `signedDate`. Exploiting it requires possession of an
Apple-PKI-issued signing key; per AGENTS.md's threat model that is over-engineering, and the fix
(`enable_online_checks=True`) would put a network call on the admission path the code deliberately
keeps I/O-free.

**R2 — crud, tables, schemas, migration DDL**

I read the migration DDL line by line and diffed every mapped column in `tables/` against it
(type, nullability, default, uniqueness, enum name, FK target). I traced tenant scoping through
every read and write in `crud/`, the two-tier lock order shared by `GrantsDB` and `SubscriptionsDB`,
and the CAS predicate in `claim_subscription_owner`.

**Verified clean, specifically.** Tenant scoping: every `ChatsDB` method (`get_chat`, `count_chats`,
`list_chats`, `get_messages`, `delete`) filters on `user_id`, and `get_messages` reaches `Chat` by an
inner join so a foreign `chat_id` returns empty rather than another user's rows; every `GrantsDB`
statement filters on `user_id`; `PurchasesDB.read_tokens` filters on `user_id`; every one of those
values is server-derived from `LinkedIdentity`, never a body or query field. Column conformance: all
five enum types are pinned by `name=`/`schema=` to the pre-existing PostgreSQL types and their member
lists match the DDL exactly; the three `unique=True` fields (`AuthChallenge.challenge_id`,
`ExternalIdentity.user_id`, `SubscriptionEvent.notification_uuid`) each match a DDL `UNIQUE`, and
every field the DDL keys by a *composite* rule correctly declines `unique=True`; the four generated
`STORED` columns are deliberately unmapped. Referential actions: the migration carries exactly the
four `ON DELETE CASCADE` edges plus the one `ON DELETE RESTRICT` that `00-schema.md:621` enumerates,
and no more. Locking: `lock_active_grants` is a superset of `lock_effective_grants`, so both writers
take the same grant-row set ascending by id before any usage row — the two do not take a second lock
tier in conflicting orders. `SQLModel.exec()` returns a raw `CursorResult` for the `delete()` in
`ChatsDB.delete` and the `update()` in `claim_subscription_owner`, so `.rowcount` is real on both.
Response-body secrets: `MeResponse.purchase_tokens` is the only account metadata on the wire and is
spec-mandated; no store proof, JWT, device attestation, challenge subject or `resolved_token_value`
reaches any response model.

**What I found is thin.** One latent write bug in `tables/chats.py` (proven empirically) and five
quality items. I dropped seven candidate findings against ratified decisions or binding-spec text.

**R3 — routers and services**

I read all 14 assigned files in full and traced every handler's subject back to its source.
**The phase's own endpoint, `GET /users/me`, is clean and I found nothing to file against it.**
I verified it line by line against `04-users-me.md` and `SHARED-INVARIANTS.md`: the subject is
`identity.user.id` taken from `get_linked_identity` and from nowhere else; the route accepts no
path, query, body or header input at all, so no client-supplied signal can change which tokens are
read (brief §3); `identity_provider` comes from the stored `core.external_identities.provider`
column via the barrier's row, the same source `/auth/sync` uses (Phase 38 D-06); `PurchasesDB.read_tokens`
scopes on `user_id` alone with no lock and mints nothing; the completeness check is against the
`PurchaseProvider` enum and fails closed as an internal 500 that never reaches the client
(`ErrorResponse` carries only `code`); `Cache-Control: no-store` is set on the injected `Response`
before the typed model returns; the barrier chain `get_linked_identity` → `get_identity` →
`IdentitiesDB.resolve` rejects pre-auth (403 `preauth_identity_not_allowed`), historical and blocked
(403 `account_unavailable`) and orphan-user (500 `IdentityUnresolvable`), which is exactly the brief's
taxonomy; the tokens really are minted eagerly in `IdentitiesDB.insert_account:118-122`, so the
fail-closed branch is a genuine invariant tripwire and not a routine 500; and nothing on the path
writes a row or logs the token (`MissingPurchaseTokenError` carries `user_id` and store names only).

Also verified clean across the slice: **every** handler in `routers/` derives its subject from the
authenticated dependency — `chats.py` passes `identity.user.id` into crud calls that all carry a
`user_id` predicate (`ChatsDB.get_chat`, `get_messages`, `list_chats`, `delete`), so there is no
cross-tenant read anywhere; `chat_id` is never trusted alone. `routers/webhooks.py` correctly orders
its parameters so verification (and the Play network read) completes before `get_db` opens a session.
No secret reaches a log line: every `logger` call in the slice carries only closed-set labels, row
ids, branch names or exception class names — the challenge handle, the DeviceCheck token, the store
proof and the attribution token are all forwarded untouched and never logged. Error-to-status mapping
is consistent, and `class_answering_status` resolves exactly one class per framework status because
`vars(cls)` excludes inherited `answers_framework_status`. I found no unawaited coroutine
(`verify_binding` and `ChatService.get_examples` are the only sync calls and both are `def`), no bare
`except:`, no mutable default argument and no `eval`. `ty check src` reports 3 diagnostics, none in
my files.

The three warnings below are all in the store/quota business logic, not in the phase endpoint.

**R4 — deployment, packaging, configuration**

I reviewed the deployment, packaging and configuration surface at standard depth. I found no
Critical defect and I will not manufacture one: the auth-relevant parts of this slice hold up.

Traced and VERIFIED CLEAN:

- **Route coverage.** I enumerated all 19 registered paths (`grep '@router\.' src/nativespeaker/api/routers/*.py`):
  `/`, `/auth/*` (8), `/chats*` (5), `/examples`, `/users/me`, `/webhooks/app-store`,
  `/webhooks/google-play/rtdn`, `/health/ready`. Every one is matched by exactly one HTTPRoute.
  Nothing is left unrouted and nothing authenticated is left off the SecurityPolicy: `security-policy.yaml:9-15`
  targets `app-routes` (which covers `/users`, so phase 39's `GET /users/me` is inside it) and
  `auth-routes`; only `webhook-routes` and `health-routes` sit outside, both deliberately, both with
  their own in-backend credential. `docs_url`/`redoc_url`/`openapi_url` are `None` (`main.py:27-29`),
  so no unrouted doc surface exists either.
- **`.env.example` variable names actually work.** `BaseConfig` sets `env_nested_max_split=1`, which
  made every two-underscore name (`APP_STORE_BUNDLE_ID`, `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT_EMAIL`,
  `DEVICECHECK_PRIVATE_KEY_PATH`, `JWT_API_KEY`) look like it would mis-split. I booted the loader
  with all of them set: all land on the right field. No documented variable is dead.
- **`config.yaml`'s own precedence claim (`:24-25`).** Verified empirically — with `LOG_LEVEL=DEBUG`,
  `CHATS_LIMIT=7` and `DB_POOL_SIZE=20` in the environment the loader still returned `INFO`, `50`
  and `12`. The comment is accurate. (It is also the basis of IN-63.)
- **`uv.lock` vs `pyproject.toml`.** Consistent: `requires-dist` matches every specifier, `ruff` and
  `ty` are gone from the runtime set and present only under `requires-dev`, and `starlette`,
  `sqlalchemy`, `google-auth` and `httpx` are all recorded as direct project dependencies.
- **No committed secret.** `.env.example` carries placeholders only; `.gitignore:13-23` ignores
  `.env`, `.env.*` (with `!.env.example` correctly re-including it), `*.p8`, `*.pem`, `*.key` and the
  ADC JSON. The only tracked credential-shaped files are the three public Apple root `.cer`s.
- **The unconditional `DEVICECHECK_PRIVATE_KEY_PATH` (`deployment.yaml:73-74`) is safe** when no
  Secret is mounted: `read_private_key` (`auth/devicecheck.py:54-62`) returns `None` on a missing
  file, which is the documented fail-closed 503.
- **Secret mount permissions work.** `fsGroup: 1000` adds gid 1000 as a supplementary group, so the
  `defaultMode: 0440` root:1000 files are readable by `runAsUser: 1000`, and the Dockerfile's
  `useradd -m -u 1000` matches.
- **Liveness sharing the readiness path is harmless here** — `/health/ready` returns a static
  `{"status":"up"}` (`routers/health.py:10-11`) with no dependency check, so a database blip cannot
  produce a restart storm.
- **Deleted templates.** Grepping `k8s/` and `values.yaml` for `llm-routes`, `backend-traffic`,
  `BackendTrafficPolicy`, `rateLimit` and `responseOverride` leaves exactly two hits:
  `NOTES.txt:14`, which deliberately documents the removal, and `httproute-auth.yaml:11`, which is
  stale (IN-62).

One item I could not settle statically and am not filing: `security-policy.yaml` relies on Envoy
Gateway translating the JWT provider with `Forward: true`. Envoy's own `JwtProvider.forward`
defaults to `false`, which strips the token; if Envoy Gateway ever stopped forcing it, every
authenticated request would reach the backend with no `Authorization` header. SHARED-INVARIANTS
already asserts the forwarding behaviour, so this is a note for the operator, not a finding.

**R5 — unit test suite**

I read all 51 assigned unit-test modules in full and cross-read the production modules each drives
(`routers/users.py`, `crud/purchases.py`, `crud/chats.py`, `auth/app_store.py`, `logs.py`,
`services/auth.py`, `crud/identities.py`). The suite is unusually strong: nearly every structural
walk carries an explicit "the walk fires" control, refusal families are asserted by body equality
rather than status alone, and the doubles run the real production writer where a restatement would
drift (`test_subscription_attribution.py:169-176` is the model). Security-relevant properties I
confirmed **are** covered: the `/users/me` read is keyed on the barrier-resolved caller by bound
value, not merely by predicate text (`test_users_me.py:253-259`, `test_purchases_crud.py:149-157`);
store tokens are absent from the 500 body and from `MissingPurchaseTokenError`'s message
(`test_users_me.py:319-321`, `test_purchases_crud.py:111-117`); `/users/me` is asserted to declare
`get_linked_identity` and to be in neither exemption set (`test_app_wiring.py:82-90`); the response
body is byte-identical across five client-supplied signals (`test_users_me.py:270-281`); and
`Cache-Control: no-store` is asserted on the success arm (`test_users_me.py:226-230`). Cross-tenant
scoping on grants and usage is asserted by bound value in `test_sync_resolver.py:636-654`. The three
findings below are all guard-strength defects, not behaviour defects: one test that exercises no
production code at all while two ratified summaries cite it as proof, one structural tripwire that
matches identifier spellings the code under test never uses, and one test name that promises a
header property it never asserts.

**R6 — e2e and schema test suites**

I read all 28 files, then executed `tests/schema` (249 passed, 30 s), each race module standalone,
and the five concurrency modules three times in a row (108 passed, ~18 s each run) — no flake.
Every file in both suites carries `pytestmark = pytest.mark.e2e` / `pytest.mark.schema`, and
`timing` is a registered marker, so nothing in my slice is silently uncollected. I traced each
`tests/schema` race by hand and confirmed the interleavings are real, not simulated: the two
first-claim races hold both attempts at `before_first_flush` and record `grants_seen_at_barrier ==
[0, 0]` as an explicit premise; the conversion race holds at `before_first_commit` (which
`AuthService._complete` reaches immediately after the challenge claim, before any grant read) and
would go red if the `FOR UPDATE` were removed, because both attempts would then write and
`role_by_writes` would bucket them both as `won`; the restore race holds at the conditional owner
`UPDATE`, which is the sole arbiter; `test_grant_locks` issues production's *compiled* statement
(`_effective_grants_statement(...).with_for_update()`) rather than a transcription, so a lost
`FOR UPDATE` fails `TestTheGrantLockExcludes` and `TestTheIssuedStatementsAreProductionsOwn`
together. Security-relevant properties I confirmed **are** covered: cross-tenant grant scoping
(`test_quota.py:432-446`, `test_restore_race.py:404-418` owner-mismatch FK); the shared authorization
barrier answering identically on `/auth/sync` and `/auth/sign-out-all` for all five rejection states
with byte-equal bodies (`test_sign_out_all.py:268-292`); secrets absent from log records for the
sign-out subject and `provider_uid`, both webhook envelopes, both attribution tokens, the store
token and the Google purchase token (`test_sign_out_all.py:315-343`,
`test_app_store_webhook.py:579-588`, `test_google_play_webhook.py:586-595`), each with a positive
control proving the walk saw records; and the full Pub/Sub push-credential refusal matrix — absent
header, non-JWT, foreign key, wrong service account, `email_verified: false`, wrong `aud`, wrong
`iss`, expired, empty `sub`, foreign package (`test_google_play_webhook.py:198-211`). The defects
below are all test-reliability, not correctness: no Critical.

## Narrative Findings (AI reviewer)

Finding IDs are globally unique across the six slices. No structural (fallow) pre-pass ran —
`workflow.code_review_fallow` is disabled — so there is no `## Structural Findings` section.

## Warnings

### WR-01: an attributes-only Pub/Sub push is logged at ERROR as `google_play_message_out_of_range`

**File:** `src/nativespeaker/api/auth/google_play.py:134-139`
**Issue:** `developer_notification_from` collapses two unrelated conditions into one arm:

```python
if not data or len(data) > PUBSUB_DATA_LIMIT:
    logger.error("google_play_message_out_of_range", length=len(data))
    return None
```

`PubSubPushMessage.data` defaults to `""` precisely so that an attributes-only push — which
`schemas/webhooks.py:32-33` and 37.5 WR-63 both record as a *shape Cloud Pub/Sub permits* and which
the Cloud Console's "Publish message" with an empty body sends — is acknowledged rather than
retried forever. That legitimate delivery now emits the highest severity this service produces,
under an event name asserting a bound was exceeded, with `length=0`. `unhandled_exception` and
`jwks_endpoint_unreachable` sit at the same level; an operator alerting on ERROR gets paged by a
routine console publish. `tests/unit/test_models.py:372-375` parametrises `["", "a"*(LIMIT+1)]`
through one case named "out_of_range", so nothing catches the mislabel.
**Fix:** split the arms and give the empty case its own, honest, non-alerting event:

```python
if not data:
    # Pub/Sub permits an attributes-only message; it carries no RTDN and is acknowledged.
    logger.info("google_play_message_without_data")
    return None
if len(data) > PUBSUB_DATA_LIMIT:
    logger.error("google_play_message_out_of_range", length=len(data))
    return None
```

Add a unit case asserting the empty body logs at INFO under the new name and the oversized body
still logs at ERROR under the old one, so the two stop being interchangeable.

### WR-02: the stale-success guard in `CircuitBreaker` only holds while the breaker is open

**File:** `src/nativespeaker/api/resilience.py:61-67` (with `before_call`, `:49-59`)
**Issue:** `record_success` states the invariant it means to enforce —

```python
if self._opened_at is not None:
    # An attempt in flight when the breaker tripped predates it, so its answer says
    # nothing about the provider now. Only `before_call`'s elapsed arm closes this.
    return
self._failure_count = 0
```

but the test it uses is "is the breaker open *right now*", not "did this attempt predate the trip".
Once `before_call`'s elapsed arm has reset `_opened_at` to `None`, a success from an attempt admitted
*before* the trip takes the second branch and zeroes a failure count accumulated entirely after the
reset, delaying the reopen by up to `failure_threshold` further failures. This is reachable on the
shipped defaults: one `ainvoke` retry chain can run `3 × timeout_seconds (30) + backoff` ≈ 98 s,
which outlives `circuit_breaker_reset_seconds = 60`. The consequence is a breaker that stays closed
through a provider outage longer than configured — the opposite of what the guard was written for,
and invisible because the comment asserts the property is held.
**Fix:** stamp the generation rather than reading the current state:

```python
def __init__(...):
    ...
    self._generation = 0

async def record_failure(self) -> None:
    async with self._lock:
        if self._opened_at is not None:
            return
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._opened_at = time.monotonic()
            self._generation += 1

async def current_generation(self) -> int:
    async with self._lock:
        return self._generation

async def record_success(self, generation: int) -> None:
    async with self._lock:
        # Stale by construction: this attempt was admitted before the breaker last opened.
        if generation != self._generation:
            return
        self._failure_count = 0
```

`attempt()` in `ainvoke` captures the generation next to its `before_call` and passes it back.
A regression test would open the breaker, let it reset, record two fresh failures, then deliver a
stale success and assert `_failure_count` is still 2.

### WR-03: `json_log_path` is a config field nothing reads, so setting it silently does nothing

**File:** `src/nativespeaker/api/config.py:132` (with `src/nativespeaker/api/logs.py:25-26`,
`src/nativespeaker/api/app/lifespan.py:122`)
**Issue:** `AppConfig` declares `json_log_path: str | None = Field(default=None, description="Path
for JSON log file output")`, but `setup_logging` takes only `(log_level, log_stream)` and `lifespan`
calls `setup_logging(log_level=config.log_level)`. I grepped `src/` and `tests/`: the identifier
appears in `config.py` and nowhere else — the `FileHandler` + `JSONRenderer` branch that once
consumed it is gone (it survives only in the archived v1.5 planning artifacts). Because `AppConfig`
inherits pydantic-settings' `extra="forbid"`, the field *is* accepted from `config.yaml` or
`JSON_LOG_PATH`, so an operator who sets it gets no error, no warning, and console-format lines on
stderr — while the field's own description promises JSON file output. In a cluster whose log
collector is configured for JSON that is a silent break, and it is exactly the class of divergence
the "fail closed / never a silent stand-in" discipline elsewhere in this codebase exists to prevent.
**Fix:** delete the field (preferred — it is dead weight, and AGENTS.md asks for less code, not
more), or restore the consumer. If deleting:

```python
# config.py — remove the field entirely
log_level: LogLevel = Field(default=LogLevel.INFO)  # type: ignore
```

and delete `JSON_LOG_PATH` from any deployment values that still set it. Whichever is chosen, a
test that asserts the config surface and `setup_logging`'s signature agree keeps them from drifting
apart again.

### WR-20: `Chat.id` mints no id, so a `Chat()` built without one inserts NULL

**File:** `src/nativespeaker/api/tables/chats.py:40`
**Issue:** Every other mapped table in the package mints its own primary key
(`Field(default_factory=uuid7, primary_key=True)` — `Message`, `AccessGrant`, `AuthChallenge`,
`Subscription`, `SubscriptionEvent`, `StorePurchase`, `ExternalIdentity`, `User`). `Chat` alone
declares `id: UUID = Field(primary_key=True)` with no default. SQLModel `table=True` models skip
Pydantic validation, so the missing value is not a `ValidationError` — I confirmed empirically that
`Chat(user_id=uuid4(), title='x')` constructs with `id = None`:

```
$ .venv/bin/python -c "from nativespeaker.api.tables import Chat; from uuid import uuid4; \
    print(repr(Chat(user_id=uuid4(), title='x').id))"
None
```

The flush then sends `NULL` to `id UUID PRIMARY KEY` (migration line 54) and raises a
`NotNullViolation`. That is an `IntegrityError` whose sqlstate is `23502`, so
`crud/violations.py:is_unique_violation` returns `False` and every writer's classification arm
re-raises it as an opaque 500 rather than a race. The one caller today,
`services/chats.py:94`, happens to pass `id=uuid4()` explicitly — which is also the only uuid4
identifier anywhere in the schema, against a package-wide uuid7 convention that `Message.id`'s
chronological ordering (`tables/chats.py:52-53`, `crud/chats.py:47`) actually depends on. The next
caller that constructs a `Chat` gets a 500 with no local sign of why.
**Fix:** Give the column the same factory every sibling has, and drop the now-redundant argument at
the call site:

```python
# src/nativespeaker/api/tables/chats.py
    id: UUID = Field(default_factory=uuid7, primary_key=True)

# src/nativespeaker/api/services/chats.py:94
        chat = Chat(user_id=user_id, title=phrase, lang=lang)
```

`uuid7` is already imported in `tables/chats.py:4`. Regression test: assert
`Chat.model_fields["id"].default_factory is uuid7` next to the existing control in
`tests/unit/test_tables_metadata.py::TestTheEntitlementTablesHoldNoSecondClock`, which already pins
the same property for `AccessGrant.id`.

### WR-40: The out-of-order guard is skipped when the pre-lock subscription read saw no row, letting a stale delivery re-grant a revoked subscription

**File:** `src/nativespeaker/api/services/subscriptions.py:84-86` (with the pre-lock read at `:51-52`)

**Issue:** `ingest` reads the canonical row at `:51` *before* any lock, then re-reads
`store_signed_at` under the grant locks at `:82` precisely because the earlier read is stale — the
comment at `:79-81` says so. But the guard that consumes it is gated on the stale value:

```python
if (stored is not None and settled_signed_at is not None
        and notification.signed_at is not None
        and notification.signed_at < settled_signed_at):
```

When the pre-lock read saw no row (`stored is None`) but a concurrent delivery for the same
`(provider, external_id)` committed one in the window, `settled_signed_at` is non-`None` and older
than nothing is compared: the `stored is not None` conjunct short-circuits and the guard never fires.
The owner check at `:68` does not catch this case when both deliveries carry the same buyer
(`settled_owner == owner`), and `read_event` at `:75` does not catch it either because the two
deliveries carry different `notification_uuid`s. Control then reaches
`upsert_subscription`, which re-reads the row with `populate_existing=True`, computes
`settled = (stored.tier_id, stored.status, stored.user_id) == (tier_id, status, owner)` as `False`,
and writes `stored.status = status` at `crud/subscriptions.py:241` — the older payload overwrites the
newer canonical status. `store_signed_at` is *not* moved backwards (`crud/subscriptions.py:228-229`
only advances), so nothing records that the row is now behind its own clock. If the older payload's
status is in `ENTITLED_STATUSES` and the newer one was `revoked`, `write_subscription_grant` then
inserts a fresh active subscription grant for a subscription the store already withdrew, and no
further delivery is guaranteed after a revoke.

**Fix:** re-read the entity under the locks and decide on that, rather than on the pre-lock object.
Replace the `read_signed_at` call with a `read_subscription` re-read and use it for both the guard
and `append_event`:

```python
settled = await self.subscriptions_db.read_subscription(notification.provider,
                                                        notification.external_id)
if (settled is not None and settled.store_signed_at is not None
        and notification.signed_at is not None
        and notification.signed_at < settled.store_signed_at):
    await self._settle(await self.subscriptions_db.append_event(
        subscription=settled,
        event_type=notification.event_type,
        notification_uuid=notification.notification_uuid,
        old_tier_id=settled.tier_id,
        new_tier_id=settled.tier_id,
        evaluated_at=self.evaluated_at), notification)
    logger.warning("store_notification_superseded", event_type=notification.event_type)
    await self.session.commit()
    return
```

A regression test that would catch it: commit a `revoked` notification with a late `signed_at` from a
second session *after* `ingest` has taken its pre-lock `read_subscription` (patch
`SubscriptionsDB.read_signed_at` to commit the rival row on first call), then assert
`core.subscriptions.status` is still `revoked` and that the buyer holds no effective grant.

### WR-41: The `no_effective_grant` 429 sends a `Retry-After` of up to 31 days, which a conforming client honours across a purchase

**File:** `src/nativespeaker/api/services/quota.py:44-59` (value derived at `:24-34`)

**Issue:** `charge` computes one `retry_after_seconds = seconds_until_rollover(evaluated_at)` and
sends it on both refusal branches. The comment at `:44-46` justifies reusing it on the
`no_effective_grant` branch with "neither an absent grant nor a spent one changes before the period
does." That premise is false for the absent-grant branch, and the code that falsifies it is in this
same review slice: `AuthService._claim_anonymous_grant`, `_claim_registered_grant` and
`RestoreService.restore` all insert a grant with `starts_at=self.evaluated_at`, which
`GrantsDB.lock_effective_grants`' shared predicate (`starts_at <= now`) reads as effective on the very
next request. Those routes landed in phases 41-44, after 37.2 WR-03 wrote that reasoning. Concretely:
a caller with no grant posts a chat on the 2nd of the month, receives `429` with
`Retry-After: 2505600`, then subscribes — and any client honouring the header refuses to send a
request for the next 29 days despite holding a paid, active entitlement.

The anti-oracle clause in `SHARED-INVARIANTS.md` § Errors ("Within a class, body, status, and copy
are identical across every triggering branch") forbids sending a *different* value per branch, and
the invariant only asks for the header "where computable" — so the fix must keep one shared value.

**Fix:** cap the shared value. A shorter `Retry-After` never grants anything — the exhausted-allowance
branch simply refuses again on the early retry — while the absent-grant branch stops stranding a
caller who has just paid:

```python
# One value for both branches, as the anti-oracle clause requires. Capped rather than the raw
# rollover: an absent grant becomes effective the instant a claim or a restore commits, so a
# month-long header strands a caller who has just paid. An early retry on the exhausted branch is
# refused again and grants nothing.
RETRY_AFTER_CEILING_SECONDS = 300

retry_after_seconds = min(seconds_until_rollover(evaluated_at), RETRY_AFTER_CEILING_SECONDS)
```

Regression test: assert `charge` on a user with no grant raises `QuotaExceededError` whose
`extra_headers()["Retry-After"]` equals the ceiling, and that the exhausted-allowance branch on the
same day returns the identical string (the anti-oracle property).

### WR-42: The chat and message caps are checked before a multi-second provider call and never re-checked, so concurrent requests overrun them and a concurrently deleted chat 500s on a charged credit

**File:** `src/nativespeaker/api/services/chats.py:90-109` and `:117-136`

**Issue:** in `create_chat` the sequence is `count_chats` (`:90`) → `session.commit()` (`:99`, which
deliberately ends the read transaction and returns the connection) → quota charge → `ask_llm` → insert
(`:106`) → commit (`:109`). The cap is read outside any lock and the row that would enforce it is
inserted seconds later, so `chats_limit` concurrent requests all observe `chats_count < chats_limit`
and all insert; the stored chat count exceeds the configured cap by the burst size. `send_message`
has the same shape at `:121` for `messages_limit`.

The same gap has a second, sharper consequence in `send_message`: `chat` is fetched at `:117`, the
transaction is closed at `:128`, and the two `Message` rows are appended at `:133-134` and flushed at
`:136`. A concurrent `DELETE /chats/{chat_id}` from the same user committing during the provider call
leaves those inserts pointing at a `core.chats` row that no longer exists — the
`core.messages.chat_id` foreign key raises, which is not an `AppError`, so it lands on
`generic_error_handler` as an opaque 500 *after* `QuotaService.charge` has already committed the
spent credit. `_commit_the_charged_write` logs it but the credit is gone.

**Fix:** re-assert both invariants in the transaction that writes. For the caps, re-count after the
provider call and before the insert, raising the same `ChatHistoryLimitError`. For the delete race,
re-read the chat by `(chat_id, user_id)` in `send_message` after the provider call and raise
`InvalidChatError(chat_id)` when it is gone, so the caller gets the same 404 it would have got a
moment earlier instead of a 500:

```python
        ai_message = await self.ask_llm(chat=chat, message=human_message, admitted=admitted)

    # Re-read in the transaction that writes: the chat could have been deleted across the
    # provider call, and the message inserts would then fail the foreign key as an opaque 500.
    if await self.chats_db.get_chat(chat_id, user_id) is None:
        raise InvalidChatError(chat_id)
```

### WR-60: No `.dockerignore`, so the real `.env` and the whole `.git` history are uploaded in every build context
**File:** `Dockerfile:1` (companion `.dockerignore` absent from the repository root)
**Issue:** The repository has no `.dockerignore` (`test -f .dockerignore` fails). Docker therefore
sends the entire working tree to the build daemon on every `docker build`, and that tree contains
`.env` — the one file holding the real DB password, the long-lived Google refresh token and the
DeviceCheck ids that `.env.example:43-46` calls "the one real, long-lived secret in this block" —
plus `.git/`, `.venv/` and `.planning/`. Nothing lands in an image layer today, because the
Dockerfile copies only `pyproject.toml`, `uv.lock`, `src` and `config` and never does `COPY . .`.
But the context transfer itself is the exposure the moment the builder is not local: `docker buildx`
against a remote builder, a shared BuildKit daemon, kaniko, or any hosted CI build ships those bytes
off the machine. It also means one careless future `COPY . .` bakes `.env` into a layer with no
other guard in the way.
**Fix:** Add `/home/init/native-speaker/ns-api-gateway/.dockerignore`:
```
.env
.env.*
!.env.example
*.p8
*.pem
*.key
application_default_credentials.json
.git/
.venv/
.planning/
.claude/
.gsd/
tests/
__pycache__/
*.egg-info/
.pytest_cache/
.ruff_cache/
htmlcov/
.coverage
```

### WR-61: The chart cannot attach its HTTPRoutes to a Gateway outside the release namespace, and the failure is silent
**File:** `k8s/values.yaml:44-45`; `k8s/templates/httproute-auth.yaml:9-10`; `k8s/templates/httproute-webhooks.yaml:9-10`
**Issue:** `values.yaml` exposes `gateway.name` but no `gateway.namespace`, and every `parentRefs`
entry in the chart omits `namespace`. Gateway API defaults an omitted `parentRefs[].namespace` to
the route's own namespace, so this chart can only ever attach to a Gateway named `eg-gateway` living
in `{{ .Values.namespace }}` (`native-speaker`). The common Envoy Gateway topology puts the Gateway
in a platform-owned namespace instead. When it does, the HTTPRoutes install successfully, `helm
install` reports success, both probes pass, and every request 404s at the gateway with nothing in
the application's logs — the only signal is the route's `Accepted=False` status condition, which
nobody reads on a green install. `httproute-auth.yaml` was added in this diff range (eb9c03a), so
`/auth/*` and `/` are newly exposed to this failure mode.
**Fix:** Add a namespace value and thread it through all four route templates.
```yaml
# k8s/values.yaml
gateway:
  name: eg-gateway
  # The Gateway's namespace. Empty means this release's own namespace; a Gateway in a
  # platform-owned namespace also needs that listener's `allowedRoutes.namespaces` to admit
  # this one, which is outside this chart.
  namespace: ""
```
```yaml
# each httproute-*.yaml
  parentRefs:
  - name: {{ .Values.gateway.name }}
    {{- with .Values.gateway.namespace }}
    namespace: {{ . }}
    {{- end }}
```

### WR-70: `test_request_id_bound_in_context` exercises no production code, and two ratified summaries cite it as the proof of request correlation

**File:** `tests/unit/test_logging.py:47-52`
**Issue:** The test binds a contextvar itself and reads it back:

```python
def test_request_id_bound_in_context():
    """Request correlation travels through contextvars, which is what carries it into every record."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-req-123")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "test-req-123"
```

It never constructs `RequestLoggingMiddleware`, never drives a request, and imports nothing from
`nativespeaker.api.logs` that it uses. It is a test of structlog's own API. Deleting
`request_id=str(uuid.uuid4())` — or the whole `bind_contextvars(...)` call — from
`src/nativespeaker/api/logs.py:71-75` leaves it green, and `request_id` is named nowhere else in the
whole `tests/` tree (verified: `grep -rn "request_id" tests/` returns only these three lines).

The other seven assertions in this module that filter on `log["event"] == "request"` cannot cover the
gap either: `structlog.testing.capture_logs` does not merge contextvars. Verified empirically at HEAD
against structlog 25.5.0 — driving a request through the middleware under `capture_logs` yields a
record whose whole key set is `['duration_ms', 'event', 'log_level', 'status_code']`, with
`request_id`, `method` and `path` absent. So no existing test can see any of the three bound fields.

This matters because two ratified artifacts record this test as the evidence:
`.planning/phases/38-post-auth-sync/38-06-SUMMARY.md:139` lists it as the `ref:` for the bound
`request_id`, `:259` says "`test_request_id_bound_in_context` covers the bound `request_id`;
`method` and `path` are bound in the same `bind_contextvars` call", and
`.planning/phases/37.1-refactor-machine-generated-code/37.1-07-SUMMARY.md:210` calls it "precisely
the case that proves it". Phase 39's own D-10 (`39-CONTEXT.md:142`) then rests its no-log-redaction-test
decision on the same unproven premise: "`RequestLoggingMiddleware` emits only `request_id`, `method`,
`path` and `status_code`".

**Fix:** Drive the real middleware and read the context from inside a handler, which is the one place
the bindings are visible. Verified to work at HEAD (the three keys come back and `request_id` is a
fresh UUID per request):

```python
def test_the_middleware_binds_the_correlation_fields_onto_every_record(_logging_app):
    """capture_logs does not merge contextvars, so the bindings are read where they are set."""
    seen: list[dict] = []

    @_logging_app.get("/bound")
    async def _bound():
        seen.append(dict(structlog.contextvars.get_contextvars()))
        return {"ok": True}

    with TestClient(_logging_app) as client:
        client.get("/bound")
        client.get("/bound")

    assert [sorted(ctx) for ctx in seen] == [["method", "path", "request_id"]] * 2
    assert [ctx["method"] for ctx in seen] == ["GET", "GET"]
    assert [ctx["path"] for ctx in seen] == ["/bound", "/bound"]
    # A fresh id per request, or correlation groups two requests into one.
    assert uuid.UUID(seen[0]["request_id"]) != uuid.UUID(seen[1]["request_id"])
```

This does not contradict D-10, which declined a test asserting a *store token* is absent from a log
record on `/users/me`. This makes the positive claim D-10 leans on checkable.

### WR-71: the "never discriminated by message text" tripwire matches two spellings neither module under test uses

**File:** `tests/unit/test_conflict_classification.py:351-355`
**Issue:**

```python
def test_conflicts_are_never_discriminated_by_message_text(self):
    """Message text depends on the server's locale and would accept either rule naming the same table."""
    code = _code_only(_CREATION_SOURCE)
    assert "str(exc" not in code
    assert "str(e)" not in code
```

`_CREATION_SOURCE` (`:310-311`) is `services/auth.py` + `crud/identities.py`. Neither binds an
exception to `exc` or `e`. Read at HEAD: `crud/identities.py:127` and `:162` are
`except IntegrityError as conflict:`; `services/auth.py:233`, `:296` and `:408` are
`except AppError as failure:` / `except Exception as failure:`. So the exact regression this tripwire
exists to catch — a classifier that reads the driver's message text instead of the SQLSTATE — passes
it as `str(conflict)`, `str(failure)`, `f"{conflict}"`, `conflict.args[0]`, or
`"external_identities_issuer_subject" in str(conflict)`. The guard is a permanent structural
tripwire that cannot trip, sitting beside `is_unique_violation`, whose fail-closed behaviour is the
thing being protected (`test_restore_proof.py:955-971`).

**Fix:** Match on the syntax tree rather than on two literal substrings, so the check binds to *any*
exception name the module chooses:

```python
def _exception_names(tree: ast.AST) -> set[str]:
    """Every name an `except ... as NAME` clause binds anywhere in `tree`."""
    return {node.name for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler) and node.name}


def _reads_a_caught_message(tree: ast.AST, caught: set[str]) -> list[str]:
    """Every `str(caught)` call and every f-string interpolating one."""
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "str" and node.args
                and isinstance(node.args[0], ast.Name) and node.args[0].id in caught):
            found.append(f"str({node.args[0].id})")
        elif isinstance(node, ast.JoinedStr):
            found.extend(f"f-string on {inner.id}" for value in node.values
                         if isinstance(value, ast.FormattedValue)
                         for inner in ast.walk(value.value)
                         if isinstance(inner, ast.Name) and inner.id in caught)
    return found


def test_conflicts_are_never_discriminated_by_message_text(self):
    tree = ast.parse(_CREATION_SOURCE)
    caught = _exception_names(tree)
    # The control: the walk must find the handlers, or the check below reads nothing.
    assert caught >= {"conflict", "failure"}, caught
    assert _reads_a_caught_message(tree, caught) == []

def test_the_walk_sees_a_synthetic_message_read_control(self):
    tree = ast.parse("try:\n    pass\nexcept Exception as conflict:\n    x = str(conflict)\n")
    assert _reads_a_caught_message(tree, _exception_names(tree)) == ["str(conflict)"]
```

### WR-90: two quota cases discard the response, so each passes on the bug it names

**File:** `tests/e2e/test_quota.py:166`, `tests/e2e/test_quota.py:221`
**Issue:** `test_an_exhausted_grant_is_not_charged_for_the_request_it_refused` calls
`await async_client.post("/chats", json=PHRASE)` with the result discarded, then asserts only
`[row.monthly_used ...] == [ALLOWANCE]`. Any non-charging failure — a 500 from the fail-closed
missing-usage branch, a 401 from the barrier, a 503 from an open circuit — leaves the counter at
`ALLOWANCE` and greens the case, so it does not in fact prove that the request was *refused*, only
that something did not charge. `test_the_missing_usage_row_is_still_missing_afterwards` at :221 has
the identical shape (`assert await usage_rows(...) == []` would hold for a 401 too). This is exactly
the gap the same file closed elsewhere in this diff range: `TestTheOtherSixRoutesConsumeNothing`
gained an `expected` status per row with the comment "a 422 or a 403 spends nothing for a reason
this case is not about", and the two cases above were left behind.
**Fix:** capture and assert the status the case is about, as the sibling now does:
```python
        response = await async_client.post("/chats", json=PHRASE)

        assert response.status_code == 429, response.text
        assert response.json()["code"] == "quota_exceeded"
        rows = await usage_rows(_db_transaction, grant.id)
        assert [row.monthly_used for row in rows] == [ALLOWANCE]
```
and at :221, `assert response.status_code == 500` before the `== []`.

### WR-91: `_contended_challenge` does its risky setup outside the `try`, so a failure leaks an engine and a committed row

**File:** `tests/e2e/test_challenge_store.py:73-104`
**Issue:** The fixture builds `create_async_engine(config.db.url, pool_size=CONTENDERS + 2,
max_overflow=0)` at :75, then runs `await issue(factory, store, now=now)` (:77, which COMMITS a row
to the real application database) and `await asyncio.gather(*(contend() ...))` (:90) — all *before*
the `try:` at :92. Only the `yield` is inside it. If `issue()` raises (a DB error, a schema drift, a
constraint change), the `finally` never runs: the ten-connection pool is never `dispose()`d and the
committed challenge row is never swept. The fixture is function-scoped, so each of the three cases in
`TestTheClaimSerializesConcurrentAttempts` repeats the leak, and `max_overflow=0` means an exhausted
server-side connection budget then fails unrelated e2e modules for a reason that is not theirs. The
teardown comment already anticipates the row half ("a run interrupted before this block leaves its
row behind for good, and the next run is what has to sweep it") but the engine half has no such
sweep — nothing in the next run disposes a pool from the previous one.
**Fix:** open the `try` where the engine starts existing, which is the same rule
`google_linked_firebase_credential` in `tests/e2e/conftest.py:169-185` states for itself:
```python
    engine = create_async_engine(config.db.url, pool_size=CONTENDERS + 2, max_overflow=0)
    factory = async_sessionmaker(engine, class_=SQLModelAsyncSession, expire_on_commit=False)
    try:
        now = datetime.now(UTC)
        handle, _ = await issue(factory, store, now=now)
        barrier = asyncio.Barrier(CONTENDERS)
        ...
        results = await asyncio.gather(*(contend() for _ in range(CONTENDERS)),
                                       return_exceptions=True)
        yield handle, results, factory
    finally:
        async with factory() as session:
            await session.exec(delete(AuthChallenge)
                               .where(col(AuthChallenge.preauth_issuer) == ISSUER))
            await session.commit()
        await engine.dispose()
```

## Info

### IN-04: `PubSubPushTokens.verify` can stringify a null reason into the log

**File:** `src/nativespeaker/api/auth/google_play.py:223-225`
**Issue:** `raise NotificationRejected(stage=str(reason))` renders `None` as the literal string
`"None"` if `verify` ever returns `(None, None)` — the exact hazard `get_identity` guards against
one module over with `reason or BoundedReason.bad_signature` (`dependencies.py:80-83`), for the
stated reason that a null label is "a population the spike alert cannot name". `verify`'s current
arms all supply a reason, so this is latent rather than live, but the type signature
(`VerificationResult = tuple[VerifiedClaims | None, BoundedReason | None]`) permits it and the
sibling call site treats that as worth defending.
**Fix:** `raise NotificationRejected(stage=str(reason or BoundedReason.bad_signature))`, importing
`BoundedReason` alongside the existing `TokenVerifier` import.

### IN-05: `read()` omits the path-segment guard on `package_name` that `read_for_restore` applies

**File:** `src/nativespeaker/api/auth/google_play.py:242-254` (compare `:306-308`)
**Issue:** `read_for_restore` refuses an absent or dots-only `package_name` before `_get`;
`read` checks only `purchase_token`. On the RTDN path the package name is pinned to the configured
value by `dependencies.py:213-215`, so no caller can choose it — but a configured `package_name` of
`".."` is truthy, escapes the boot warning at `lifespan.py:163-164`, survives `quote(..., safe="")`
unescaped (quote never escapes a dot), and is then removed as a dot segment by httpx, addressing a
different Play URL. The hoisting comment at `:249-252` explains why the *purchase token* guard was
lifted to cover both entry points; the same argument applies to the sibling value and it was not.
**Fix:** hoist the second guard too, next to the credential check:

```python
if not package_name or not _names_one_path_segment(package_name):
    logger.error("google_play_unusable_package_name")
    return None
```

### IN-06: the ADC boot probe does not exercise the credential the Admin app will actually use

**File:** `src/nativespeaker/api/auth/firebase.py:48-60`
**Issue:** `_application_default_credential` calls `google.auth.default()` with **no scopes**,
discards the result, and returns `credentials.ApplicationDefault()`. That object resolves ADC a
second time, lazily and with Firebase's own `_scopes`, on the first Admin call
(`firebase_admin/credentials.py:171-173`). The probe therefore costs a duplicate ADC resolution
without proving the one that matters: `firebase_admin_credential_absent` can stay silent at boot
while every `getUser` still answers 503. The pod does not crashloop — I confirmed `initialize_app`
returns early from `_lookup_project_id` because `options["projectId"]` is set, and both `_read` and
`_revoke` catch `GoogleAuthError`, of which `DefaultCredentialsError` is a subclass — so this is a
diagnostics gap, not a crash.
**Fix:** drop the probe and let the returned object be the thing that is tested, e.g. call
`credential.get_credential()` inside the same `try` so the guarded call and the used call are one:

```python
credential = credentials.ApplicationDefault()
credential.get_credential()   # forces the scoped ADC resolution this app will use
```

### IN-07: the database password is rendered into a plain `str` where SQLAlchemy accepts a `URL`

**File:** `src/nativespeaker/api/config.py:36-44` (consumed at `app/lifespan.py:178`)
**Issue:** `DatabaseConfig.url` ends with `.render_as_string(hide_password=False)`, producing a bare
string that carries the secret and has none of `URL`'s repr protection. `create_async_engine`
accepts a `sqlalchemy.engine.URL` directly, so the round-trip through a cleartext string is
avoidable. The exposure today is small — `sqlalchemy.engine` is pinned to WARNING in
`_QUIETED_LIBRARIES` and `echo` is off — but the property "the password never exists as a plain
`str`" is cheap to hold and is the same discipline `SecretStr` is used for two lines above.
**Fix:** return the `URL` object and rename the property to say so:

```python
@property
def url(self) -> URL:
    return URL.create("postgresql+asyncpg", username=self.user,
                      password=self.password.get_secret_value(), host=self.host,
                      port=self.port, database=self.name)
```

`create_async_engine(config.db.url, ...)` needs no change.

### IN-08: `exc_info` is decided from the unclamped level while the log method comes from the clamped one

**File:** `src/nativespeaker/api/app/error_handlers.py:37-45`
**Issue:** `level` is clamped into `_LOGGABLE` (defaulting to `ERROR`) before the method is chosen,
but the traceback decision reads the raw field: `exc_info=exc if exc.log_level >= logging.ERROR else False`.
A class declaring an out-of-band level such as `25` would be *recorded* at ERROR and yet carry no
traceback — the one thing an ERROR record exists to supply. No class does this today (all nine
non-`None` levels are standard), so this is defensive-code inconsistency rather than a live bug.
**Fix:** read the same value both times — `exc_info=exc if level >= logging.ERROR else False`.

### IN-09: the definitive-`kid`-miss test is a substring match on a third-party English message

**File:** `src/nativespeaker/api/auth/jwt_verifier.py:68, 217`
**Issue:** `_DEFINITIVE_KID_MISS = "Unable to find a signing key that matches"` is compared with
`in str(exc)` to decide whether a `PyJWKClientError` names a bogus key id worth negative-caching.
PyJWT reserves no stability guarantee for that sentence. If it is reworded in an upgrade, the
negative cache silently stops recording anything and every bogus-`kid` token again costs a full
JWKS refresh — which is the amplification the cache was added to remove. The failure is
degradation, not a bypass (the rejection itself is unchanged), and it is silent.
**Fix:** add a unit case that constructs the miss through the real `PyJWKClient` (or asserts against
the library's own message constant if one is exposed) so a wording change fails a named test rather
than quietly disarming the cache.

### IN-20: `Chat.human_messages` is dead code

**File:** `src/nativespeaker/api/tables/chats.py:60-62`
**Issue:** Nothing reads it. `grep -rn "human_messages" src tests` returns the definition and
nothing else; its sibling `ai_messages` has exactly one reader
(`services/chats.py:121`, the message-limit check). The `_chat_with_ai_messages` hits in
`tests/unit/test_quota_seam.py` are a helper name, not a use of either property.
**Fix:** Delete the property. If it is wanted as documentation of the symmetry, say so in a comment
on `ai_messages` rather than keeping an unread code path on a mapped table.

### IN-21: `PubSubPushRequest.subscription` is validated and read by nothing

**File:** `src/nativespeaker/api/schemas/webhooks.py:40`
**Issue:** No code reads `body.subscription` — I grepped `\.subscription\b` across `src` and `tests`
and every hit is `AccessGrantSource.subscription` or a product id. The file's own comment on the
removed `messageId` field (lines 22-26) sets the rule this field breaks: a declared field
"made an envelope shape change a permanent 422 in exchange for validating a value the service never
used", and this route is on the Pub/Sub push path where a 422 is redelivered until retention
expires. `str | None = None` tolerates an absent field but still refuses a non-string one, which is
the same trade the `messageId` decision rejected.
**Fix:** Drop the field. Pydantic ignores what is not declared, so a delivery still carrying
`subscription` is unaffected — exactly the argument lines 22-26 already make.

### IN-22: `count_chats` is the one crud query that skips `col()`, and its return type is unchecked

**File:** `src/nativespeaker/api/crud/chats.py:26-28`
**Issue:** Two small inconsistencies in three lines. `where(Chat.user_id == user_id)` is the only
predicate in the whole `crud` package that does not wrap the column in `col()`; every sibling in
this same file does (lines 22, 34, 44, 54). And the method is annotated `-> int` while
`session.scalar()` is typed `Any | None`, so the annotation is asserted rather than checked —
`services/chats.py:90` then compares the result against `chats_limit`, which would be a `TypeError`
if it were ever `None`. It cannot be, because `select(func.count()).select_from(...)` always yields
one row, so this is a readability item and not a live bug.
**Fix:**

```python
    async def count_chats(self, user_id: UUID) -> int:
        statement = select(func.count()).select_from(Chat).where(col(Chat.user_id) == user_id)
        # `func.count()` over a `select_from` always yields exactly one row, so this is never None.
        return (await self.session.exec(statement)).one()
```

### IN-23: `MessageResponse.role` is a bare `str` where `ChatRole` exists

**File:** `src/nativespeaker/api/schemas/api.py:36`
**Issue:** `role: str` is the one place a value backed by a native PostgreSQL enum crosses the wire
untyped. `ChatRole` (`tables/chats.py:13-16`) is a `StrEnum` with exactly two members and is what
the `core.messages.role` column stores, so the response model documents a wider contract than the
data can hold and the OpenAPI schema publishes `string` instead of an enum the client can switch on.
Compare `CompletionResponse.identity_provider: IdentityProvider` and
`MeResponse.purchase_tokens: dict[PurchaseProvider, str]` in `schemas/auth.py`, which both do type
the enum.
**Fix:** `role: ChatRole`, importing from `nativespeaker.api.tables.chats`. A `StrEnum` serialises to
the same JSON string, so no client sees a change.

### IN-24: `activate_anonymous_device_grant` takes usage locks on a path that can never write

**File:** `src/nativespeaker/api/crud/grants.py:157-159`
**Issue:** The loop locks a usage row for every effective grant, but every branch below it that can
be reached with a non-empty `grants` returns without writing: line 172 raises on `len(grants) > 1`,
line 175 returns `lost_race` on an anonymous grant, and line 178's `if grants or ...` returns
`refused` for everything else. So the locks the loop takes are never used by a write, and the
`None` return of `lock_usage` is discarded here while `SubscriptionsDB.lock_grants_of`
(`crud/subscriptions.py:93-96`) treats the same `None` as a broken invariant and raises
`MissingUsageRowError`. Two writers behind one written lock order answer a missing usage row two
different ways.
**Fix:** Either drop the loop and say in a comment that this writer only ever proceeds with
`grants == []`, so there is no second lock tier to take; or keep it for order symmetry and make the
`None` case raise, matching `lock_grants_of`:

```python
        for grant in grants:
            if await self.lock_usage(grant.id) is None:
                # Fail closed, as `SubscriptionsDB.lock_grants_of` does over the same set.
                raise MissingUsageRowError(grant.id)
```

`MissingUsageRowError` is already imported at line 13.

### IN-40: `/auth/sync` returns the same body as three sibling routes that all set `Cache-Control: no-store`, and sets no header

**File:** `src/nativespeaker/api/routers/auth.py:183-192`

**Issue:** `claim_anonymous_grant` (`:128`), `claim_registered_grant` (`:151`) and
`restore_subscription` (`:179`) all return `SyncResponse` and all set `Cache-Control: no-store`;
`sync` returns the identical model and sets nothing. Phase 39 D-09 gives the reason for the header —
private account metadata that a private client cache would otherwise retain — and it applies verbatim
to the entitlement body. The risk is low because `/auth/sync` is a POST and POST responses are not
cached without explicit freshness information, so this is consistency rather than a live bug. I found
no ratified decision either way (no `Cache-Control` entry in the phase 36 or 38 records).

**Fix:** inject a `Response` and set the header, matching its three siblings.

```python
async def sync(response: Response,
               identity: LinkedIdentity = Depends(get_linked_identity),
               service: SyncService = Depends(get_sync_service)) -> SyncResponse:
    entitlement = await service.read_entitlement(identity.user.id)
    response.headers["Cache-Control"] = "no-store"
    return SyncResponse(entitlement=entitlement, identity_provider=identity.identity.provider)
```

### IN-41: `audit.subscription_events.old_tier_id` is written from the pre-lock read

**File:** `src/nativespeaker/api/services/subscriptions.py:53`

**Issue:** `old_tier_id = None if stored is None else stored.tier_id` is taken from the read at `:51`,
which the code itself treats as stale everywhere else (`:64-67`, `:79-83` both re-read under the
locks). The event row appended at `:154-160` can therefore record a `old_tier_id` that a concurrent
delivery already replaced, or `None` where a tier existed. It is an audit-accuracy defect only — no
entitlement decision reads the column — but it is the same staleness WR-40 makes exploitable.

**Fix:** fold into WR-40's re-read: take `old_tier_id` from the under-lock `read_subscription` result
rather than from the pre-lock object.

### IN-42: `list_chats` is the only handler in the slice without a return-type annotation

**File:** `src/nativespeaker/api/routers/chats.py:21-22`

**Issue:** every other handler in `routers/chats.py`, `users.py`, `examples.py` and `auth.py` carries
an explicit return annotation; `list_chats` carries only `response_model=list[ChatResponse]`, so the
type checker validates nothing about the list comprehension it returns. `routers/root.py::root` has
neither annotation nor `response_model`.

**Fix:** `async def list_chats(...) -> list[ChatResponse]:`.

### IN-43: A language configured with an empty example list is reported as unsupported

**File:** `src/nativespeaker/api/services/chats.py:168-172`

**Issue:** `get_examples` does `self.examples.get(lang, [])` and then `if not examples: raise
UnsupportedLanguageError(...)`, which conflates "this language is not in the configured map" with
"this language is configured but its list is empty". `supported_languages` (`:48-49`) is
`list(self.examples.keys())`, so such a language *is* advertised as supported by `GET /` and by the
error's own `supported` list, and then refused by `GET /examples`. The same file rejects exactly this
truthiness-vs-absence conflation at `:85-87` for `lang`.

**Fix:** test membership, not truthiness, so a configured-but-empty list returns an empty
`ExamplesResponse` rather than a 400 contradicting the advertised set:

```python
    def get_examples(self, lang: str) -> ExamplesResponse:
        # Membership, never truthiness: an advertised language with an empty list is not "unsupported".
        if lang not in self.examples:
            raise UnsupportedLanguageError(lang, self.supported_languages)
        return ExamplesResponse(lang=lang, examples=self.examples[lang])
```

### IN-62: `httproute-auth.yaml` still cites `llm-routes`, a template deleted in this diff range
**File:** `k8s/templates/httproute-auth.yaml:11`
**Issue:** The comment reads "Under the JWT SecurityPolicy, as app-routes and llm-routes are."
`k8s/templates/httproute-llm.yaml` was deleted by 918816e ("delete the duplicate llm-routes that
silently outranked app-routes"), and `security-policy.yaml:9-15` now names two targets, not three.
A reader chasing `llm-routes` finds nothing and cannot tell whether a template is missing.
**Fix:** `# Under the JWT SecurityPolicy, as app-routes is. Every route here carries a`

### IN-63: `config.yaml:1` breaks the rule `config.yaml:25` adds, and locks `log_level` for every deployment
**File:** `config/config.yaml:1` (rule at `:25`)
**Issue:** This diff adds the rule "Add a key here only when it must NOT vary per deployment." Line 1
declares `log_level: INFO`, which is precisely a value that must vary per deployment — and because
this file is `init_settings`, `LOG_LEVEL=DEBUG` in the k8s Secret is silently ignored (I verified
this: the loader returned `INFO`). An operator debugging an incident has no way to raise the level
without a new image. The same applies to `chats_limit` and `messages_limit`. Separately, 15 of the
17 keys in this file restate a `config.py` default verbatim — `model.*` (all three), `resilience.*`
(all nine), `jwt.jwks_cache_ttl_seconds`, `log_level`, `chats_limit`, `messages_limit` — so they buy
nothing and cost per-deployment overridability. Only `db.pool_size: 12` (ratified, D-16) and the two
product maps differ from a code default.
**Fix:** Delete the keys that only restate a `config.py` default, `log_level` first. The file then
holds what the rule says it should: the two tracked product catalogues and `db.pool_size` with its
comment.

### IN-64: `jwt.issuer` and the Secret's `JWT_PROJECT_ID` are the same fact in two places, with no check
**File:** `k8s/values.yaml:72-76`; `k8s/templates/security-policy.yaml:34`
**Issue:** The chart takes a whole issuer URL, while the backend derives its issuer from
`JWT_PROJECT_ID` (`config.py`, `JWTConfig.issuer`). Two operator-supplied values must spell the same
project id, in two different objects, and nothing compares them. A mismatch is not an auth bypass —
the backend is the authority and fails closed — but it refuses every genuine token, and depending on
which side is wrong the refusal is either Envoy's plain-text body (breaking the shared `{"code": ...}`
error contract for every request) or a blanket backend 401.
**Fix:** Take the project id once and derive the issuer in the template, so the value the operator
types is the same string on both sides:
```yaml
# values.yaml
jwt:
  # Must equal the Secret's JWT_PROJECT_ID: the backend derives its own issuer from that.
  projectId: ""
```
```yaml
# security-policy.yaml
      issuer: {{ printf "https://securetoken.google.com/%s" (required "jwt.projectId must be set, and must equal the Secret's JWT_PROJECT_ID" .Values.jwt.projectId) | quote }}
```

### IN-65: `pyproject.toml` is at 1.6.0 while the chart still declares appVersion 1.5.0
**File:** `pyproject.toml:3`
**Issue:** `version = "1.6.0"` here, but `k8s/Chart.yaml:6` still reads `appVersion: "1.5.0"`, and
`_helpers.tpl:30` renders that into `app.kubernetes.io/version` on every object. Every deployed
resource is labelled with the wrong application version, which is the label operators select on when
correlating an incident to a release.
**Fix:** Set `appVersion: "1.6.0"` in `k8s/Chart.yaml`, or drop the duplication and stop labelling a
version the chart cannot know (the real one is `image.tag`, supplied at install).
**Out-of-scope note for the orchestrator:** `k8s/Chart.yaml:3` is not in my file list but is stale
for the same reason as IN-62 — its description still reads "Linguistic analysis API with Envoy
Gateway rate limiting" after the BackendTrafficPolicy was deleted and `NOTES.txt:14` recorded that
no rate-limit policy ships in this chart.

### IN-66: `httpx` is declared twice, as a runtime dependency and as a dev dependency
**File:** `pyproject.toml:31` and `pyproject.toml:40`
**Issue:** This diff promoted `httpx >=0.28` into `[project] dependencies` but left the identical
entry in the `dev` group. `uv.lock` records it in both `requires-dist` and `requires-dev`. It is
harmless to resolution, but it tells the next reader that the test suite needs a version the runtime
does not, which is no longer true, and a future bump to one line and not the other is silent.
**Fix:** Delete line 40. The runtime declaration already covers the test client.

### IN-67: `Dockerfile:5-8` claims `uv` is the only unpinned build input, but the build backend is unpinned too
**File:** `pyproject.toml:47-49`; claim at `Dockerfile:5-8`
**Issue:** The comment added by 6f85be5 reads "`uv.lock` plus `--frozen` below pin every package and
`uv` itself is then the one input a rebuild of this commit can change." `uv.lock` does not lock
`[build-system].requires`, and `requires = ["setuptools"]` carries no specifier. `uv sync` builds
this project from source in an isolated environment and resolves `setuptools` fresh each time, so a
new setuptools release is a second input a rebuild of this commit can change — one that can alter or
break the produced wheel. (`setuptools>=82.0.1` in the `dev` group is a different thing and does not
constrain the build isolation environment.)
**Fix:** Pin the backend and correct the claim:
```toml
[build-system]
requires = ["setuptools>=82.0.1,<83"]
build-backend = "setuptools.build_meta"
```

### IN-68: the `/tmp` emptyDir has no `sizeLimit`
**File:** `k8s/templates/deployment.yaml:99-100`
**Issue:** `readOnlyRootFilesystem: true` makes `/tmp` the process's only writable path, and the
volume backing it is `emptyDir: {}` with no bound. An emptyDir with no `sizeLimit` draws from node
ephemeral storage without a ceiling, so a runaway temporary file evicts neighbouring pods on the
node rather than just this one. `resources` bounds cpu and memory but declares no
`ephemeral-storage` either.
**Fix:**
```yaml
      - name: tmp
        emptyDir:
          sizeLimit: 64Mi
```

### IN-72: the `/users/me` 500-arm case names a cache-header property it never asserts

**File:** `tests/unit/test_users_me.py:313-321`
**Issue:** `test_the_refusal_carries_no_cache_header_and_no_identifier` asserts only
`set(response.json()) == {"code"}` and that neither seeded token appears in `response.text`. Nothing
in it reads `response.headers`, so the "no cache header" half of its own name is unmeasured; the
docstring's "no user id, no provider name" is likewise unasserted directly (the sibling at `:305-311`
covers the body value by equality, so the identifiers are in fact safe). A reader auditing this route
against invariant 10 would count the header channel as covered when it is not. Verified at HEAD: the
refusal really does carry no cache header — the response is
`500 {'content-length': '25', 'content-type': 'application/json'} {"code":"internal_error"}` — so the
missing assertion would pass today and is a live regression guard rather than a new obligation.

**Fix:** Add the two assertions the name promises:

```python
@pytest.mark.parametrize("seeded", _INCOMPLETE_ACCOUNTS)
def test_the_refusal_carries_no_cache_header_and_no_identifier(self, identity, seeded):
    """The 500 body is the whole disclosure: no user id, no provider name, no token value."""
    with _client_for(identity, _RecordingSession(seeded)) as client:
        response = client.get("/users/me")

    # The handler sets `no-store` after the read, so a refusal reaches no header of its own.
    assert "cache-control" not in response.headers
    assert set(response.json()) == {"code"}
    assert str(identity.user.id) not in response.text
    assert APPLE_TOKEN not in response.text
    assert GOOGLE_TOKEN not in response.text
```

### IN-92: whole-table `count(*)` snapshots survive in two modules the rest of the suite scoped away from

**File:** `tests/schema/test_create_atomicity.py:198,199,231,235,284,285,303,309`;
`tests/e2e/test_sync.py:56-58`
**Issue:** `test_create_atomicity.py` captures `SELECT count(*) FROM core.users`,
`... core.store_purchase_tokens` and `... core.external_identities` unscoped and asserts equality
after. It is one of the eight modules that COMMIT into the session-scoped `ns_schema_test` scratch
database (37.4-REVIEW WR-43 names it in that list), and the fix pass that landed WR-43 covered
`test_apply_rollback.py` and `test_registration_pairing.py` only — this module was rewritten
substantially in this diff range and kept its unscoped reads. The same holds for
`tests/e2e/test_sync.py:56-58` `_TABLE_COUNTS`, which is the module `39-PATTERNS.md:595-617` copied
into `test_users_me.py`, where `39-REVIEW.md` IN-04 filed it and it is still open. These are
before/after *deltas*, so they are sound while pytest runs one process sequentially; they break under
`-n`, or under a second developer or reviewer against the same instance, and they break as a product
failure rather than as an infrastructure one. Filing at Info to match IN-04's tier, not to duplicate
it: this is the sibling occurrence inside my slice.
**Fix:** key each count to the rows the case owns, as `test_create_race.py:250-258` and
`test_registration_pairing.py:43-51` already do — e.g.
`SELECT count(*) FROM core.users u JOIN core.external_identities i ON i.user_id = u.id WHERE
i.issuer = :issuer` for the atomicity module, and
`SELECT (SELECT count(*) FROM core.access_grants WHERE user_id = :user_id), ...` for `_TABLE_COUNTS`.

### IN-93: no log-hygiene guard for `device_token`, the one client secret the two claim routes accept

**File:** `tests/e2e/test_claim_anonymous_grant.py:1-415`,
`tests/e2e/test_claim_registered_grant.py:1-576`
**Issue:** Three routes in this slice carry an explicit "no record carries a sensitive value" case
built on a `_LogSpy` over the modules that write records — `test_sign_out_all.py:315-343`,
`test_app_store_webhook.py:579-588`, `test_google_play_webhook.py:586-595`. The two claim routes
accept a client-supplied Apple DeviceCheck token in the request body and neither file installs a log
spy at all (`grep -n "LogSpy\|logger\|monkeypatch" ` over both returns nothing). I verified there is
no leak today: `src/nativespeaker/api/auth/devicecheck.py` contains no `logger.` call, no
`NotificationRejected`/`ProofRejected`/`RetryableDeviceCheckError` construction embeds the token,
and the refusal bodies are pinned as raw bytes (`REFUSED_BODY` at
`test_claim_registered_grant.py:38`), so the response-body half of the property *is* guarded. Only
the record half is unguarded, and it is the half a future `logger.warning("devicecheck_read_failed",
device_token=...)` would break silently.
**Fix:** add one case per claim module on the pattern already in the repository — spy on
`nativespeaker.api.app.error_handlers.logger` and `nativespeaker.api.services.auth.logger` at
`info`/`warning`/`error`, drive the arms that record (a rejected proof, an exhausted device, a
retry exhaustion), assert the recorded event set as a control, then
`assert DEVICE_TOKEN not in repr(records.entries)`.

## Dropped (ratified decisions)

Candidate findings each reviewer discarded because a ratified decision in
`.planning/REQUIREMENTS.md` or a phase decision record already settled the point. They are
recorded so a later pass does not re-file them.

**R1 — app wiring, auth adapters, top-level modules**

- Comma-joined, line-folded, and trailing-content `Authorization` values are not distinctly
  rejected as `duplicate_authorization`/`malformed` (`01-foundation.md` §1.1) — dropped per
  **37.4 D-10**: *"Comma-joined and line-folded values stop being distinctly rejected; they degrade
  to a signature failure"*, and **37.4 A-09**, which records `get_authorization_scheme_param`'s
  `param.strip()` loosening as the fifth flagged conflict.
- The Google replay key is the composite `google_play:{token}:{millis}:{type}` rather than the
  Pub/Sub message ID that `09-webhook-google-play-rtdn.md:24,41` mandates — dropped per **44 OQ-4**,
  chosen by the user at plan 44-01's blocking checkpoint and recorded as a flagged conflict in
  `44-07-SUMMARY.md:179`.
- The raw Play purchase token is persisted as `external_id` and embedded in
  `audit.subscription_events.notification_uuid`, against `09`'s *"No raw purchase tokens … persisted
  outside the minimum verification path"* — dropped per **44 D-10**, an explicit FLAGGED DIVERGENCE
  rated one-way.
- `_product_of` refusing `len(lineItems) != 1` with a 500 that Pub/Sub redelivers until retention —
  dropped per **44 REVIEW WR-08**, which prescribed this exact code (`44-REVIEW.md:482-500`).
- The log event `pre_auth_identity_not_allowed` diverges from the wire code and the spec's internal
  result `preauth_identity_not_allowed` — dropped per **37.3-02** / `STATE.md:644`: *"The log event
  pre_auth_identity_not_allowed diverges from the client code preauth_identity_not_allowed, by
  decision (37.3-02)"*.
- No startup route-enumeration assertion exists, against `01-foundation.md` §2.3 — dropped per
  **44 D-02/D-03**, which replaced it with `tests/unit/test_app_wiring.py` (*"The structural
  replacement for the deleted startup assertion"*).
- Both webhook routes are registered unconditionally and answer 503 when their integration is
  unconfigured, against `08`/`09`'s *"not registered at all while … unconfigured"* — dropped per the
  recorded flagged conflict in `44-07-SUMMARY.md:178` (*"the always-registered router answering
  503"*), inherited from phase 43.
- The webhook rejections carry the shared one-field JSON error body instead of plain status codes,
  against `08`/`09`'s *"never the shared client-visible error classes"* — dropped per the same
  recorded flagged conflict (`44-07-SUMMARY.md:178`, *"the shared one-field body"*).
- In-process rate limiting for the webhook and auth routes — dropped per `AGENTS.md`: Envoy Gateway
  rate-limits by IP, user and URL, and `08`/`09` name gateway limits only.

**R2 — crud, tables, schemas, migration DDL**

- `MeResponse.purchase_tokens` returns per-store attribution tokens in a response body —
  dropped per `specs/auth-refactor-phases/04-users-me.md` § "Fixed response shape" and phase 39 D-01/D-02:
  "always an entry for EVERY store provider with that store's token, for every existing user … the
  token is non-secret and confers nothing … returning it to an authenticated bearer is no privilege
  escalation (accepted risk)".
- `Profile.display_name` can never be non-NULL, since no code path writes `core.users.display_name` —
  dropped per `04-users-me.md` § "Explicit DELETIONS": "`display_name` never populated from auth
  context or the Admin record", and § 3: "If backend `display_name` is NULL the client may show an
  IDP-local name for presentation only".
- `core.subscriptions.restore_bound_user_id` is declared and written by nothing, while
  `specs/auth-refactor-phases/10-restore-subscription.md:49` makes it restore's *lifetime* replay
  protection ("Restore's replay protection is the lifetime `restore_bound_user_id` binding") —
  dropped per phase 45 D-10, `45-04-PLAN.md:177` ("D-10 replaces that column and nothing writes it")
  and `45-04-PLAN.md:262` (T-45-01: the one-move-per-UTC-month cap was accepted in its place on a
  sub-$5 subscription). REQUIREMENTS.md records the conflict against RESTORE-01 with line refs.
- `core.access_grants.subscription_id` carries no plain FK to `core.subscriptions(id)`, so a
  non-active subscription grant can hold a dangling id — dropped per
  `specs/auth-refactor-phases/00-schema.md:349`, whose authoritative DDL is `subscription_id UUID`
  with no `REFERENCES`; only the two generated columns carry deferred FKs.
- `audit.auth_events`, `core.access_grants_anti_abuse`, `core.provider_accounts`,
  `core.provider_account_gate_consumptions`, `core.auth_event_result`, `core.gate_consumption_kind`
  and `UNIQUE (id, source)` are absent from the migration although `00-schema.md:646` enumerates all
  of them in its "Final object inventory" — dropped per phase 37.1 D-01, recorded in
  `.planning/REQUIREMENTS.md:67-72` ("SCHEMA-06 — WITHDRAWN … no phase may assert anything about
  `audit.auth_events`").
- `core.auth_operation` lost `restore_subscription`, `sign_out_all` and `sync`, and the DDL CHECK
  pinning the challenge partition went with them, although `00-schema.md:190` still says the type
  "lists all seven state-changing operations" — dropped per phase 40 D-11, recorded verbatim in
  `.planning/REQUIREMENTS.md:61` as a forward flag with the accepted cost stated.
- The `tables/__init__.py:1-4` docstring's claim that "no field here declares one" reads as false
  against ~15 `foreign_key=` and three `unique=True` fields — dropped: `tests/unit/test_tables_metadata.py`
  defines the rule precisely as "no `index=True`" and "no FK with `ondelete`", and both assertions
  hold. The docstring means what the tests pin.

**R3 — routers and services**

- **No `users_me` backend rate-limit entry** — dropped per `39-CONTEXT.md` § "Carried forward" citing Phase 35 D-05: "deleted the backend `limits` engine **from the product, not deferred**"; `limits` is absent from `pyproject.toml` and there is no engine to register with.
- **`GET /users/me` writes no `audit.auth_events` row and increments no bounded-cardinality counter, despite `04-users-me.md` §"This phase adds"** — dropped per `39-CONTEXT.md` § "Carried forward": the table and its writer were deleted by Phase 37.1 D-01, § "Audit" was struck from `SHARED-INVARIANTS.md` by Phase 38 D-03, and the counter was removed by Phase 36 D-15.
- **No route registry and no startup route-enumeration assertion** — dropped per `39-CONTEXT.md` § "Carried forward": `auth/registry.py` was deleted by Phase 37.1 D-06 and Phase 37.5 turned the totality walk into `tests/unit/test_app_wiring.py`, which I confirmed does assert `/users/me` at `:70-80`.
- **`/users/me` has no `services/` class and the router calls `crud/` directly** — dropped per `39-CONTEXT.md` D-05: "a router may call `crud/` directly; a `services/` class is introduced when the router body would otherwise become too big or complicated."
- **`me()` reads the profile from the barrier's already-resolved `User` row instead of re-querying `core.users` as brief handler step 1 literally says** — dropped per `39-CONTEXT.md` D-03, which records it as a deliberate divergence: "The step is satisfied in substance: the row *was* loaded from `core.users`, by the barrier, in this request."
- **Both stores' tokens are returned unconditionally, with no platform branch** — dropped per `39-CONTEXT.md` D-02 / `REQUIREMENTS.md` PROF-01: "Not open — recorded here so a planner does not reopen it."
- **`MissingPurchaseTokenError` carries `user_id` into an ERROR log line** — dropped per `39-CONTEXT.md` D-06: "It carries `user_id` and the missing provider(s) — enough to find and repair the row… Neither value is the token."
- **`/auth/challenge` admits an unlinked caller, though `SHARED-INVARIANTS.md` § The barrier says "Only `POST /auth/create-user` … is pre-auth-callable"** — dropped: ratified as the second member of `PREAUTH_CALLABLE_PATHS` in `tests/unit/test_app_wiring.py:19`, and the handler narrows it to the `create_user` operation at `routers/auth.py:65-66`.
- **The registered-grant conversion arm reaches Apple not at all and leaves DeviceCheck `bit1` unset, so the device-level cap is not spent on that path** — dropped per Phase 42 `42-02-PLAN.md:76,387`: "the bit1 read then the bit1 write, on the new-grant arm only" and "the e2e conversion case asserts the DeviceCheck fake recorded zero reads and zero writes."
- **A quota credit spent on a request whose provider call then fails is not refunded** — dropped per the module docstring `services/quota.py:1-2`, which states the rule, and `services/chats.py:107-108`, which records the ordering it depends on.
- **No test asserts the purchase token never reaches a log line** — dropped per `39-CONTEXT.md` D-10: "no code path carries a response body into a log, so such a test would assert something no code attempts."
- **`POST /users/me` answers 405 to an unauthenticated caller, disclosing that the path exists** — dropped per the deliberate comment at `errors.py:107`: "The generic 405. It discloses only that the path exists."

**R4 — deployment, packaging, configuration**

- `addopts = "-v --tb=short -m 'not e2e and not schema'"` silently deselects the schema and e2e
  suites from a bare `pytest` — dropped per phase 34 plan 34-03 orchestrator DIRECTIVE-2
  (`.planning/phases/34-schema/34-03-PLAN.md:182`): "extend `addopts` from `-m 'not e2e'` to
  `-m 'not e2e and not schema'` ... The consequence is deliberate and binds every later verification
  command in this phase." (There is also no `.github/workflows` in this repository, so no CI run is
  being silently narrowed today.)
- `db: pool_size: 12` in the tracked `config.yaml` makes `DB_POOL_SIZE` permanently unreachable —
  dropped per D-16 / `.planning/phases/41-post-auth-claim-anonymous-grant/41-RESEARCH.md:415`:
  "Recommend the YAML block ... [the alternative] keeps `DB_POOL_SIZE` overridable from `.env`,
  which YAML would foreclose."
- `security-policy.yaml:28` `optional: true` lets a request carrying no `Authorization` reach the
  backend — dropped per commit c4a604c (37.5 WR-79) and SHARED-INVARIANTS' "defense-in-depth only;
  no backend correctness depends on it"; the backend answers the shared `401 {"code":"auth_required"}`.
- The SecurityPolicy injects no `claimToHeaders` — dropped per SHARED-INVARIANTS ("No claim-header
  authentication or header-derived identity") and commit ed99b1c (37 WR-04).
- No rate-limit policy ships in the chart, so nothing at the gateway answers 429 — dropped per
  commits 22ec7bf (37.1 WR-61), c7a3de4 (37.1 CR-61) and 971365e (37.4 WR-80), and per AGENTS.md:
  "Envoy Gateway ... rate-limits by IP, user, URL, etc." `NOTES.txt:14-24` documents the gap
  deliberately.
- `config.yaml` commits the `app_store.products` and `google_play.products` maps — dropped per
  `.planning/REQUIREMENTS.md:400` (D-16 amending 43 D-14): "only the catalogue is tracked in
  `config/config.yaml` — the three deployer values stay in the environment."
- `python:3.14-slim` is a moving tag, not a digest — dropped per commit 6f85be5 (37.5 WR-78) and the
  Dockerfile's own `:5-8` statement of the trade-off ("still moving, which is weaker but only ever
  moves the base OS, never the resolution").
- `.env.example:7,13` ships `DB_PASSWORD=postgres` — dropped: these are the local development
  defaults `docker-compose.yml:10-16` consumes, and commit 782a3a5 (36 WR-05) already bound that
  database to `127.0.0.1`.
- The very heavy prose comment register across `.env.example`, `values.yaml`, `deployment.yaml` and
  `NOTES.txt` against AGENTS.md's "Keep specs short" — dropped per commit c36fb57 (38 WR-05), which
  already ran a comment-register pass over this surface.

**R5 — unit test suite**

- **No unit test asserts a store token is absent from any log record on `/users/me`** — dropped per
  D-10, `.planning/phases/39-get-users-me/39-CONTEXT.md:142` and the "Log-redaction test" row of
  `39-DISCUSSION-LOG.md:151`: *"No test — current logging shape is proof… The redaction obligation is
  met instead by constraining `MissingPurchaseTokenError` never to carry `identity_value`"* — which
  `test_purchases_crud.py:111-117` does assert.
- **The two `@pytest.mark.timing` wall-clock cases in `tests/unit/test_jwks_offload.py:160,179` are
  not deselected by pyproject's `addopts` and so run in the default unit selection** — dropped per
  phase 38 WR-57, `.planning/phases/38-post-auth-sync/38-REVIEW-FIX.md:649-660`, which ratifies
  `-m "… and timing"` as the *reporting* mechanism rather than a deselection, and accepts the
  marked cases running in the ordinary suite.
- **The anonymous/registered claim's destination `user_id` is never asserted in the unit suite**
  (`_RecordingGrants.activate` at `tests/unit/test_claim_precedence.py:131-140` records
  `claim_platform` but discards `user_id`, and `_a_grant` mints rows under a random owner) — dropped:
  covered in the suite R6 owns, `tests/e2e/test_claim_anonymous_grant.py:90` reads back
  `select(AccessGrant).where(col(AccessGrant.user_id) == user.id)`.
- **`crud/chats.py`'s per-caller scoping (`get_chat`, `list_chats`, `get_messages`, `delete` all
  filter on `Chat.user_id`) is not asserted in `tests/unit/test_chats_crud.py`, which pins only the
  `ORDER BY`** — dropped: covered in R6's slice by `tests/e2e/test_isolation.py` and
  `tests/e2e/test_chats.py:77`.

**R6 — e2e and schema test suites**

- `seed_purchase_tokens(providers=PurchaseProvider)` defaults to the enum *class* rather than a
  sequence (`tests/e2e/conftest.py:656-658`) — dropped: already filed and still open as `IN-05` in
  `.planning/phases/39-get-users-me/39-REVIEW.md:411-418` ("`providers=PurchaseProvider` defaults to
  the enum *class*, which happens to be iterable").
- `_TABLE_COUNTS` in `tests/e2e/test_users_me.py` — dropped: out of slice by instruction, and already
  filed as `IN-04` in `39-REVIEW.md:396`.
- `tests/schema/test_constraints.py:123-136` re-implements `_insert_subscription` beside the new
  shared `schema.helpers.insert_subscription` — dropped per the reviewer instruction: "Do NOT file:
  naming, formatting, or duplication between test files."
- `google_linked_firebase_credential` errors instead of skipping when no Firebase Admin credential is
  configured, unlike its twin `anonymous_firebase_credential` — dropped per the fixture's own ratified
  comment at `tests/e2e/conftest.py:149`: "No skip and no guard: the three variables are supplied
  before the run, so an absent one is a broken environment."
- `tests/schema/test_apply_rollback.py` unscoped tier read — dropped: WR-43's fix record
  (`.planning/phases/37.4-.../37.4-REVIEW-FIX.md:488-508`) shows the case was scoped to the three
  seeded ids, and the current `TestSeededTiers` reads `WHERE id = ANY($1)`. Already resolved.
- Live-clock `datetime.now(UTC).strftime("%Y-%m")` comparisons across a request in `test_sync.py:107,
  137,169,187` and `test_quota.py` — dropped per the file's own ratified comment at
  `tests/e2e/test_sync.py:162-163`: "A live clock cannot be made to hit `ends_at` exactly; that
  boundary is proved deterministically against the compiled statement in
  tests/unit/test_sync_resolver.py."
- The deleted `TestTheEffectiveGrantStatement` in `tests/e2e/test_quota.py` (removed in this diff) —
  dropped as a coverage loss: the identical properties (`FOR UPDATE`, `ORDER BY ... id ASC`, the
  tenant term, no `LIMIT`) are now asserted against production's *compiled* statement in
  `tests/schema/test_grant_locks.py:52-77`, which is strictly stronger than the stub-session copy.

---

_Reviewed: 2026-09-09T21:50:37Z_
_Reviewer: Claude (gsd-code-reviewer x6, parallel split by module, merged)_
_Depth: standard_
