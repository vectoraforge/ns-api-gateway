---
phase: 35-foundation
plan: 03
subsystem: identity-context
tags: [fastapi, starlette, sqlmodel, dataclasses, dependency-injection, postgresql-enums]

requires:
  - phase: 35-foundation
    plan: 01
    provides: "auth/registry.py RouteMetadata; auth/ subpackage with its explicit __init__.py barrel"
  - phase: 35-foundation
    plan: 02
    provides: "errors.py with AuthenticationError pointed at AUTH_REQUIRED; auth/verification.py VerifiedClaims"
provides:
  - "auth/context.py — the §1.4 seam: REQUEST_CONTEXT_SCOPE_KEY, IdentityKind, ClientIpBucketKind, LinkedIdentity, PreAuthIdentity, RequestContext"
  - "models/identities.py — core.external_identities plus IdentityProvider / IdentityState / NativeClaimProvider"
  - "app/dependencies.py — get_request_context / get_linked_identity / get_preauth_identity, each raising rather than returning None"
  - "tests/unit/test_identity_accessors.py — 61 tests over fail-loudly, variant confusion, the field sets, and the absent client address"
affects: [35-04, 35-05, 35-06, 35-07, 35-08, 35-09, 35-10, 35-11, 36-rebinding]

actuals:
  tokens: 6960
  tasks: 1
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A discriminated union of frozen slotted dataclasses whose kind tag sits last and defaults, so the tag cannot be omitted or mis-set at a construction site"
    - "A pinned module-level scope key shared by the writer (barrier) and the readers (accessors), so the two cannot drift to different strings and fail open"
    - "Depends() accessors that raise on both absence and the wrong variant, centralising the fail-loudly check instead of leaving it to seven later phases"
    - "isinstance rather than `is None` as the absence check, so a wrong-typed stash fails closed too"
    - "A pure-ASGI stash middleware in tests standing in for the barrier, exercising the real scope[\"state\"] hand-off rather than dependency_overrides"

key-files:
  created:
    - src/nativespeaker/api/auth/context.py
    - src/nativespeaker/api/models/identities.py
    - tests/unit/test_identity_accessors.py
  modified:
    - src/nativespeaker/api/app/dependencies.py
    - src/nativespeaker/api/auth/__init__.py
  deleted: []

key-decisions:
  - "All three accessors raise AuthenticationError (auth_required) on both absence and the wrong variant. The caller-facing preauth_identity_not_allowed rejection is the barrier's to emit at §1.5 step 5; a wrong variant reaching an accessor is a wiring bug, not a caller condition, so the accessor's only job is refusing to hand it over."
  - "The kind tag sits last in each variant and defaults to its own member. A dataclass cannot carry a defaulted field ahead of undefaulted ones, so kind-first would force every construction site to pass the tag explicitly — the one place it could be passed wrong."
  - "The absence check is `not isinstance(context, RequestContext)`, not `context is None`, so a wrong-typed value under the key fails closed rather than reaching a handler as a duck-typed stand-in."
  - "models/identities.py encodes no table CHECK and no composite UNIQUE. __table_args__ is exactly {\"schema\": \"core\"} per the plan; the provider/provider_uid CHECK, UNIQUE (issuer, subject), and ix_external_identities_provider_account stay in the migration, which is what actually enforces them."
  - "models/__init__.py was not touched. It is outside this plan's file list, and every src/ importer already uses the full module path — the same convention plan 02 recorded for the auth barrel."

requirements-completed: [FOUND-01]

coverage:
  - id: D1
    description: "Reading the identity context where the barrier did not attach one raises and is answered auth_required — never a None a handler could treat as anonymous"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestAbsentContextRaises (12 tests: 3 accessors x raise / class-is-AUTH_REQUIRED / wrong-typed-stash, plus 3 over a live client)"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestNeverReturnsNone (12 tests over 3 accessors x 3 failing stashes, plus the return-annotation check)"
        status: pass
      - kind: other
        ref: "mutation M1 (absent context returns None instead of raising) -> 21 failures; M6 (isinstance relaxed to `is None`) -> 7 failures"
        status: pass
    human_judgment: false
  - id: D2
    description: "The context carries the identity variant, the route metadata record, the client-IP bucket kind, one evaluation time, and a server-generated attempt id"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestContextShape::test_request_context_carries_exactly_the_five_request_scoped_values"
        status: pass
      - kind: other
        ref: "python -c \"...sorted(RequestContext.__dataclass_fields__)\" -> ['attempt_id','client_ip_bucket_kind','evaluated_at','identity','route_metadata']"
        status: pass
    human_judgment: false
  - id: D3
    description: "The pre-auth variant carries the verified (issuer, subject) and nothing else — no user row, no identity row, no provider"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestContextShape::test_preauth_carries_the_verified_pair_and_nothing_else"
        status: pass
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestVariantConfusionRaises (7 tests — both wrong-variant directions raise, both right-variant directions return the identical object)"
        status: pass
      - kind: other
        ref: "mutations M2/M3 (drop each variant check) and M5 (add provider to PreAuthIdentity) -> 2 failures each"
        status: pass
    human_judgment: false
  - id: D4
    description: "The package still imports and the whole suite is still green — this plan only adds, it deletes nothing"
    requirement: FOUND-01
    verification:
      - kind: other
        ref: "git show --stat HEAD -> 5 files, 583 insertions, 0 deletions; git diff --diff-filter=D HEAD~1 HEAD -> empty"
        status: pass
      - kind: other
        ref: "python -c 'import nativespeaker.api.app.main' exits 0; get_current_user and require_quota still import and are still referenced 8x in routers/chats.py"
        status: pass
      - kind: unit
        ref: "pytest -q -> 310 passed (249 baseline + 61 new), 0 regressions; schema 77 passed; e2e 26 failed/16 passed = exact measured baseline"
        status: pass
    human_judgment: false
  - id: D5
    description: "No client address is carried on the context — bucket kind only (A3)"
    requirement: FOUND-01
    verification:
      - kind: unit
        ref: "tests/unit/test_identity_accessors.py::TestNoClientAddressIsCarried (7 tests — the three bucket kinds, no address-shaped field name, and the only str fields being the verified issuer and subject)"
        status: pass
      - kind: other
        ref: "mutation M4 (add client_address: str | None to RequestContext) -> 2 failures"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-08-20
status: complete
---

# Phase 35 Plan 03: Typed Identity Context and Fail-Loudly Accessors Summary

**The seam phases 36-46 import by name now exists: two identity variants that cannot be confused
for each other, one request-scoped record of everything a later phase must not recompute, and three
`Depends()` accessors that answer `auth_required` rather than hand a handler a `None` it could read
as anonymous.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-20 22:26
- **Completed:** 2026-08-20 22:37
- **Tasks:** 1 of 1
- **Files modified:** 5 (3 created, 2 modified, 0 deleted)

## Accomplishments

- **§1.4 is implemented.** `auth/context.py` declares all five symbols with the exact field sets
  the plan pinned. Both variants and the context are `frozen=True, slots=True`, so a handler cannot
  mutate what the barrier resolved.
- **`core.external_identities` has a model.** All twelve migration columns, with the three native
  PostgreSQL enums bound the v1.6 way (`cast(Any, Enum(..., name=..., schema='core'))`).
- **D-02 is complete.** The three accessors live in one place, so none of the seven later phases
  re-implements the fail-loudly check.
- The unit suite grew **249 → 310** (+61) with zero regressions, and both gates stay clean.
- **Nothing was deleted.** `git show --stat` reports 583 insertions and 0 deletions.

### The final field sets

| Type | Fields | Note |
|---|---|---|
| `RequestContext` | `identity`, `route_metadata`, `client_ip_bucket_kind`, `evaluated_at`, `attempt_id` | all required, no defaults |
| `LinkedIdentity` | `user`, `identity`, `issuer`, `subject`, `kind` | `kind` defaults to `IdentityKind.linked` |
| `PreAuthIdentity` | `issuer`, `subject`, `kind` | `kind` defaults to `IdentityKind.preauth` |

`REQUEST_CONTEXT_SCOPE_KEY = "ns_request_context"`.
`IdentityKind` = `linked`, `preauth`. `ClientIpBucketKind` = `ipv4`, `ipv6`, `unresolved`.

`ExternalIdentity` maps all twelve columns: `id`, `user_id`, `issuer`, `subject`, `provider`,
`provider_uid`, `identity_state`, `native_claim_platform`, `free_grant_consumed_at`, `created_at`,
`updated_at`, `historical_at`. `IdentityProvider` = `anonymous`/`google`/`apple`; `IdentityState` =
`active`/`historical` exactly; `NativeClaimProvider` = `ios_devicecheck`/`android_play_integrity`.

### What plan 04 must still delete

Confirmed present and still wired after this plan, exactly as the plan requires:

| Symbol | State | Evidence |
|---|---|---|
| `get_current_user` | present in `app/dependencies.py`, imported by `routers/chats.py` | `routers/chats.py` carries 8 references to the two names combined |
| `require_quota` | present, still on the two `dependencies=[Depends(require_quota)]` route decorators | same |
| `get_subscription_service` | present, still reads `app.state.apple_verifier` | unchanged |

They sit below a new banner comment in `app/dependencies.py` recording that plan 04 deletes them
together with the chat-route rewiring that is their last caller. Deleting them here would have left
the package un-importable, because `routers/chats.py` is not rewired by this plan.

## Task Commits

1. **Task 1: Typed identity context and the fail-loudly `Depends()` accessors** — `27315f2` (feat)

One commit, because the plan is one task and is not TDD-marked. The tests are in the same commit as
the code they cover; splitting them would have produced a RED commit the plan never asked for.

## Decisions Made

- **Both wrong-variant paths raise `AuthenticationError`, not `preauth_identity_not_allowed`.**
  This was the one genuinely open choice — the plan pins the class for the *absent* case only. The
  reasoning: SHARED-INVARIANTS does say an unlinked caller on a non-`preauth_callable` route gets
  `preauth_identity_not_allowed`, but that rejection belongs to the barrier's admission matrix at
  §1.5 step 5, which plan 06 implements. By the time a request reaches a `Depends()` accessor the
  barrier has already ruled, so a pre-auth variant arriving at a linked-only handler means the
  route's registry declaration and its handler disagree — a wiring bug, not a caller condition.
  Answering a bug with the caller-facing "complete account setup" contract would send a client
  round a loop it cannot exit. `auth_required` is the fail-closed answer that reveals nothing, and
  it keeps all three accessors indistinguishable to a client, which is the anti-oracle shape §3.1
  wants anyway. It also kept `errors.py` — not in this plan's file list — untouched.
  **Plan 06 may specialise this** once `/auth/create-user` exists and `get_preauth_identity` has a
  real caller; the accessor is the only place that would change.
- **The `kind` tag sits last and defaults to its own member.** A dataclass cannot carry a defaulted
  field ahead of undefaulted ones, so putting `kind` first as the plan's interface sketch shows
  would have forced every construction site to pass the tag explicitly — creating the one place it
  could be passed wrong. Last-and-defaulted makes the discriminator correct by construction, and
  the `Literal[IdentityKind.linked]` annotation makes the wrong member a type error. Field *order*
  is not part of the contract: both acceptance criteria assert `sorted(__dataclass_fields__)`.
- **The absence check is `isinstance`, not `is None`.** A wrong-typed value under the key is as
  unusable as an absent one and must fail closed rather than reach a handler as a duck-typed
  stand-in. Mutation M6 (relaxing it to `is None`) fails 7 tests, so this is covered, not merely
  intended.
- **No table CHECK or composite UNIQUE is re-encoded in Python.** `__table_args__` is exactly
  `{"schema": "core"}` per the plan's action text. The provider/provider_uid agreement CHECK,
  `UNIQUE (issuer, subject)`, and the partial `ix_external_identities_provider_account` index stay
  in the migration; a Python copy is a second source of truth that can drift from the one that
  enforces. The single-column `UNIQUE (user_id)` is expressible on the `Field` itself without
  touching `__table_args__`, so it is mirrored there as documentation of the one-identity-per-user
  cap.
- **`models/__init__.py` was left alone.** It is outside the plan's file list, and `auth/context.py`
  imports `nativespeaker.api.models.identities` by full module path — the convention plan 02 already
  recorded. Plan 11 writes the final barrels.
- **The tests stash context through a pure-ASGI middleware, not `dependency_overrides`.** Overriding
  the accessor would prove only that FastAPI calls the override. The stash middleware writes the
  real `REQUEST_CONTEXT_SCOPE_KEY` onto `scope["state"]`, which is exactly what the barrier will do
  in plan 06, so `test_a_stashed_context_reaches_the_handler_over_http` proves the hand-off the
  negative tests are the inverse of.

## Deviations from Plan

**None — the plan executed exactly as written.** No auto-fix was needed under any of Rules 1–3, and
no Rule 4 architectural question arose. The wrong-variant error class (above) was a discretionary
choice the plan left open, not a deviation from it.

The one place the implementation differs from the plan's prose is the `<interfaces>` sketch, which
lists `kind` as the first field of each variant. That sketch is a field *list*, not a declaration
order, and both acceptance criteria assert the sorted set — see the decision above for why the tag
sits last instead.

## Issues Encountered

- **Six mutations, all caught.** Coverage was verified by mutating the shipped modules rather than
  assumed from a green run: absent context returning `None` (21 failures), dropping
  `get_linked_identity`'s variant check (2), dropping `get_preauth_identity`'s (2), adding a
  `client_address` field to `RequestContext` (2), adding a `provider` field to `PreAuthIdentity`
  (2), and relaxing the `isinstance` guard to `is None` (7). Each mutation was asserted to have
  actually applied before its result was read — plan 02 recorded a silent anchor-miss producing a
  false green, so the harness raises on an unmatched anchor. All three source files were confirmed
  byte-identical to their pre-mutation state afterwards.
- **`User` and `ExternalIdentity` are constructed in tests without their required columns.** SQLModel
  skips validation on `table=True` classes, so `User(id=..., active=True)` works. This is deliberate
  forward-proofing: `models/users.py` still carries the v1.6 shape (`jwt_sub`, non-null `email`,
  `subscription_plan`) that plan 05 repairs, and constructing with those fields would have made
  `test_identity_accessors.py` break on the repair.
- **`structlog.testing.capture_logs` was not needed.** This plan asserts no log output, so the
  deferred `test_logging.py` caching issue is not touched either way.
- **Out of scope, unchanged:** the 26 e2e failures (v2.0 schema drift, `column users.jwt_sub does
  not exist`, plan 35-05's to repair) and the two `test_logging.py` failures in a combined run
  reproduce exactly as measured. Nothing was added to `deferred-items.md` — this plan discovered no
  new out-of-scope item.

## Test Status

| Suite | Result | Note |
|---|---|---|
| Unit (`pytest -q`) | **310 passed**, 119 deselected | 249 baseline + 61 new; zero regressions |
| New file (`pytest -q tests/unit/test_identity_accessors.py`) | **61 passed** | 6 test classes |
| Schema (`pytest -q -m schema`) | **77 passed** | unchanged |
| E2E (`pytest -q -m e2e`) | 16 passed, **26 failed** | exactly the measured baseline; this plan adds and touches no e2e test |
| `ruff check src tests` | **All checks passed!** | |
| `ty check src` | **All checks passed!** | |

`python -c "import nativespeaker.api.app.main"` exits 0 — nothing was removed.

The plan's `<verification>` bullet "`pytest -q -m ""` green, zero xfail, zero skip" cannot hold at
plan 03, for the same reason it could not at plans 01 and 02: it is the D-18 phase-end bar, and the
26 e2e failures it covers are plan 35-05's to repair. No `xfail` markers exist anywhere in `tests/`.

## Known Stubs

None. Every symbol this plan declares is implemented and exercised.

Two fields are declared here and populated by a later plan. Neither is a stub — both are part of the
§1.4 contract this plan exists to pin, and neither has a caller yet because the barrier that fills
them is plan 06's:

| Field | State | Owner |
|---|---|---|
| `RequestContext.client_ip_bucket_kind` | the enum and the field exist; nothing derives the kind from `scope["client"]` yet | plan 35-06 |
| `RequestContext.attempt_id` | typed and required; the barrier generates the uuid7 | plan 35-06 |

`get_preauth_identity` likewise has no production caller until `/auth/create-user` lands (phase 36+).
That is the plan's design — the seam ships before its consumers — and it is fully unit-covered here.

## Threat Flags

None. Every file this plan created or modified is covered by the plan's own `<threat_model>`. No new
network endpoint, auth path, file-access pattern, or schema change at a trust boundary was
introduced — no route was registered, no query was written, and no session is reachable from any
symbol added here. The five `mitigate` dispositions are all implemented:

| Threat ID | Mitigation as shipped |
|---|---|
| T-35-03-01 | All three accessors raise `AuthenticationError` (→ `auth_required`) when the context is absent *or* wrong-typed, and none has a `None`-returning path; `TestNeverReturnsNone` proves it across 3 accessors × 3 failing stashes, and mutation M1 confirms the coverage |
| T-35-03-02 | `get_linked_identity` raises on a `PreAuthIdentity` and `get_preauth_identity` on a `LinkedIdentity`; `PreAuthIdentity` carries no `user`, `identity`, `provider`, `provider_uid`, or `user_id` attribute for a handler to read even if one leaked through — asserted directly |
| T-35-03-03 | The classifier is `LinkedIdentity.identity.provider`, the stored column; no context-level `provider` field exists (`test_the_linked_classifier_is_the_stored_provider_column`), and the module docstring records `registered_at` as reporting-only |
| T-35-03-04 | `ClientIpBucketKind` carries exactly `ipv4`/`ipv6`/`unresolved`; no dataclass field name reads as an address and the only `str`-typed fields on any of the three are the verified `issuer` and `subject`; mutation M4 confirms an added address field fails the suite |
| T-35-03-SC | No package was installed; the legitimacy gate stays vacuous for Phase 35 |

The **no-provisioning prohibition** (plan 04 owns its enforcement, but these accessors are in scope
for it) is satisfied structurally rather than by inspection: all three accessors are synchronous and
take exactly one parameter, the `Request`. `TestAccessorsCannotWrite` asserts both. A sync function
with no session parameter cannot await a write, so creating, linking, repairing, reassigning, or
merging a row is unreachable from this seam, not merely absent from it.

## Next Phase Readiness

Ready. Every interface plan 04 and beyond import from this plan exists at the pinned module path:

- `auth.context.REQUEST_CONTEXT_SCOPE_KEY` / `IdentityKind` / `ClientIpBucketKind` /
  `LinkedIdentity` / `PreAuthIdentity` / `RequestContext`, re-exported from the `auth` barrel.
- `models.identities.IdentityProvider` / `IdentityState` / `NativeClaimProvider` /
  `ExternalIdentity`.
- `app.dependencies.get_request_context` / `get_linked_identity` / `get_preauth_identity`.

Notes for the plans that follow:

- **Plan 04** can now swap `Depends(get_current_user)` → `Depends(get_linked_identity)` on
  `routers/chats.py` and drop `dependencies=[Depends(require_quota)]`, then delete both functions.
  Note the handler signature changes shape: `get_linked_identity` yields a `LinkedIdentity`, so
  `user.id` becomes `identity.user.id`.
- **Plan 05** repairs `models/users.py` to the v2.0 seven columns. `LinkedIdentity.user: User` is a
  type reference only — no test in this plan constructs a `User` with a v1.6-specific column, so the
  repair does not touch `test_identity_accessors.py`.
- **Plan 06** owns the barrier's write side: derive `ClientIpBucketKind` from `scope["client"]` (the
  gateway-resolved address, never a forwarded header), capture one `evaluated_at`, generate the
  `attempt_id`, and stash the `RequestContext` at `scope["state"][REQUEST_CONTEXT_SCOPE_KEY]`. The
  stash middleware in `tests/unit/test_identity_accessors.py::_stash_middleware` is the exact shape
  it needs.
- **Plan 06 may specialise the wrong-variant error class** on `get_preauth_identity` once
  `/auth/create-user` has a real caller. The absent-context class is fixed by §1.4 and must stay
  `auth_required`.
- **`models/__init__.py` still does not export `ExternalIdentity`.** Deliberate — plan 11 writes the
  final barrels, and `src/` importers use full module paths.

## Self-Check: PASSED

All 5 claimed files are in their claimed state on disk: `auth/context.py`,
`models/identities.py`, and `tests/unit/test_identity_accessors.py` present; `app/dependencies.py`
and `auth/__init__.py` modified. The claimed commit `27315f2` is present in `git log`, carries
exactly those 5 paths, and shows 583 insertions with 0 deletions.

---
*Phase: 35-foundation*
*Completed: 2026-08-20*
