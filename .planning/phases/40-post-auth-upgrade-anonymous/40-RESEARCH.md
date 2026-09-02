# Phase 40: POST /auth/upgrade-anonymous - Research

**Researched:** 2026-09-02
**Domain:** In-repo endpoint work — FastAPI route + SQLModel/asyncpg identity flip + Firebase Admin `getUser` + PostgreSQL enum shrink
**Confidence:** HIGH (every load-bearing claim was read out of the installed source or executed against the live interpreter/database this session)

## Summary

This phase adds no library and invents no pattern. Every mechanism it needs — the challenge protocol, the
`getUser` read with its retry, the linked-identity barrier, the `IntegrityError`→typed-rejection idiom, the
scripted provider fake — is already shipped and was read line by line this session. Research therefore went
where the risk actually is: **verifying the twelve in-repo premises the CONTEXT file rests on.** Nine hold
exactly as written. **Three do not**, and each one changes the plan.

The three corrections, in descending cost:

1. **D-18 is broken today, not merely "awkward".** `firebase_admin.auth.create_custom_token` was executed
   against this machine's Application Default Credentials and **failed** — the ADC file is
   `type: "authorized_user"` (a `gcloud auth application-default login` session), which carries no signer, and
   the SDK's IAM fallback found no service account. D-18's success-path test cannot be written as specified
   without a credential change, and `.env.example` records that org policy `iam.disableServiceAccountKeyCreation`
   forbids minting a key here at all.
2. **D-11's fallout list is two files short.** `tests/schema/test_constraints.py:566` and
   `tests/unit/test_challenge_endpoint.py:123` both hardcode the three dropped enum labels and both break.
   D-11's sentence *"Nothing in `tests/schema/test_constraints.py` names that CHECK"* is true of the
   constraint's *name* and false of its *coverage*: a three-case class asserts the CHECK's behaviour.
3. **`NotLinked`'s `empty` cause does not exist.** D-01 says the bounded causes "stay `empty | invalid-shape`".
   `empty` has **zero producers** in `src/` — Phase 37.3 swept it when an empty `providerData` became the
   *anonymous* classification rather than a rejection. This phase writes the first `empty` producer in the
   repository, which makes it new code the vocabulary ratchet must be updated for, not a reuse.

Two further hazards were found that no decision anticipated, both about D-15's lock. PostgreSQL 17.11
**rejects** `FOR UPDATE` on the nullable side of an outer join (executed live), so the lock query cannot reuse
`IdentitiesDB.resolve`'s `isouter=True` shape. And `tests/unit/test_conflict_classification.py` scans the
combined source of `services/auth.py` **and** `crud/identities.py` for the literal `"for update"` and fails if
it appears — SQLAlchemy's `.with_for_update()` slips through by the letter (verified), raw SQL does not.

**Primary recommendation:** Plan the code exactly as the decisions specify; sequence the phase so the
credential question (D-18) is answered in Wave 0 by a probe rather than discovered in the test-writing wave;
and treat the enum shrink (D-11) as a five-file edit, not three.

## User Constraints (from CONTEXT.md)

### Locked Decisions

Copied from `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md` § Implementation Decisions.
The planner MUST honor these. Where research corrects a premise, the correction is flagged inline and the
decision itself is left intact.

- **D-01: There is no client-supplied target provider. The server derives it solely from the Firebase Admin
  providerData read.** Brief steps 3 and 4 dissolve. `operation_variant` stays deleted. `NotLinked`'s bounded
  causes stay `empty | invalid-shape` — *see § Premise Corrections P-03: `empty` currently has no producer.*
  The case matrix collapses to what the stored row and the live read say, with no third input.
- **D-02: A caller cannot distinguish a recoverable refusal from a terminal one, and that is deliberate.**
  All three refusals answer 403 `operation_not_allowed` with a one-field body. Operators tell them apart in
  the structured log (D-05).
- **D-03: The wire models are shared with create-user.** `CreateUserRequest` is renamed to a neutral name
  (planner's call) and both routes take it; `CompletionResponse` is reused unchanged.
- **D-04: A repeat call that changed nothing answers identically to one that performed the flip** — 200 with
  the same `{identity_provider}` body. No `changed` flag, no distinct status.
- **D-05: Three separate exception classes, not one class with a field.** Case 1 reuses the existing
  `NotLinked` (cause `empty`). Two new classes for cases 2 and 3; names are the planner's call but must
  snake-case to `provider_transition_not_allowed` and `provider_account_already_linked`.
- **D-06: The two new refusals log our identity row id plus the stored and live provider names.** The
  provider account uid is deliberately excluded.
- **D-07: All three refusals log at WARNING.**
- **D-08: The already-taken case is found by catching the database's refusal, not by checking first.** No
  constraint name is stored or compared and no error message is parsed.
- **D-09: Prepare is served by the existing `POST /auth/challenge`**, not by a `?challenge=true` mode. The
  challenge store needs no change at all.
- **D-10: A caller with no account asking for anything but create-user is rejected in the challenge handler,
  by one derived condition:** any operation other than `create_user` with `identity.identity is None` raises
  `PreAuthIdentityNotAllowed`. Rejected and not to be re-litigated: the rule in `ChallengesDB.issue`; a
  per-operation admission table; deriving the issuable set from FastAPI route metadata.
- **D-11: `core.auth_operation` is shrunk to its four challenge-bearing values**, so no issuable-operation
  list is written anywhere. The membership test becomes `body.operation not in AuthOperation`. The now-redundant
  `auth_challenges` CHECK is dropped. The single migration is edited in place and the dev/test database
  rebuilt. *See § Premise Corrections P-02: the fallout list is two files short.*
- **D-12: One crud method is the sole writer of both halves of the flip, backed by a schema-level test.**
  A test in `tests/schema/` scans for rows in the third state. Rejected: a runtime re-read and assertion.
- **D-13: The verified email is copied only when the stored email is still NULL.** A non-NULL stored value is
  never overwritten and a divergent live address is not a rejection. `display_name` is never populated.
- **D-14: The challenge is consumed on every outcome at or after the Firebase call**, including
  `provider_not_linked`. Rejections *before* the Firebase call neither claim nor consume.
- **D-15: The identity and user rows are locked and revalidated at the top of the completion transaction, but
  this phase does not test that the lock blocks.** Dropping the lock entirely was offered and declined.
- **D-16: The upgrade completion is added to the existing `AuthService`**, not given its own class. A separate
  service would copy the sequence; extracting a shared base was offered and declined.
- **D-17: No nested exception handling, and `try` blocks stay narrow.** A `try` contains only the statement
  that can raise. Where a failure must be swallowed, the swallow goes in a small named function.
  Create-user's existing nested block is not this phase's obligation.
- **D-18: A real, permanently Google-linked Firebase account covers the successful flip.** One Firebase user
  has a Google credential attached by hand, once; each run mints a custom token and exchanges it for an ID
  token. Two things to schedule rather than discover: someone creates the account by hand and records it; and
  minting custom tokens needs signing rights — **verify this early.** *See § Premise Corrections P-01: it was
  verified, and it fails today.*
- **D-19: The scripted fake covers everything the real account cannot produce on demand** — the not-yet-linked
  refusal, the drift conflict, the already-taken conflict, and the idempotent repeat.
- **D-20: One e2e flow test proves roadmap criteria 3 and 4.** Upgrade, then call `/users/me` and `/auth/sync`
  and confirm the new provider; read the purchase-attribution tokens either side and confirm they are identical.
- **D-21: Amend UPGRADE-01 and UPGRADE-02 in `.planning/REQUIREMENTS.md`** with a dated entry covering D-01,
  D-11 and D-22, and stating that the brief's rate-limit and audit obligations are already dead.
- **D-22: Record the accepted Firebase exposure explicitly** — every completion makes one `getUser`, a looping
  client is unbounded, accepted and flagged as Phase 37 D-01 did.
- **D-23: Note the enum shrink under SCHEMA-01.**
- **D-24: Reword ROADMAP.md Phase 40 success criterion 2.**
- **D-25: `specs/auth-refactor-phases/05-upgrade-anonymous.md` is NOT edited.**

**Carried forward — decided earlier, binding here, do NOT rebuild.** No `audit.auth_events` row and nothing to
write one with. No rate limiting of any kind. No `BudgetGate` and no `auth/budgets.py`. No mode-signal
partition. No route registry and no startup enumeration assertion. No incremental migration file. No new
client-visible error code. No success log line. No `provider_uid` mutation once set, no reverse flip, no
registered-to-registered rebinding, no auto-rewrite of a divergent binding.

### Claude's Discretion

- The names of the two new exception classes, subject to D-05's snake-case constraint, and where they sit in
  the tree in `errors.py`.
- The new neutral name for `CreateUserRequest` (D-03), and whether the rename lands in its own commit.
- The crud method's name and signature (D-12), and how the locked-and-revalidated rows reach it.
- How the lock-and-revalidate query is issued — one joined statement taking `FOR UPDATE` on both tables, or
  two ordered statements. *See § Common Pitfalls 1 and 2 — one of these two options has a hard constraint.*
- How `AuthService` accommodates the second completion (D-16); the constraint is that the shared sequence is
  not duplicated.
- Test placement and depth, within the existing `tests/unit` + `tests/e2e` + `tests/schema` split, and whether
  the enum shrink lands in its own commit.

### Deferred Ideas (OUT OF SCOPE)

- One test asserting each Python enum's values equal its `core.*` database type's labels.
- Cleaning up create-user's nested exception block to match D-17.
- Operator tooling for a drifted row.
- A real Google-linked account for a genuinely registered create-user flow (Phase 37's declined coverage).
- A second permanently anonymous Firebase account for the not-yet-linked refusal path.
- `PROJECT.md` § Constraints says Python 3.12; the environment runs 3.14.7.
- Restoring rate limiting to the auth surface.
- Secret Manager integration.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UPGRADE-01 | The endpoint records the client-side same-Firebase-UID `linkWithCredential` upgrade by flipping the existing `core.external_identities` row's provider in place [VERIFIED: .planning/REQUIREMENTS.md:235] | § Architecture Patterns 2 (the flip method) and 3 (case matrix); § Standard Stack (`with_for_update`, `IntegrityError`); § Common Pitfalls 1–4 |
| UPGRADE-02 | The endpoint is challenge-bearing with prepare and completion modes, callable only by an authenticated linked identity [VERIFIED: .planning/REQUIREMENTS.md:236] | § Architecture Patterns 1 (the shared completion sequence) and 4 (the issuance handler); § Integration Points (`get_linked_identity`, `PREAUTH_CALLABLE_PATHS`) |

## Project Constraints (from CLAUDE.md / AGENTS.md)

`/home/init/native-speaker/CLAUDE.md` is `@AGENTS.md`, which is
`/home/init/native-speaker/AGENTS.md` [VERIFIED: /home/init/native-speaker/AGENTS.md:1-10]:

- First version, startup, no users yet. Do not over-engineer for a theft threat model; do not skip normal
  security measures either.
- **Keep specs short: programming this app should not consume many tokens.**
- The app runs behind Envoy Gateway, which authenticates by JWT and rate-limits by IP, user, URL.

`/home/init/native-speaker/ns-api-gateway/AGENTS.md` binds the code [VERIFIED: ns-api-gateway/AGENTS.md:1-89]:

| Rule | Verbatim source | Consequence for this phase |
|---|---|---|
| Docstrings — three lines maximum | `:8` | Gated by `tests/unit/test_docstring_bar.py`, baseline **0 on every root** |
| Comments — only where necessary, one line each | `:17-22` | Same gate |
| `services/` = business logic, `crud/` = database access, `schemas/` = bodies, `tables/` = SQLModel, `routers/` = handlers `Depends()`-only, `auth/` = external-SDK seams only | `:29-36` | The flip query goes in `crud/identities.py`; the orchestration in `services/auth.py`; the request model in `schemas/auth.py` |
| A router may call `crud/` directly; a service is earned by complexity | `:38-42` | The completion is already a service; do not add a second one |
| `commit()`/`rollback()` are transaction boundaries and live in `services/`, not `crud/` | `:57-58` | The flip method must NOT commit |
| A fail-closed read may raise its own rejection, so the rejection stays with the query in `crud/` | `:59-60` | D-08's `IntegrityError` catch belongs in `crud/identities.py` |
| Delete a function that is only a step; keep one that states a rule or marks a boundary | `:64-66` | D-17's "small named function whose whole job is not raising" is a rule, so it stays |
| The `limits` library was overridden by Phase 35 D-05: the engine is deleted from the product, not deferred | `:86-88` | Confirms every rate-limit obligation in the brief is dead |

## Premise Corrections

The three CONTEXT premises that do not survive contact with the installed source. Each is stated with the
evidence and the plan consequence.

### P-01 — D-18's custom-token mint fails on this machine, today

D-18 says signing rights are *"the most likely thing to make D-18 awkward"* and *"verify this early."* Verified.

The ADC file this repo points at is a user credential, not a service account
[VERIFIED: executed `google.auth.default()` + read the file's `type` key this session]:

```
credential file type: authorized_user
has client_email: False
keys: ['account', 'client_id', 'client_secret', 'quota_project_id', 'refresh_token', 'type', 'universe_domain']
ADC class: Credentials   service_account_email attr: None
```

Minting a custom token through that credential raises
[VERIFIED: executed `firebase_admin.auth.create_custom_token("probe-uid", app=<ADC app>)` this session]:

```
FAILED: ValueError
Failed to determine service account: HTTPConnectionPool(host='metadata.google.internal', port=80): ...
Make sure to initialize the SDK with service account credentials or specify a service account ID
with iam.serviceAccounts.signBlob permission.
```

`firebase_admin` 7.3.0 is installed and `firebase_admin.auth.create_custom_token` exists
[VERIFIED: executed `import firebase_admin; firebase_admin.__version__` → `7.3.0`, `hasattr(auth,"create_custom_token")` → `True`]. The method exists; the *signer* does not.

`.env.example` records why a key cannot simply be minted [VERIFIED: ns-api-gateway/.env.example, verbatim]:
*"ADC is the only route on projects whose org policy sets `iam.disableServiceAccountKeyCreation` — as this one
does, so no service-account key can be minted here at all."*

**Three routes forward, for the planner to choose between — this is a Wave 0 decision, not a test-wave discovery:**

| Route | What it costs | What it keeps |
|---|---|---|
| (a) Grant the developer's ADC principal `roles/iam.serviceAccountTokenCreator` on a service account, and pass `serviceAccountId` in the test's own Admin app options | A GCP IAM change outside this repo, plus a **second** Admin app built in the test (production `build_admin_apps` passes only `{"projectId", "httpTimeout"}` [VERIFIED: src/nativespeaker/api/auth/firebase.py:40-44], so it cannot carry `serviceAccountId`) | D-18 exactly as written |
| (b) Mint the ID token locally with the ephemeral-RSA verifier and let only `getUser` hit real Firebase | `_FixedKeyVerifier` hardcodes `TEST_ISSUER = f"https://securetoken.google.com/{TEST_PROJECT_ID}"` with `TEST_PROJECT_ID = "test-project"` [VERIFIED: tests/unit/conftest.py:32-33], which is **not** the configured issuer, and `FirebaseAdminLookup.get_user_provider_data` selects its app by exactly that issuer [VERIFIED: src/nativespeaker/api/auth/firebase.py:66-69] — so a parameterized variant of `make_test_verifier()` is needed | The real `getUser` against the real Google-linked account, with **zero** credential work |
| (c) Skip the test when signing is unavailable, exactly as `anonymous_firebase_credential` already skips [VERIFIED: tests/e2e/conftest.py:79-80] | D-18's success-path coverage is aspirational until someone fixes credentials | Nothing breaks; the suite stays green |

Note (b) does not weaken D-18's stated purpose. D-18's own reasoning is that the fake cannot prove the *shape*
of a real Google `providerData` response; (b) preserves that read verbatim and substitutes only the token
minting, which D-18 never claimed to be testing.

### P-02 — D-11's fallout list is two files short

D-11 names four sites: the enum and the CHECK in the migration, the members in `tables/auth.py`, and the three
labels in `tests/schema/test_inventory.py::EXPECTED_ENUM_LABELS`. All four confirmed. **Two more break:**

**`tests/schema/test_constraints.py:566-571`** [VERIFIED: tests/schema/test_constraints.py:566-571, verbatim]:

```python
    @pytest.mark.parametrize("operation", ["restore_subscription", "sign_out_all", "sync"])
    async def test_challenge_for_a_challenge_free_operation_rejected(self, conn, operation):
        """All three challenge-free operations are asserted, because a too-loose CHECK would admit all three."""
        async with _rejects(conn, asyncpg.CheckViolationError):
            await _insert_challenge(conn, operation=operation)
```

D-11 states *"Nothing in `tests/schema/test_constraints.py` names that CHECK."* True of the constraint's
**name**; false of its **coverage**. After the shrink these three strings are not members of
`core.auth_operation` at all, so the insert raises an invalid-enum-input error rather than
`asyncpg.CheckViolationError`, and the case fails. The sibling case
`test_challenge_for_every_challenge_bearing_operation_accepted`, parametrized over the surviving four
[VERIFIED: tests/schema/test_constraints.py:573-577], is unaffected and becomes the sole partition proof.

**`tests/unit/test_challenge_endpoint.py:122-124`** [VERIFIED: tests/unit/test_challenge_endpoint.py:122-124, verbatim]:

```python
# Members of the operation vocabulary whose phases are unbuilt, and strings outside it entirely.
_NOT_ISSUABLE = ["sync", "sign_out_all", "restore_subscription", "claim_anonymous_grant",
                 "nope", "", "create-user", "CREATE_USER"]
```

Three problems at once after D-11: `claim_anonymous_grant` becomes **issuable** and must leave this list; the
first three become garbage strings rather than known-but-unbuilt operations, so the comment above them is
false; and the class's whole premise (*"an unbuilt operation and an invented one are indistinguishable"*)
needs restating, because there are no longer any unbuilt operations in the enum. The neighbouring assertion
`assert store.issued == ["create_user"]` [VERIFIED: tests/unit/test_challenge_endpoint.py:113] also pins the
fake store to the single operation and will need widening.

### P-03 — `NotLinked(cause="empty")` has no producer anywhere in `src/`

D-01 says the causes *"stay `empty | invalid-shape`"* and D-05 says case 1 *"reuses the existing `NotLinked`
(cause `empty`)"*. The classifier never produces `empty` [VERIFIED: src/nativespeaker/api/auth/firebase.py:110-122, verbatim]:

```python
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
```

An empty `providerData` is the *anonymous* answer, not a rejection. A repo-wide grep for `cause=` finds
`"invalid-shape"` at every one of the twelve call sites in `src/` and `tests/` and `"empty"` at none
[VERIFIED: grep over `src/ tests/` this session]. `.planning/STATE.md:265` records why:
*"D-13 instance: the bounded cause 'empty' had no producer (an empty providerData classifies as anonymous and
never reaches the rejection) and went with the sweep (37.3-03)."*

**Consequence.** The decision is unchanged — case 1 *should* raise `NotLinked(stage=…, cause="empty")` — but
this phase writes the **first** producer of that cause, in the upgrade completion, where an *anonymous* live
classification against an *anonymous* stored row is the "client called too early" refusal. That is new
behaviour to test, not reuse to lean on. It also means the `stage` value is this phase's to pick: every
existing `stage` is `"provider_lookup"`, `"issuer_selection"` or `"provider_classification"`, and none of
those describes "the live read confirmed nothing to record."

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Token acceptance + identity resolution | Barrier dependency (`app/dependencies.py`) | — | `get_identity` is the only place it happens; the route re-verifies nothing [VERIFIED: src/nativespeaker/api/app/dependencies.py:37-54] |
| Narrowing to a linked caller | Route dependency (`get_linked_identity`) | — | `/auth/sync` already does exactly this on the same router [VERIFIED: src/nativespeaker/api/routers/auth.py:76-82] |
| Body shape / handle presence | `schemas/auth.py` (Pydantic) | Framework 422 | `min_length=1` makes an unusable handle a 422, not a 409 [VERIFIED: src/nativespeaker/api/schemas/auth.py:24-28] |
| Rejection precedence, claim, provider call, spend | `services/auth.py::AuthService` | — | D-16; the sequence already lives there [VERIFIED: src/nativespeaker/api/services/auth.py:42-93] |
| The `getUser` read and its classification | `auth/firebase.py` (external-SDK seam) | — | Reused unchanged; `auth/` is seams only per AGENTS.md `:35` |
| The locked re-resolution and the two-row write | `crud/identities.py` | — | AGENTS.md `:30` (database access) + exception 4 (a fail-closed read may raise its own rejection) |
| Transaction boundaries (`commit`/`rollback`) | `services/auth.py` | — | AGENTS.md `:57-58`, stated as a rule |
| Client-visible status/code/body | `errors.py` | — | AGENTS.md exception 1; `SHARED-INVARIANTS.md:47` |
| Operation issuance + membership test | `routers/auth.py::issue_challenge` | `tables/auth.py::AuthOperation` | D-10/D-11; the enum *is* the list |

## Standard Stack

No package is added by this phase. Everything below is already installed and was version-checked this session.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| CPython | 3.14.7 | Runtime | [VERIFIED: executed `sys.version` → `3.14.7 (main, Aug 14 2026, 15:35:28)`]. Note `PROJECT.md` says 3.12 — stale, out of scope |
| fastapi | 0.135.1 | Route, `Depends`, `HTTPBearer` | [VERIFIED: executed `fastapi.__version__`] |
| pydantic | 2.12.5 | Request/response models | [VERIFIED: executed `pydantic.VERSION`] |
| sqlmodel + SQLAlchemy async | installed | Tables, `select`, `with_for_update`, `IntegrityError` | The whole `crud/` layer is built on it |
| firebase-admin | 7.3.0 | `auth.get_user` providerData read | [VERIFIED: executed `firebase_admin.__version__`] |
| tenacity | installed | `lookup_with_retry`'s 3 attempts | Already built [VERIFIED: src/nativespeaker/api/auth/firebase.py:139-147] |
| PostgreSQL | 17.11 (Debian 17.11-1.pgdg13+2) | The database the flip writes | [VERIFIED: executed `select version()` against `localhost:5432/nativespeaker` this session] |
| pytest + pytest-asyncio ≥1.3 | installed | Test suite | `asyncio_mode = "auto"` [VERIFIED: pyproject.toml:56] |
| asyncpg | installed | The `tests/schema/` driver, outside the ORM | [VERIFIED: tests/schema/conftest.py:7] |

### Alternatives Considered

None. Every "alternative" this phase could reach for is either an existing decision (D-05, D-08, D-12, D-16) or
a Deferred Idea. Introducing a dependency would contradict AGENTS.md `:8` and Phase 35 D-05.

**Installation:** none — no `uv add`, no `pip install`, no `pyproject.toml` change.

## Package Legitimacy Audit

**Not applicable.** This phase installs no external package. No `pyproject.toml` dependency line is added or
changed, so the legitimacy gate has no subject. Nothing was resolved from a registry and nothing is tagged
`[ASSUMED]` on package grounds.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 client (already ran linkWithCredential, same Firebase UID)
   │
   │  POST /auth/challenge   {operation: "upgrade_anonymous_to_registered"}
   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ router-level Depends(get_identity)   ← unnarrowed, admits pre-auth       │
│   ├─ token absent/bad ────────────────────────► 401 auth_required        │
│   └─ historical / blocked ────────────────────► 403 account_unavailable  │
└───────────────┬──────────────────────────────────────────────────────────┘
                ▼
        issue_challenge handler
                │
                ├─ body.operation NOT IN AuthOperation ──► 400 invalid_request  (D-11)
                ├─ op != create_user AND identity.identity is None
                │                        ──────────────► 403 preauth_...       (D-10)
                └─ ChallengesDB.issue(bound_external_identity_id = row.id)
                                         ──────────────► 200 {challenge_id, expires_at}
                                                             Cache-Control: no-store

 client
   │  POST /auth/upgrade-anonymous   {challenge_id}
   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ route-level Depends(get_linked_identity)  ← narrows to linked callers    │
│   unlinked ───────────────────────────────────► 403 preauth_...          │
└───────────────┬──────────────────────────────────────────────────────────┘
                ▼
      AuthService  — shared completion sequence (D-16)
                │
   ┌────────────┴──── PRE-CLAIM: neither claims nor consumes (D-14) ───────┐
   │  locate handle ─ none ────────────────────► 409 challenge_required    │
   │  verify_binding ─ not the presenter ──────► 409 challenge_required    │
   │  operation != upgrade_anonymous_to_registered ► 409 challenge_required│
   └────────────┬──────────────────────────────────────────────────────────┘
                ▼
      claim (single atomic conditional UPDATE — the only expiry check)
                │  lost ────► expired / consumed ► 409 challenge_required
                ▼
      COMMIT the claim          ← deliberate: no transaction open across the call
                │
                ▼
      Firebase Admin getUser(subject)   ── 3 attempts, run_in_threadpool ──┐
                │                                                          │
                │  not found ─► 401   outage/exhausted ─► 503              │
                │  shape outside accept set ─► 403 operation_not_allowed   │
                ▼                                                          │
      _resolve_provider(entries) ─► (provider, provider_uid) + email       │
                │                                                          │
                ▼          ─── everything below here CONSUMES the handle ──┘
      ONE short database-only transaction
                │
                ├─ SELECT identity JOIN user … FOR UPDATE   (D-15, lock + revalidate)
                │
                ├─ case matrix (D-05 / § Pattern 3)
                │    stored anonymous + live registered ──► FLIP  ──► 200 {provider}
                │    stored == live (provider AND uid)  ──► NO-OP ──► 200 {provider}
                │    stored anonymous + live anonymous  ──► NotLinked(cause=empty)   403
                │    stored registered, live disagrees  ──► ProviderTransition…      403
                │    UNIQUE (issuer,provider,provider_uid) breach ► ProviderAccount… 403
                │
                └─ consume the handle, commit
```

### Recommended Project Structure

No new module. Six existing files carry the code; five more carry the tests.

```
src/nativespeaker/api/
├── routers/auth.py        # + the completion route; issue_challenge gains D-10 + D-11
├── services/auth.py       # + the second completion, sharing the sequence (D-16)
├── crud/identities.py     # + the locked re-resolution and the flip (D-12, D-08)
├── errors.py              # + two classes (D-05)
├── schemas/auth.py        # CreateUserRequest renamed (D-03)
└── tables/auth.py         # AuthOperation shrunk to four (D-11)

migrations/20260818_01_initial-release.sql   # enum shrink + CHECK drop, edited IN PLACE
```

### Pattern 1: The shared completion sequence (D-16)

`AuthService.complete` already *is* the sequence. Only two things in it are create-user-specific: the operation
it checks for at line 53, and the write it performs at line 74 [VERIFIED: src/nativespeaker/api/services/auth.py:42-93].
Everything else — locate, verify binding, claim, commit-before-the-call, retry-wrapped lookup, rollback-then-consume,
consume-and-commit — is identical for both endpoints.

```python
# Source: src/nativespeaker/api/services/auth.py:42-93 (installed, read this session)
    async def complete(self, *, identity: Identity, challenge_id: str) -> IdentityProvider:
        located = await self.challenge_store.locate(self.session, challenge_id)
        if located is None:
            raise ChallengeNotFound()

        challenge = self.challenge_store.verify_binding(located, identity)
        if challenge.operation is not AuthOperation.create_user:      # ← the operation seam
            raise ChallengeOperationMismatch()

        if not await self.challenge_store.claim(self.session,
                                                challenge_id=challenge_id,
                                                now=self.evaluated_at):
            await self.session.refresh(challenge)
            if challenge.claimed_at is None:
                raise ChallengeExpired()
            else:
                raise ChallengeConsumed()

        await self.session.commit()
        challenge_row_id = str(challenge.id)

        try:
            facts = await lookup_with_retry(self.adapter, identity.issuer, identity.subject)
            await self.create_user(identity=identity,                  # ← the write seam
                                   provider=facts.provider,
                                   provider_uid=facts.provider_uid,
                                   email=facts.email)
        except AppError:
            await self.session.rollback()
            try:
                await self._consume_and_commit(challenge_id=challenge_id,
                                               challenge_row_id=challenge_row_id)
            except Exception as failure:
                logger.error("challenge_consume_failed", challenge_row_id=challenge_row_id,
                             failure=type(failure).__name__)
            raise

        await self._consume_and_commit(challenge_id=challenge_id,
                                       challenge_row_id=challenge_row_id)
        return facts.provider
```

**Two facts the planner needs about this body:**

- **The `try`/`except AppError` arm contains a nested `try`** (lines 82-88). D-17 binds the *new* code and
  explicitly does not oblige this phase to clean this up — but if the sequence is shared rather than copied,
  the new completion inherits it. The natural discharge is D-17's own prescription: move the swallow into a
  small named function whose whole job is not raising, which changes the shared arm once and satisfies both.
  That is a discretion call, but it is not the Deferred Idea, which is about *rewriting* create-user's block.
- **The return type is `IdentityProvider`.** For the flip, the returned provider must come from the value the
  transaction settled on (which for the idempotent repeat is the *stored* provider, and for the flip is the
  freshly written one) — not unconditionally from `facts.provider`. In practice they are equal on every
  success branch by construction, but a shared seam that returns `facts.provider` before the transaction has
  had its say would silently launder a divergence into a success.

### Pattern 2: The flip as one crud method that writes both rows (D-12)

The invariant D-12 protects is `users.registered_at IS NOT NULL` **iff** the identity's provider is
`google`/`apple`. Both rows exist and both are already loaded — `insert_account` shows the shape to copy
[VERIFIED: src/nativespeaker/api/crud/identities.py:63-98]:

```python
# Source: src/nativespeaker/api/crud/identities.py:63-98 (installed, read this session)
    async def insert_account(self, *, evaluated_at, identity, provider, provider_uid, email) -> UUID:
        try:
            user = User(email=email,
                        registered_at=None if provider is IdentityProvider.anonymous else evaluated_at,
                        created_at=evaluated_at, updated_at=evaluated_at)
            self.session.add(user)
            await self.session.flush()
            ...
            await self.session.flush()
            return user.id
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict
```

Note what it does **not** do: it names no constraint, parses no message, and opens no savepoint. D-08 copies
exactly this. The one adaptation D-17 forces is that the flip's `try` must wrap **only the `flush()`** — an ORM
attribute assignment (`identity.provider = …`) sends nothing to the database and does not belong inside one.

The column set the flip touches, quoted from the table so no value is guessed
[VERIFIED: src/nativespeaker/api/tables/identities.py:42-56 and :11-16, verbatim]:

```python
class IdentityProvider(StrEnum):
    """Mirrors `core.identity_provider`. `provider_uid` is NULL exactly for `anonymous`."""
    anonymous = "anonymous"
    google = "google"
    apple = "apple"

class ExternalIdentity(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="core.users.id", unique=True)
    issuer: str = Field()
    subject: str = Field()
    provider: IdentityProvider = Field(sa_type=IdentityProviderType)
    provider_uid: str | None = Field(default=None)
    identity_state: IdentityState = Field(sa_type=IdentityStateType, default=IdentityState.active)
    native_claim_platform: NativeClaimProvider | None = Field(sa_type=NativeClaimProviderType, default=None)
    free_grant_consumed_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    historical_at: datetime | None = Field(sa_type=DateTimeType, default=None)
```

and the user side [VERIFIED: src/nativespeaker/api/tables/users.py:11-24, verbatim]:

```python
class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    email: str | None = Field(default=None)
    display_name: str | None = Field(default=None)
    registered_at: datetime | None = Field(sa_type=DateTimeType, default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

So the flip writes exactly: `identity.provider`, `identity.provider_uid`, `identity.updated_at`,
`user.registered_at`, `user.updated_at`, and `user.email` only when it is still `None` (D-13). It writes
`user.display_name` never, `identity.identity_state` never, `identity.historical_at` never,
`identity.free_grant_consumed_at` never.

### Pattern 3: The case matrix, as five branches over two inputs (D-01)

With the client declaration gone there are exactly two inputs: `stored = identity.provider` and
`live = facts.provider` (plus `facts.provider_uid`).

| stored | live | uid comparison | Outcome | Class |
|---|---|---|---|---|
| `anonymous` | `google`/`apple` | — (NULL → confirmed uid, the only assignment) | **flip** | 200 `{identity_provider}` |
| `anonymous` | `anonymous` | — | client called before its own link finished | `NotLinked(cause="empty")` → 403 |
| `google`/`apple` | same provider | `facts.provider_uid == identity.provider_uid` | **idempotent no-op** | 200 `{identity_provider}` (D-04) |
| `google`/`apple` | same provider | uid differs | drift | *ProviderTransitionNotAllowed* → 403 |
| `google`/`apple` | different provider, or `anonymous` | — | drift | *ProviderTransitionNotAllowed* → 403 |
| any | `google`/`apple` | target triple already held | conflict, caught at flush | *ProviderAccountAlreadyLinked* → 403 |

A live shape outside the accept set never reaches this table — `_resolve_provider` raises
`NotLinked(cause="invalid-shape")` inside the seam first [VERIFIED: src/nativespeaker/api/auth/firebase.py:110-122].

The uniqueness the last row breaches [VERIFIED: migrations/20260818_01_initial-release.sql:110-113, verbatim]:

```sql
-- Partial, and carrying no state predicate, so retirement never frees a provider account for reuse.
CREATE UNIQUE INDEX ix_external_identities_provider_account
    ON core.external_identities (issuer, provider, provider_uid)
    WHERE provider_uid IS NOT NULL;
```

and the only other constraint that statement can breach, which D-08 correctly identifies as reachable only by
a bug in this phase's own code [VERIFIED: migrations/20260818_01_initial-release.sql:96-103, verbatim]:

```sql
    -- provider_uid is NULL exactly for anonymous; no sentinel value is ever invented for one.
    CHECK (
        (provider = 'anonymous' AND provider_uid IS NULL)
        OR
        (provider IN ('google', 'apple')
            AND provider_uid IS NOT NULL
            AND provider_uid <> '')
    ),
```

### Pattern 4: The issuance handler after D-10 + D-11

Current body [VERIFIED: src/nativespeaker/api/routers/auth.py:47-55, verbatim]:

```python
    if body.operation != AuthOperation.create_user.value:
        # The rejected string is caller-supplied and bounded, so logging it is safe; a handle never is.
        logger.warning("auth_challenge_operation_not_issuable", operation=body.operation)
        raise InvalidRequest

    challenge_id, expires_at = await challenge_store.issue(session,
                                                           operation=AuthOperation.create_user,
                                                           identity=identity,
                                                           now=evaluated_at)
```

D-11's membership test was executed against the live enum this session
[VERIFIED: executed against `nativespeaker.api.tables.auth.AuthOperation` on CPython 3.14.7]:

```
member str in enum: True     ('create_user' in AuthOperation)
garbage in enum:    False    ('nonsense'    in AuthOperation)
member obj in enum: True
AuthOperation('create_user') → create_user
```

So `body.operation not in AuthOperation` is safe on this interpreter and returns `False` rather than raising
for a non-member string. Two consequences for the handler: the `operation=` passed to `issue` becomes
`AuthOperation(body.operation)` rather than the hardcoded member, and the `logger.warning` line stays correct
(the string is still caller-supplied and now still bounded, because it failed the membership test).

D-10's condition sits after the membership test and before the issue:
`if body.operation != AuthOperation.create_user and identity.identity is None: raise PreAuthIdentityNotAllowed`.
`PreAuthIdentityNotAllowed` already exists and already answers 403 `preauth_identity_not_allowed`
[VERIFIED: src/nativespeaker/api/errors.py:304-307].

### Anti-Patterns to Avoid

- **Writing the flip as raw SQL text containing `FOR UPDATE`.** It fails a ratchet test — see Pitfall 1.
- **Reusing `IdentitiesDB.resolve`'s statement for the lock.** Its `isouter=True` makes `FOR UPDATE` illegal
  on PostgreSQL — see Pitfall 2.
- **Re-reading the row after the write to assert the invariant.** D-12 rejects this explicitly: it costs a
  query per successful upgrade to check what the same transaction just wrote. The schema test is the check.
- **A `changed`/`upgraded` flag on the response.** D-04 forbids it, and `CompletionResponse` is one field
  [VERIFIED: src/nativespeaker/api/schemas/auth.py:31-33].
- **A distinct client-visible error code for any of the three refusals.** `ErrorResponse` is exactly one field
  and the 403 `operation_not_allowed` code already exists on `NotLinked`
  [VERIFIED: src/nativespeaker/api/errors.py:31-33 and :377-380].
- **A savepoint.** `tests/unit/test_conflict_classification.py:288-290` asserts `begin_nested` appears nowhere
  in the combined source of `services/auth.py` + `crud/identities.py` [VERIFIED, verbatim].
- **Deriving `IdentityProvider` from `PurchaseProvider` or vice versa.** Both carry the value `"apple"` for
  different things; D-20's test reads both.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecting the already-taken provider account | A pre-flight `SELECT` for the triple | `except IntegrityError` around the `flush()` | D-08: a pre-check cannot answer without a race, so the catch is needed anyway; two paths saying the same thing, one exercised only by a race |
| Naming which constraint fired | A constraint-name constant or a message parse | Nothing — convert the `IntegrityError` unconditionally | `insert_account` already does this [VERIFIED: crud/identities.py:97-98]; message text is locale-dependent, and `test_conflict_classification.py:284-286` asserts `str(exc`/`str(e)` appear nowhere in these two modules |
| Retrying the Firebase read | A loop, a backoff, a budget object | `lookup_with_retry` | Already 3 attempts through tenacity, already off-loop, already fails closed to 503 [VERIFIED: auth/firebase.py:139-147] |
| Classifying providerData | Any per-endpoint provider logic | `_resolve_provider` inside the seam | Closed classifier, reused unchanged (D-01); duplicating it would put the rule in two places |
| The email-copy rule | An `emailVerified` check in the flip | `facts.email` | `_verified_email` already returns the address only when non-empty and verified [VERIFIED: auth/firebase.py:125-131]; D-13 adds only the stored-is-NULL guard |
| Serializing two simultaneous upgrades | An advisory lock, `SERIALIZABLE`, a `claim_attempt_id` | The existing challenge claim | One atomic conditional UPDATE, one winner [VERIFIED: crud/challenges.py:64-75]; `test_conflict_classification.py:277-280` forbids `advisory_lock`, `pg_advisory`, `isolation_level`, `serializable` in these modules |
| A per-operation issuable list | Any list, table, or route-metadata marker | The `AuthOperation` enum itself | D-10 and D-11, both with reasons the planner must not re-litigate |
| An audit row / a rate limiter / a success log line | Any of them | Nothing | All three deleted from the product by earlier phases |

**Key insight:** this phase's entire novelty is *the flip and its case matrix*. Everything around it is a
seam that already exists and is already tested. The failure mode is not "we couldn't build it" — it is
"we rebuilt something that was already there, or we tripped a ratchet nobody remembered."

## Runtime State Inventory

This phase is an endpoint addition plus a destructive schema edit, so the migration half of the inventory is
live. Each category answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **The `core.auth_operation` type itself.** D-11 removes three labels from a live PostgreSQL type. `core.auth_challenges.operation` is its only consumer [VERIFIED: `grep` over `migrations/` finds `core.auth_operation` referenced only at `:18` (the `CREATE TYPE`) and `:378` (`operation core.auth_operation NOT NULL`)]. Any existing dev-database row carrying one of the three dropped labels would block the change — none can exist, because the `auth_challenges` CHECK at `:392-399` has always forbidden all three. | Edit the single migration in place and **drop + re-apply the dev/test database**, exactly as Phase 37 D-13 did (SCHEMA-01). No `ALTER TYPE`, no incremental file. |
| Live service config | **None.** The endpoint reads no external service configuration; Envoy is untouched (the 3/hour entry is v2.1 per Phase 35 D-08), and no `k8s/` file names an auth operation. | none |
| OS-registered state | **None.** No task, timer, unit or supervisor entry references anything this phase changes. | none |
| Secrets / env vars | **`GOOGLE_APPLICATION_CREDENTIALS` becomes load-bearing in a new way.** It is already required for the create-user real-path test; D-18 additionally requires it to be *signing-capable*, which it is not [VERIFIED: § P-01]. **`FIREBASE_TEST_*` gains a sibling** — D-18's Google-linked account UID needs a home. The existing e2e keys are `JWT_PROJECT_ID`, `JWT_API_KEY`, `FIREBASE_TEST_EMAIL`, `FIREBASE_TEST_PASSWORD`, `GOOGLE_APPLICATION_CREDENTIALS` [VERIFIED: read `.env` variable **names** only, and `.env.example` in full]. | Add the new UID variable to **`.env.example`** with the by-hand creation note D-18 requires, and to the developer's `.env`. Resolve the signing question per § P-01. |
| Build artifacts / installed packages | **None.** No package name, entry point or console script changes; `pyproject.toml` is untouched except (optionally) nothing at all. The `.venv` needs no reinstall. | none |

## Common Pitfalls

### Pitfall 1: `"for update"` is a forbidden literal in the two modules this phase edits

**What goes wrong:** D-15's lock is added, the suite goes red on a test that has nothing to do with locking.

**Why it happens:** [VERIFIED: tests/unit/test_conflict_classification.py:246-248 and :271-280, verbatim]

```python
# Both halves of the creation path: the service holds the rule, the store holds the inserts.
_CREATION_SOURCE = "\n".join(Path(module.__file__).read_text()
                             for module in (auth_service, identities_crud))

class TestTheModuleUsesNoSecondRaceArbiter:
    """The UNIQUE constraints are the sole arbiters, and nothing else may be added."""

    @pytest.mark.parametrize("forbidden", ["serializable", "advisory_lock", "pg_advisory",
                                           "isolation_level", "for update", "select_for_update"])
    def test_no_second_serialization_mechanism_appears_in_the_code(self, forbidden):
        """An advisory lock, a stricter isolation level or a row lock would each be an arbiter that can disagree."""
        assert forbidden not in _code_only(_CREATION_SOURCE).lower()
```

`_code_only` unparses the AST with docstrings stripped, so comments and docstrings cannot trip it — but a
string literal can, and `services/auth.py` + `crud/identities.py` are **exactly** the two modules this phase
edits.

**How to avoid:** express the lock as SQLAlchemy's `.with_for_update()`. Executed against the forbidden list
this session, a statement reading
`select(ExternalIdentity, User).join(User).where(...).with_for_update()` matches **none** of the six terms
[VERIFIED: ran the test's own `ast.unparse(...).lower()` + substring check over that source]. Raw SQL text
containing `FOR UPDATE` matches `"for update"` and fails.

**Warning signs:** the test is in the *unit* suite, so it runs in the default `pytest` invocation
(`addopts = "-v --tb=short -m 'not e2e and not schema'"` [VERIFIED: pyproject.toml:58]) — it will fail fast,
which is the good case. The bad case is a planner who reads the failure as "the lock is forbidden" and drops
D-15, which the user explicitly declined.

**A judgement call the plan must make, not dodge:** the test passes by the letter, but its docstring reads
*"The UNIQUE constraints are the sole arbiters, and nothing else may be added."* D-15's lock is not a race
arbiter for the create-user path (which is what the class guards) and the challenge claim remains the only
serialization point — but a later reader will meet a lock in a module whose test says none may exist. The
honest discharge is one line in the test class or its docstring recording that the upgrade path's lock is
revalidation, not arbitration. That is cheaper than the alternative, which is a reviewer re-deriving D-15's
argument from scratch.

### Pitfall 2: `FOR UPDATE` cannot be applied to the nullable side of an outer join

**What goes wrong:** the discretion item *"one joined statement taking `FOR UPDATE` on both tables"* is chosen,
the obvious implementation reuses `IdentitiesDB.resolve`'s statement shape, and PostgreSQL refuses at runtime.

**Why it happens:** `resolve` deliberately uses an outer join [VERIFIED: src/nativespeaker/api/crud/identities.py:29-34, verbatim]:

```python
        # Outer join: an identity row whose user_id resolves to nothing must stay distinct from no row.
        statement = (select(ExternalIdentity, User)
                     .join(User, col(ExternalIdentity.user_id) == col(User.id), isouter=True)
                     .where(col(ExternalIdentity.issuer) == issuer,
                            col(ExternalIdentity.subject) == subject))
```

Executed against the live database this session [VERIFIED: asyncpg against PostgreSQL 17.11 on `localhost:5432/nativespeaker`]:

```
outer-join FOR UPDATE REJECTED: FeatureNotSupportedError
    FOR UPDATE cannot be applied to the nullable side of an outer join
inner-join FOR UPDATE: ACCEPTED
```

**How to avoid:** the lock query is a **new** method with an **inner** join. That is sound here and not a
weakening: by the time the completion transaction opens, `get_linked_identity` has already established that
both rows exist and both are active, so the outer join's purpose (telling "broken link" apart from "no row")
has already been served by the barrier. The alternative discretion option — two ordered statements — sidesteps
this entirely at the cost of a second round trip.

**Warning signs:** this surfaces only against a real database, so it will appear in `tests/e2e` or
`tests/schema`, both of which are **deselected by default** (`-m 'not e2e and not schema'`). A green
`pytest` run does not clear it.

### Pitfall 3: the error-tree ratchets reject a new exception class that is not registered in three places

**What goes wrong:** D-05's two classes are appended to `errors.py` and four unit tests go red at once.

**Why it happens:** `tests/unit/test_rejection_vocabulary.py` holds the vocabulary as a literal
[VERIFIED: tests/unit/test_rejection_vocabulary.py:34-35 and :95-97, verbatim]:

```python
# One entry per class in the tree.
EVENT_NAMES = frozenset({
...
    def test_the_tree_spells_exactly_the_recorded_event_names(self):
        derived = {camel_to_snake(cls.__name__) for cls in _production_family()}
        assert derived == EVENT_NAMES
```

and separately requires every class's `log_fields()` to yield scalars only
[VERIFIED: tests/unit/test_rejection_vocabulary.py:140-143, verbatim]:

```python
    @pytest.mark.parametrize("cls", _production_family(), ids=lambda c: c.__name__)
    def test_every_class_in_the_tree_contributes_only_scalars(self, cls):
        for key, value in _sample(cls).log_fields().items():
            assert isinstance(value, str | None), f"{cls.__name__}.{key} is not a scalar"
```

with `_sample` building each class from a table that must be kept in step
[VERIFIED: tests/unit/test_rejection_vocabulary.py:105-127].

**How to avoid:** a new class with a required `__init__` needs (1) its snake-cased name added to
`EVENT_NAMES`, (2) an entry in `CONSTRUCTOR_ARGUMENTS`, and (3) `log_fields()` returning `str | None` values
only — so **D-06's identity row id must be stringified**, exactly as `InvalidExternalJwt` stringifies its
`StrEnum` [VERIFIED: src/nativespeaker/api/errors.py:299-301] and as `AuthService` stringifies the challenge
row id [VERIFIED: src/nativespeaker/api/services/auth.py:70]. D-06's two provider values are already
`IdentityProvider` members, which are `StrEnum` and therefore `str` instances — but `str(provider)` is the
convention the repo uses and reads unambiguously.

The tree's own totality walk additionally requires each class to declare `status` and `code` **together or
neither**, and forbids one code at two statuses [VERIFIED: `.planning/REQUIREMENTS.md:103`, describing
`assert_tree_total`, now hosted at `tests/unit/error_tree.py`]. Both new classes answer 403
`operation_not_allowed` — which `NotLinked` already declares [VERIFIED: src/nativespeaker/api/errors.py:377-380]
— so the safest placement is as siblings under a base that declares the pair once, mirroring how
`ChallengeRejected` declares its 409 once and no leaf re-declares it [VERIFIED: src/nativespeaker/api/errors.py:386-391].

**Warning signs:** `AppError`'s fail-closed default is 500 `internal_error` [VERIFIED: src/nativespeaker/api/errors.py:39-41],
so a class that forgets to declare anything answers **500**, not 403, and the client-visible symptom is an
internal error rather than a refusal.

### Pitfall 4: the docstring bar is measured at zero and the new code is measured too

**What goes wrong:** a helpful four-line docstring lands and `tests/unit/test_docstring_bar.py` goes red.

**Why it happens:** [VERIFIED: tests/unit/test_docstring_bar.py:40-46, verbatim]

```python
BASELINE: dict[str, int] = {
    "src": 0,
    "tests": 0,
    "tests/e2e": 0,
    "tests/schema": 0,
    "tests/unit": 0,
}
```

**How to avoid:** three lines maximum in every docstring, in `src/` **and** in the new tests. Comments one
line each, only where they resolve a real ambiguity.

### Pitfall 5: the enum shrink breaks two tests the CONTEXT does not list

Covered in full at § Premise Corrections P-02. Restated here so a planner reading only the pitfalls meets it:
`tests/schema/test_constraints.py:566` and `tests/unit/test_challenge_endpoint.py:123` both hardcode the three
dropped labels. The first expects `asyncpg.CheckViolationError` for a constraint that will no longer exist,
against enum labels that will no longer exist. The second lists `claim_anonymous_grant` as un-issuable, which
D-11 makes false.

### Pitfall 6: `PREAUTH_CALLABLE_PATHS` is a deliberate literal and the new route belongs in neither set

**Why it happens:** [VERIFIED: tests/unit/test_app_wiring.py:12-13, verbatim]

```python
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
```

The generic case then requires every other route to declare `get_linked_identity`
[VERIFIED: tests/unit/test_app_wiring.py:28-32]. So `/auth/upgrade-anonymous` must take
`Depends(get_linked_identity)` at the **route** level — the router-level dependency is `get_identity` and is
deliberately unnarrowed [VERIFIED: src/nativespeaker/api/routers/auth.py:33-34] — and must be added to
**neither** literal. The named-route parametrization at `tests/unit/test_app_wiring.py:40` and `:47` currently
reads `("/auth/sync", "/users/me")` [VERIFIED] and is the natural place to name the new path explicitly.

### Pitfall 7: a claim committed before the provider call means a lost call leaves a dead handle

**What goes wrong:** the repair loop is expected to retry with the same handle and cannot.

**Why it happens:** the claim is committed deliberately before the Firebase read
[VERIFIED: src/nativespeaker/api/services/auth.py:66-67, verbatim]:

```python
        # Deliberate commit: an uncommitted claim across the provider call would let a second attempt win the challenge.
        await self.session.commit()
```

combined with D-14's rule that everything at or after the Firebase call consumes.

**How to avoid:** nothing to avoid — this is the accepted design, and D-14 names the cost explicitly
(*"the repair loop pays a fresh prepare round-trip on every retry"*). It is listed here so the **client
contract** in any documentation this phase writes says *prepare then complete*, every time, rather than
*retry the handle*.

## Code Examples

### The existing `IntegrityError` → typed rejection, which D-08 copies

```python
# Source: src/nativespeaker/api/crud/identities.py:97-98 (installed, read this session)
        except IntegrityError as conflict:
            raise IdentityAlreadyLinked() from conflict
```

No constraint name, no message parse, no savepoint. The flip's arm is the same two lines with a different
class.

### The established row-lock idiom in this repo

```python
# Source: src/nativespeaker/api/crud/grants.py:41 and :52 (installed, read this session)
        statement = _effective_grants_statement(user_id, evaluated_at).with_for_update()
        ...
        statement = _usage_statement(grant_id).with_for_update()
```

`.with_for_update()`, never raw SQL. This is both the repo convention and the only form that survives
Pitfall 1.

### The scripted provider fake D-19 uses

```python
# Source: tests/unit/conftest.py:192-210 (installed, read this session)
class FakeFirebaseAdapter:
    def __init__(self) -> None:
        self.answer: BaseException | VerifiedProviderIdentity = ANONYMOUS_IDENTITY
        self.calls: list[tuple[str, str]] = []

    def script(self, answer: BaseException | VerifiedProviderIdentity) -> None:
        """Raise-or-return: a scripted exception is raised, a scripted identity is returned."""
        self.answer = answer

    async def get_user_provider_data(self, issuer: str, subject: str) -> VerifiedProviderIdentity:
        self.calls.append((issuer, subject))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer
```

It scripts the **seam's answer**, not the read's inputs — so a D-19 case for "live says google" scripts a
`VerifiedProviderIdentity(provider=IdentityProvider.google, provider_uid=…, email=…)` directly, and a case for
"live says anonymous" scripts the anonymous identity. Its `calls` list is also how D-22's "exactly one
`getUser` per completion, repeats included" is asserted.

### The e2e seeding helper, which already takes the provider the flip starts from

```python
# Source: tests/e2e/conftest.py:173-194 (installed, read this session)
async def seed_identity(factory, *,
                        issuer: str,
                        subject: str,
                        identity_state: IdentityState = IdentityState.active,
                        user_active: bool = True,
                        provider: IdentityProvider = IdentityProvider.google):
    """Insert a core.users row and its matching core.external_identities row; return both."""
    # The table's CHECK ties the two together: provider_uid is NULL exactly for anonymous.
    provider_uid = None if provider is IdentityProvider.anonymous else f"{provider}-uid-{subject}"
```

`provider=IdentityProvider.anonymous` gives the pre-upgrade row for free, and the derived
`f"{provider}-uid-{subject}"` is exactly the handle a D-19 already-taken case needs to pre-reserve on a
*second* seeded identity.

### The real-path e2e shape D-18 mirrors

```python
# Source: tests/e2e/test_create_user.py:553-560 (installed, read this session)
@pytest.mark.asyncio(loop_scope="module")
class TestTheRealAnonymousCompletion:
    """Nothing substituted, end to end against the live project; skips without an Admin credential."""

    async def test_a_genuinely_anonymous_user_completes_through_the_real_admin_sdk(
            self, anonymous_client, _db_transaction, _app_lifespan, _app_config,
            anonymous_firebase_credential):
        _, local_id = anonymous_firebase_credential
        adapter = _app_lifespan.state.firebase_adapter
        # scripted_firebase_adapter is deliberately not requested, and this is what makes that visible.
        assert isinstance(adapter, FirebaseAdminLookup)
```

The `assert isinstance(adapter, FirebaseAdminLookup)` line is the pattern worth copying: it makes "this test
really did hit Firebase" an assertion rather than an absence.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `?challenge=true` mode-signal partition | A dedicated `POST /auth/challenge` route | Phase 37.2 | D-09; `classify_mode_signal` does not exist |
| Client declares the target provider | The server derives it from `providerData` | Phase 37 D-12 → this phase's D-01 | Brief steps 3, 4 and the `supported-provider-mismatch` cause all dissolve |
| `AuthEventResult` 44-member outcome enum | Exception classes; the class name **is** the log event | Phase 37.3 | D-05's two classes are the internal results |
| Returned rejection vocabulary | DRF-style raised exceptions, one handler | Phase 37.3 | The flip raises; it never returns an outcome |
| `audit.auth_events` | Nothing; the structured log line only | Phase 37.1 D-01, Phase 38 D-03 | Brief step 11 and the whole audit hardening paragraph are dead |
| Backend `limits` rate-limit engine | Nothing in the product; Envoy deferred to v2.1 | Phase 35 D-05 / D-08 | Every rate-limit entry in the brief is dead |
| `auth/identity.py`, `auth/create_user.py`, `quota.py` | `crud/identities.py`, `services/auth.py`, `services/quota.py` | Phase 37.5 | The layering AGENTS.md now states |
| A service-account key for Firebase Admin | Application Default Credentials | Phase 37.2 D-06…D-08 | The reason P-01 exists: ADC cannot sign |

**Deprecated/outdated in the inputs the planner will read:**

- `05-upgrade-anonymous.md` "Provided by foundation" `:16-21` describes a route registry, an audit writer and
  a rate-limit engine. **None exists.** Read the CONTEXT's "Carried forward" list before implementing any line
  of that section.
- `.planning/codebase/*.md` — captured 2026-02-24, three milestones stale, predates the `d466a4b` renames and
  Phase 37.5's moves. **Do not consult them; read the source.**
- `.planning/PROJECT.md` § Constraints says Python 3.12; the interpreter is 3.14.7 [VERIFIED this session].

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| CPython | everything | ✓ | 3.14.7 | — |
| PostgreSQL (dev/test) | the flip, `tests/schema`, `tests/e2e` | ✓ | 17.11 on `localhost:5432`, database `nativespeaker` | — |
| firebase-admin SDK | the `getUser` read | ✓ | 7.3.0 | — |
| Firebase ADC (read) | D-18's real `getUser`; create-user's existing real test | ✓ | `authorized_user` ADC file present and resolvable | — |
| **Firebase ADC (signing)** | **D-18's custom-token mint** | **✗** | ADC has no signer; `create_custom_token` raises `ValueError` | **§ P-01 routes (a), (b) or (c)** |
| A permanently Google-linked Firebase account | D-18 | ✗ | not created; no env var reserved for its UID | Route (c): the test skips, as `anonymous_firebase_credential` already does |
| `JWT_PROJECT_ID` / `JWT_API_KEY` / `FIREBASE_TEST_EMAIL` / `FIREBASE_TEST_PASSWORD` | the e2e suite's real token | ✓ | present in `.env` | — |
| `psql` CLI | nothing in the suite | ✗ | not installed | asyncpg is the driver everywhere; no fallback needed |

**Missing dependencies with no fallback:** none that block implementation. The flip, the enum shrink, the
route, the unit tests, the schema test and every D-19/D-20 case can be built and run today.

**Missing dependencies with fallback:** D-18's success-path test only. Three routes are costed at § P-01, and
the choice is a **Wave 0 gate**, not a test-wave discovery.

## Validation Architecture

`workflow.nyquist_validation` is `true` [VERIFIED: .planning/config.json].

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio ≥1.3, `asyncio_mode = "auto"` [VERIFIED: pyproject.toml:31, :56] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` [VERIFIED: pyproject.toml:51-62] |
| Quick run command | `uv run pytest` — `addopts = "-v --tb=short -m 'not e2e and not schema'"`, so this is the unit suite [VERIFIED: pyproject.toml:58] |
| Full suite command | `uv run pytest -m 'e2e or schema' && uv run pytest` (the markers are deselected by default and must be asked for explicitly) [VERIFIED: pyproject.toml:59-62] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UPGRADE-01 | anonymous → google/apple flips in place, same row id | e2e | `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -k flips_in_place` | ❌ Wave 0 |
| UPGRADE-01 | `provider_uid` assigned NULL → confirmed uid; `registered_at` set; `email` copied only when NULL | e2e | same file, `-k writes_both_rows` | ❌ Wave 0 |
| UPGRADE-01 | idempotent repeat: 200, identical body, no mutation (D-04) | e2e (scripted fake) | same file, `-k idempotent` | ❌ Wave 0 |
| UPGRADE-01 | live-anonymous refusal → `NotLinked(cause="empty")` → 403 | e2e (scripted fake) | same file, `-k not_linked_yet` | ❌ Wave 0 |
| UPGRADE-01 | drift refusal → the new transition class → 403 | e2e (scripted fake) | same file, `-k drift` | ❌ Wave 0 |
| UPGRADE-01 | already-taken triple → the new conflict class → 403, caught not pre-checked | e2e (scripted fake, second seeded identity) | same file, `-k already_linked` | ❌ Wave 0 |
| UPGRADE-01 | no row exists in the third state (`registered_at` set XOR provider registered) | schema | `uv run pytest -m schema tests/schema/test_registration_pairing.py` | ❌ Wave 0 (D-12) |
| UPGRADE-01 | criteria 3 & 4: `/users/me` + `/auth/sync` report the new provider; purchase tokens unchanged | e2e | `uv run pytest -m e2e tests/e2e/test_flows.py -k upgrade` | ✅ file exists, case ❌ (D-20) |
| UPGRADE-01 | real Google-linked account completes through the real Admin SDK | e2e | `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -k real_google` | ❌ Wave 0, **gated on § P-01** |
| UPGRADE-02 | rejection precedence: not-found / binding / operation reject before the claim and consume nothing | unit | `uv run pytest tests/unit/test_upgrade_precedence.py` | ❌ Wave 0 |
| UPGRADE-02 | every outcome at or after the Firebase call consumes the handle (D-14) | unit | same file, `-k consumes` | ❌ Wave 0 |
| UPGRADE-02 | exactly one `getUser` per completion, idempotent repeat included (D-22) | unit | same file, `-k one_lookup` | ❌ Wave 0 |
| UPGRADE-02 | an unlinked caller is 403 on the route (never pre-auth) | unit | `uv run pytest tests/unit/test_app_wiring.py` | ✅ exists — extend the two parametrizations at `:40`/`:47` |
| UPGRADE-02 | `/auth/challenge` issues for all four operations, rejects garbage with 400 | unit | `uv run pytest tests/unit/test_challenge_endpoint.py` | ✅ exists — **must be edited**, see P-02 |
| UPGRADE-02 | an account-less caller asking for anything but create-user is 403 (D-10) | unit | same file, new class | ❌ Wave 0 |
| D-11 | `core.auth_operation` has exactly four labels | schema | `uv run pytest -m schema tests/schema/test_inventory.py` | ✅ exists — **literal must be edited** |
| D-11 | the dropped-label CHECK cases | schema | `uv run pytest -m schema tests/schema/test_constraints.py -k AuthChallenge` | ✅ exists — **three cases break**, see P-02 |
| D-05 | the two new classes are in the vocabulary and carry scalars only | unit | `uv run pytest tests/unit/test_rejection_vocabulary.py` | ✅ exists — `EVENT_NAMES` + `CONSTRUCTOR_ARGUMENTS` must be edited |

### Sampling Rate

- **Per task commit:** `uv run pytest` (the unit suite; ~1000 cases, no external dependency).
- **Per wave merge:** `uv run pytest -m schema` after any migration or `tables/` change; `uv run pytest -m e2e`
  after any router/service change. Both need the live PostgreSQL; `-m e2e` also needs Firebase credentials.
- **Phase gate:** `uv run pytest -m 'e2e or schema'` **and** `uv run pytest` both green, plus `ruff check`.

### Wave 0 Gaps

- [ ] `tests/e2e/test_upgrade_anonymous.py` — the endpoint's own e2e file (D-18 real case + D-19 fake cases)
- [ ] `tests/unit/test_upgrade_precedence.py` — the rejection-precedence and consumption-disposition cases
- [ ] `tests/schema/test_registration_pairing.py` — D-12's third-state scan (asyncpg, outside the e2e rollback)
- [x] **Answer § P-01 before the test wave.** Answered 2026-09-02: none of (a), (b) or (c) — see
      § Open Questions Q1. The mechanism is exchange-and-link with a stored Google refresh token (plan 40-03).
- [ ] Reserve and document the D-18 credential variables in `.env.example` — three
      `FIREBASE_TEST_GOOGLE_*` values under the adopted mechanism, not an account UID (D-18's obligation 1,
      plan 40-03 Task 2)
- [ ] Edits to existing files: `tests/schema/test_inventory.py` (enum literal),
      `tests/schema/test_constraints.py` (three cases, P-02), `tests/unit/test_challenge_endpoint.py`
      (`_NOT_ISSUABLE` + `store.issued`, P-02), `tests/unit/test_rejection_vocabulary.py`
      (`EVENT_NAMES` + `CONSTRUCTOR_ARGUMENTS`), `tests/unit/test_app_wiring.py` (name the new path),
      `tests/unit/test_conflict_classification.py` (Pitfall 1's judgement call)
- [ ] Framework install: **none** — pytest, pytest-asyncio, asyncpg and httpx are all installed

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json` [VERIFIED], so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Firebase ID token, RS256, pinned `iss`/`aud`, cached JWKS, verified in `get_identity` only. **Nothing new is built** [VERIFIED: src/nativespeaker/api/app/dependencies.py:37-54] |
| V3 Session Management | no | `SHARED-INVARIANTS.md:23` — no backend-minted token, no session, no cookie, ever. This endpoint issues nothing |
| V4 Access Control | yes | `get_linked_identity` narrows to a linked active caller; `ChallengesDB.verify_binding` proves the presenter is the identity row the handle was bound to [VERIFIED: crud/challenges.py:90-105] |
| V5 Input Validation | yes | Pydantic. The body is exactly `{challenge_id}` with `min_length=1`; the operation string is a plain `str` validated against the enum, never a `Literal` [VERIFIED: schemas/auth.py:13-28] |
| V6 Cryptography | yes (indirect) | Handle generation is `secrets.token_bytes(16)` base64url-unpadded [VERIFIED: crud/challenges.py:21-23]. **Nothing new is written**; the phase adds no crypto |
| V7 Error Handling & Logging | yes | One WARNING per rejection from one handler; the class name is the event [VERIFIED: app/error_handlers.py:33-44]. D-06 bounds what the two new classes may carry |
| V8 Data Protection | yes | D-06 excludes the provider-account uid from the log line; the challenge handle is never logged (the store module holds no logger at all [VERIFIED: crud/challenges.py:1]) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Account-takeover by claiming a provider account another user holds | Elevation of Privilege | The partial unique index `(issuer, provider, provider_uid) WHERE provider_uid IS NOT NULL`, carrying **no state predicate** so retirement never frees a reservation [VERIFIED: migration `:110-113`]. D-08 converts the breach; nothing auto-rewrites |
| Enumeration oracle — probing which provider accounts are taken | Information Disclosure | D-02: all three refusals answer an identical 403 with a one-field body. `ErrorResponse` is exactly one field [VERIFIED: errors.py:31-33]. `SHARED-INVARIANTS.md:49` requires it within a class |
| Challenge replay to probe provider state | Spoofing | D-14: consumed on every outcome at or after the Firebase call, with no branch on which rejection fired. The claim is a single atomic conditional UPDATE and the only expiry check [VERIFIED: crud/challenges.py:64-75] |
| Handle leakage into logs, URLs or error bodies | Information Disclosure | Body-only transport; `Cache-Control: no-store` on issuance [VERIFIED: routers/auth.py:56-59]; the validation handler logs `loc`/`type` and never `input`, precisely because a malformed body can carry a live handle [VERIFIED: app/error_handlers.py:47-50] |
| Trusting client-declared provider | Tampering | D-01 removes the declaration outright. Provider and `provider_uid` derive **only** from the `getUser` read; `SHARED-INVARIANTS.md:7` forbids rederiving from claims, headers or client input |
| Half-written upgrade (provider flipped, `registered_at` unset) | Tampering / integrity | D-12: one method issues both writes in one transaction, plus the schema-level third-state scan |
| Network call under a held lock | Denial of Service | The Admin read runs strictly before the write transaction opens, and the claim is committed first [VERIFIED: services/auth.py:66-73]. `SHARED-INVARIANTS.md:35` mandates it |
| Unbounded provider calls from a looping client | Denial of Service | **Accepted and flagged (D-22).** No rate limiting exists; the caller must hold a valid token for an existing linked account, so it is one subject looping on itself, not a fan-out. Closes when the Envoy contract lands (v2.1) |

**One recorded divergence relevant here, not introduced by this phase:** `SHARED-INVARIANTS.md:52-55` mandates
the `limits` library. This project has none, by Phase 35 D-05, recorded as an override rather than a flagged
conflict [VERIFIED: .planning/REQUIREMENTS.md:22 and :34]. This phase must not "fix" it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Route (b) of § P-01 works end to end — a parameterized ephemeral-RSA verifier lets a locally minted token reach the **real** `FirebaseAdminLookup` and select the right app. The two halves are verified (the verifier's hardcoded issuer, and `get_user_provider_data`'s issuer-keyed app lookup); the composition is not, because no Google-linked account exists yet to compose against. | § P-01 | If wrong, only route (a) or (c) remains for D-18 — no code outside the test changes |
| A2 | Granting the ADC principal `roles/iam.serviceAccountTokenCreator` makes `create_custom_token` succeed via the SDK's IAM `signBlob` fallback. Inferred from the SDK's own error text (*"specify a service account ID with iam.serviceAccounts.signBlob permission"*), not executed — the grant is a GCP change outside this repo. | § P-01 route (a) | Route (a) costs an IAM change and still fails; fall back to (b) or (c) |
| A3 | No **production** dashboard or alert keys on the log-event names this phase adds. Phase 37.3 recorded the same finding for the events it retired. | D-05 / D-06 | A renamed-later event breaks nothing today; the risk is zero pre-launch |
| A4 | Editing the single migration in place and re-applying will succeed without an `ALTER TYPE … DROP VALUE` (which PostgreSQL does not support) because the dev/test database is disposable. This is what Phase 37 D-13 did and SCHEMA-01 requires; not re-executed this session. | § Runtime State Inventory | If a developer's local database holds data they care about, the re-apply destroys it — the plan should say "drop and re-apply" explicitly rather than "migrate" |
| A5 | The new upgrade route needs no change to `crud/challenges.py`, per D-09. Verified by reading all four methods and `verify_binding`; `issue` already binds a linked caller to `bound_external_identity_id` [crud/challenges.py:43-47]. Marked assumed only because it is a negative claim about a module this phase does not touch. | D-09 | A missing binding surfaces as a failing precedence test, cheaply |

## Open Questions (RESOLVED)

All four were answered during planning on 2026-09-02. Each resolution below names the plan that carries it;
the plans, not this file, are the executable record.

1. **Which § P-01 route does D-18 take?**
   - What we know: the mint fails today, for a reason verified by execution; three routes exist, each costed.
   - What's unclear: whether the developer will make a GCP IAM change for a pre-launch test.
   - Recommendation: **ask before planning the test wave.** Default to route (b) if no answer arrives — it
     preserves the real `getUser` read (D-18's actual purpose) at zero credential cost, and route (a) can be
     added later without rewriting the test's assertions.
   - **RESOLVED (2026-09-02, plan 40-03): none of the three — the question's premise was dropped.** The
     developer reversed route (a): no IAM grant is made, and with the org policy
     `iam.disableServiceAccountKeyCreation` in force and the machine's ADC an `authorized_user` with no
     signer, this project mints and signs nothing at all. The adopted mechanism is **exchange-and-link with a
     stored Google refresh token**: one browser consent by hand yields a long-lived refresh token held in
     `.env` as `FIREBASE_TEST_GOOGLE_REFRESH_TOKEN`; each run redeems it for a fresh Google ID token, creates
     a fresh anonymous Firebase user over Identity Toolkit REST with the existing `JWT_API_KEY`, links the
     Google credential to it, and deletes the user afterwards. **This supersedes all three routes this
     section proposed** — (a)'s IAM grant, (b)'s locally minted ID token, and (c)'s skip — and it also
     supersedes D-18's own stated mechanism, which described custom-token minting and said explicitly "no
     per-run OAuth consent flow and no stored refresh token." It keeps what D-18 was actually for: the real
     `getUser` read against a genuine `google.com` `providerData` entry. Recorded as a divergence in the
     Phase 40 amendment to `.planning/REQUIREMENTS.md` (plan 40-08, Task 1).

2. **What `stage` value does the new `NotLinked(cause="empty")` carry?**
   - What we know: every existing `stage` is `"provider_lookup"`, `"issuer_selection"` or
     `"provider_classification"` [VERIFIED by grep]; the field is a plain string chosen by the raiser
     [VERIFIED: errors.py:345-358].
   - What's unclear: this rejection is not a classification failure — the classifier succeeded and answered
     *anonymous*. Reusing `"provider_classification"` would be misleading in the log.
   - Recommendation: a new bounded value naming the upgrade decision (the planner's call), added in the same
     commit as the raise so the vocabulary and its producer land together.
   - **RESOLVED (2026-09-02, plan 40-05): a fourth bounded value, `"upgrade_confirmation"`.** The planner
     took the call the recommendation reserved. It names the decision that failed rather than the classifier
     that succeeded, and it lands in the same commit as its raiser.

3. **Does the shared completion sequence keep or discharge the nested `try` (D-17)?**
   - What we know: D-17 binds new code; the nested block is at `services/auth.py:82-88`; cleaning up
     create-user's block is a Deferred Idea.
   - What's unclear: sharing the sequence means the new completion *runs through* that block.
   - Recommendation: extract the swallow into a small named function per D-17's own prescription. That is the
     minimum change that satisfies the rule for the new path, and it is not the deferred rewrite.
   - **RESOLVED (2026-09-02, plan 40-04): discharged by extraction, as recommended.** The swallow becomes a
     small named function, `_consume_quietly`, whose whole job is not raising; the shared sequence therefore
     contains no nested `try`. This is the minimum change satisfying D-17 for the new path and is not the
     deferred rewrite of create-user.

4. **Does `tests/unit/test_conflict_classification.py` get a note about the upgrade lock?**
   - What we know: the lock passes the literal check; the class docstring says nothing else may be added.
   - Recommendation: one line recording that the upgrade path's lock is revalidation, not arbitration. Cheaper
     than a reviewer re-deriving D-15.
   - **RESOLVED (2026-09-02, plan 40-04, Task 2): yes — one docstring line, as recommended.** It records that
     the upgrade path's lock is revalidation rather than arbitration, so a reader does not re-derive D-15.

## Sources

### Primary (HIGH confidence)

All read or executed in this session, in `/home/init/native-speaker/`:

- `ns-api-gateway/src/nativespeaker/api/` — `services/auth.py`, `routers/auth.py`, `routers/users.py`,
  `crud/identities.py`, `crud/challenges.py`, `auth/firebase.py`, `errors.py`, `schemas/auth.py`,
  `tables/auth.py`, `tables/identities.py`, `tables/users.py`, `app/dependencies.py`,
  `app/error_handlers.py`, `config.py`, `crud/__init__.py`, `services/__init__.py` (read in full or in the
  cited ranges)
- `ns-api-gateway/migrations/20260818_01_initial-release.sql` — lines 10-56, 62-121, 372-416
- `ns-api-gateway/tests/` — `unit/conftest.py`, `unit/test_rejection_vocabulary.py`,
  `unit/test_conflict_classification.py`, `unit/test_app_wiring.py`, `unit/test_challenge_endpoint.py`,
  `unit/test_docstring_bar.py`, `unit/test_auth_package_shape.py`, `e2e/conftest.py`,
  `e2e/test_create_user.py`, `schema/conftest.py`, `schema/test_inventory.py`, `schema/test_constraints.py`
- `ns-api-gateway/AGENTS.md`, `ns-api-gateway/pyproject.toml`, `ns-api-gateway/.env.example`
- `native-speaker/AGENTS.md` (the `CLAUDE.md` target)
- `specs/auth-refactor-phases/05-upgrade-anonymous.md` (93 lines, read in full)
- `specs/auth-refactor-phases/SHARED-INVARIANTS.md` (64 lines, read in full)
- `.planning/phases/40-post-auth-upgrade-anonymous/40-CONTEXT.md`, `.planning/REQUIREMENTS.md` (§ header +
  § UPGRADE), `.planning/STATE.md`, `.planning/config.json`

**Executed this session (not read — run):**

- CPython 3.14.7 interpreter: enum membership over `AuthOperation`; `firebase_admin.__version__`;
  `fastapi.__version__`; `pydantic.VERSION`; `google.auth.default()`; `firebase_admin.auth.create_custom_token`
- PostgreSQL 17.11 via asyncpg: `select version()`; `FOR UPDATE` on an outer join (rejected) and on an inner
  join (accepted)
- The forbidden-substring check from `test_conflict_classification.py`, re-run over a candidate
  `.with_for_update()` statement

### Secondary (MEDIUM confidence)

- The `firebase_admin` SDK's own error text, quoted verbatim, as the basis for A2's remediation path.

### Tertiary (LOW confidence)

None. No web search was needed: this phase adds no library and every question was answerable from the
installed source or by executing it.

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — nothing is added; every version was executed, not recalled
- Architecture: **HIGH** — every pattern quoted from installed source with line ranges
- Pitfalls: **HIGH** — 1, 2, 3, 4, 5 and 6 each verified by reading the failing test's own literal or by
  executing the failing condition; 7 quoted from the shipped comment
- Environment: **HIGH** for what exists, and the one gap (signing) was proven by execution rather than assumed
- D-18's remediation: **MEDIUM** — the failure is verified, the three fixes are costed but only route (c) is
  proven to work

**Research date:** 2026-09-02
**Valid until:** 2026-10-02 (30 days — an in-repo domain with no fast-moving external dependency). Invalidated
earlier by: any edit to `services/auth.py`, `crud/identities.py`, `errors.py` or the migration; any change to
`GOOGLE_APPLICATION_CREDENTIALS`.
