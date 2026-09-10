---
phase: 42-post-auth-claim-registered-grant
fixed_at: 2026-09-10T04:51:50Z
review_path: .planning/phases/42-post-auth-claim-registered-grant/42-REVIEW.md
iteration: 1
findings_in_scope: 40
fixed: 39
skipped: 1
status: partial
---

# Phase 42: Code Review Fix Report

**Fixed at:** 2026-09-10T04:51:50Z
**Source review:** `.planning/phases/42-post-auth-claim-registered-grant/42-REVIEW.md` (commit `2b14d71`)
**Iteration:** 1

**Summary:**
- Findings in scope: 40 (0 Critical + 40 Warning; Info was out of scope, no `--all`)
- Fixed: 39
- Skipped: 1 (WR-42)

The fix pass ran as five batches, A to E, STRICTLY SEQUENTIALLY. Concurrent fixers share one git index and corrupt each other, so no two ran at the same time. Each batch owned a disjoint set of findings and committed one commit per finding.

Six extra commits repair the repository docstring-line ratchet, which tripped on new test cases in batch D. Each names the finding whose case tripped it.

Two findings were fixed **in part**. Half of WR-02 and half of WR-24 were declined against ratified decisions; both declined halves are recorded under Skipped Issues with the governing decision.

## Fixed Issues

<!-- batch A -->

### WR-01: `container.port` is a knob that silently breaks the deployment

**Files:** `Dockerfile`, `k8s/templates/deployment.yaml`, `k8s/values.yaml`
**Commit:** `89c14ea`

The finding holds. The image started uvicorn from a single `CMD` carrying `--port 8000`,
and the chart never overrode it, so `--set container.port=9000` moved `containerPort`,
`targetPort: http` and both probes while the process stayed on 8000.

Made the value load-bearing rather than deleting it. The `Dockerfile` now splits
`ENTRYPOINT ["uvicorn", "nativespeaker.api.app.main:app"]` from `CMD ["--host", "0.0.0.0",
"--port", "8000"]`, and `deployment.yaml` renders
`args: ["--host", "0.0.0.0", "--port", "{{ .Values.container.port }}"]` beside the `ports:`
block. The split is required: with no `ENTRYPOINT`, a Kubernetes `args:` alone would have
replaced the whole `CMD` and left `--host` as the command. `values.yaml`'s probe comment,
which asserted the false premise, now states the mechanism that makes it true. `docker run
<image>` still starts the server on 8000.

### WR-02 (in part): deployer-tunable values pinned in the tracked `config.yaml`

**Files:** `config/config.yaml`
**Commit:** `4870ff4`

Deleted the `model:` and `resilience:` blocks. Every one of those twelve values was
byte-identical to the `config.py` field default, so the deletion is a runtime no-op that
restores the levers: measured after the change, `MODEL_NAME=gpt-x RESILIENCE_POOL_SIZE=9`
now reaches the loaded config (`gpt-x 9`), where before the tracked file outranked both.
The file's own rule at its foot — "Add a key here only when it must NOT vary per
deployment" — is the ground; a model switched during a provider incident and caps sized
for one staging replica are per-deployment decisions.

The `db:` block was kept. See `## Skipped Issues`.

The dangling comment ("The relation to resilience **above**") was rewritten to name
`resilience.pool_size` and its field default, since the block it pointed at is gone.

### WR-03: `AGENTS.md` sends a new exception handler to the wrong module

**Files:** `AGENTS.md`
**Commit:** `b9f5cef`

Confirmed: `errors.py` contains `ErrorResponse`, `AppError` and its subclasses only, and
every handler plus `register_exception_handlers` lives in `app/error_handlers.py`.
Exception 1 now splits the two owners. Added the two homes the list omitted while opening
with "Every file has exactly one home": `app/` (`main.py`, `lifespan.py`,
`dependencies.py`, `error_handlers.py`) and the package root (`config.py`, `errors.py`,
`logs.py`, `resilience.py`), which together cover every previously homeless module.

### WR-20: the never-set DeviceCheck body matched case-sensitively

**Files:** `src/nativespeaker/api/auth/devicecheck.py`, `tests/unit/test_devicecheck_adapter.py`
**Commit:** `8e0e3d3`

`_NEVER_SET_BODIES` now holds casefolded literals and `_parse_bit_state` casefolds the body,
matching `_DEVICE_TOKEN_FAULT`'s treatment of the same response at `:127`. Both literal sets
carry the same `[ASSUMED]` provenance, so neither may turn on Apple's capitalisation, and
the never-set state is the only state the anonymous grant is issued for.

The test's `NEVER_SET_BODIES` tuple gained a second capitalisation of each body, which feeds
the three existing parametrized cases. Mutation-probed: reverting the `.casefold()` on the
body fails six of them, including both new drifted spellings. Probe reverted in the same
call.

### WR-21: `get_devicecheck_adapter` bound `DeviceCheckAdapter` at no seam

**Files:** `src/nativespeaker/api/app/dependencies.py`
**Commit:** `d3f9d0e`

Annotated the accessor's return type and `get_auth_service`'s `devicecheck` parameter, and
imported the Protocol (no cycle). The docstring no longer says "deliberately unannotated"
with no reason attached.

Proved the annotation is load-bearing rather than decorative: a throwaway module calling
`get_auth_service(devicecheck=WrongShapedDouble())`, where the double declares `read_bits`
and not `write_bits`, now draws `invalid-argument-type` from `ty` naming the parameter.
The probe module was deleted; `ty check src` is clean.

Left `adapter=Depends(get_firebase_adapter)` on the same signature untouched — the same gap,
but not this finding, and `services/auth.py` belongs to another batch.

### WR-22: `VerifiedClaims.payload` carried the whole verified JWT with no reader

**Files:** `src/nativespeaker/api/auth/jwt_verifier.py`, `tests/unit/test_jwt_security.py`
**Commit:** `25a9320`

Verified the field is dead in `src/` before deleting: `dependencies.get_identity` reads
`issuer`/`subject`, and `PubSubPushTokens.verify` reads only whether `claims is None`. The
field and its comment are gone, and the required-claims branch now ends
`return claims_from_payload(payload)` — the same value the other branch returns, minus the
re-widening.

Updated the two cases that asserted the field: the field-set case now pins
`["issuer", "subject"]` and carries the reason, and `test_fields` drops the `payload is
None` line. Neither was weakened — the field-set assertion is still an exact `==`.

### WR-23: the `exc_info` decision read the level the line above had just clamped

**Files:** `src/nativespeaker/api/app/error_handlers.py`, `tests/unit/test_exception_handlers.py`
**Commit:** `446b534`

`exc_info` now reads `level`, not `exc.log_level`. For any non-standard level below 40 the
record was emitted at ERROR by the clamp and carried `exc_info=False` from the raw value —
the highest-severity line this handler writes, with the traceback stripped.

The finding calls this latent, so it added a regression case:
`TestALevelOutsideTheFiveIsClampedOnceAndReadOnce` sets `log_level = logging.INFO + 5` **on
the instance**, never on a synthetic `AppError` subclass — a subclass would join `_family`
for the rest of the session and the error-tree and registry cases walk it. Mutation-probed:
restoring `exc.log_level` fails exactly that case. Probe reverted in the same call.

### WR-24 (in part): a transient ADC failure at pod start, behind a warning promising recovery

**Files:** `src/nativespeaker/api/auth/firebase.py`, `src/nativespeaker/api/app/lifespan.py`
**Commit:** `19d7918`

Fixed the half that is a defect on its own terms: all four `consequence=` strings said the
route recovers "until X **are available in this environment**", over reads that happen once
at boot. They now say "until this pod is **restarted** with X available in this
environment", which is what the code does. This matters most on the Firebase line, where the
value genuinely can appear on its own — a metadata server recovers in seconds — and the
process would never look again.

The half that re-raises a `RefreshError`/`TransportError` was declined. See
`## Skipped Issues`.

### WR-25: only half of the path-segment guard was hoisted into `read`

**Files:** `src/nativespeaker/api/auth/google_play.py`, `tests/unit/test_google_play_notifications.py`
**Commit:** `dc652f0`

Confirmed the whole chain: `verify_google_play_notification` forwards only a `packageName`
equal to the configured one, so a configured `"."` reaches `read` intact; `_get` interpolates
it through `quote(..., safe="")`, which leaves the dot; httpx removes the dot segment; the
404 is classified by `_play_answer_is_usable` as `_GONE_STATUSES`; `read` returns `None` and
the route acknowledges 200 — permanent loss, since Pub/Sub does not redeliver an
acknowledged message.

`read` now applies `read_for_restore`'s guard to `package_name` too, and refuses loudly
(`google_play_unusable_package_name` + `InternalError` → 500 → redelivery) rather than
acknowledging, because the fault is the deployment's and not the payload's. Also corrected
`_get`'s comment, which credited the dot refusal to `read_for_restore` alone.

Added four cases to the existing `TestBothEntryPointsGuardTheValueTheyPutInThePath`
(`""`, `"."`, `".."`, `"..."`), with a transport that raises if reached. Mutation-probed:
neutering the guard fails all four. Probe reverted in the same call.

<!-- batch B -->

### WR-40 — the lock-taking readers hand back the identity map's pre-lock snapshot

**Files:** `src/nativespeaker/api/crud/grants.py`
**Commit:** `b5fa27d`

Added `.execution_options(populate_existing=True)` to `lock_effective_grants`,
`lock_active_grants`, `lock_active_grants_of` and `lock_usage`, and to
`read_usage` (which `write_subscription_grant` reads `monthly_used` through).
`SubscriptionsDB.read_subscription` already carried the option and its comment
is cited as the reason.

The review also named `crud/subscriptions.py:89`. That line is
`await self.grants_db.lock_active_grants_of(user_ids)` — it delegates to the
reader fixed here, so the two-account restore hole closes with it and
`crud/subscriptions.py` needed no edit.

Proved against the live PostgreSQL before committing (scratch table created and
dropped in the same command):

```
populate_existing=False: preflight='anonymous' under-lock='anonymous' same_obj=True
populate_existing=True:  preflight='CHANGED_BY_RIVAL' under-lock='CHANGED_BY_RIVAL' same_obj=True
```

The first line is the defect: a rival had committed `CHANGED_BY_RIVAL` and the
`SELECT ... FOR UPDATE` still answered with the preflight's value.

### WR-41 — `SubscriptionEvent.notification_uuid` states a schema rule the `tables` package forbids

**Files:** `src/nativespeaker/api/tables/purchases.py`,
`src/nativespeaker/api/tables/auth.py`,
`src/nativespeaker/api/tables/identities.py`,
`tests/unit/test_tables_metadata.py`
**Commit:** `2c93d6f`

Dropped `unique=True` from `SubscriptionEvent.notification_uuid`,
`AuthChallenge.challenge_id` and `ExternalIdentity.user_id`, each replaced with
the "Deliberately not `unique=True`" comment the three sibling columns in
`purchases.py` already carry. Each rule is stated by the migration:
`notification_uuid TEXT NOT NULL UNIQUE` (line 208), `challenge_id TEXT NOT NULL
UNIQUE` (line 296) and `UNIQUE (user_id)` (line 100).

All three had to go together, because the second half of the fix — the new
`TestTheMetadataDeclaresNoUniquenessRule` guard, which walks `table.constraints`
where the existing guard walks `table.indexes` — fails while any one of them
stands. The guard was mutation-probed: re-adding `unique=True` to
`notification_uuid` fails `test_no_mapped_table_declares_one`, and the change
was reverted in the same call.

`tests/unit/test_tables_metadata.py:26-28` (`_UUID_KEYED_TABLES`) is another
batch's WR-124 and was left untouched.

### WR-60 — a registered claim that loses the one-active index to a subscription or manual writer answers 200 having granted nothing

**Files:** `src/nativespeaker/api/services/auth.py`,
`tests/unit/test_claim_precedence.py`,
`tests/unit/test_claim_precedence_registered.py`
**Commit:** `ebb5c87`

`AuthService._settle` now takes `source` and requires the re-read to find a
grant of *that* source before it answers 200. A winner of any other source
raises `ClaimRefusedUnderLock(cause="lost_race_to_another_source")`; an empty
re-read keeps the existing `lost_race_without_a_readable_grant`. Both claim arms
pass their own source down.

Grounds checked before editing, because this changes the lost-race outcome:

- 42-CONTEXT.md D-09(b) answers "any other active grant that is not
  `anonymous_device_grant`" with 403 `operation_not_allowed`, and D-09 says
  destination selection is "run in the preflight **and again inside the locked
  transaction**". `crud/grants.py:258-259` already returns
  `refused, "other_grant_held"` when the writer *sees* that grant — the
  lost-race arm was the one place the same state answered 200.
- `specs/auth-refactor-phases/07-claim-registered-grant.md` step 2(b) says the
  same: reject `operation_not_allowed`, "mutating nothing — a wait, not a
  forfeit".
- D-10's "the loser re-reads and answers 200" and D-12's "the repeat and the
  race loser return the same body" are unaffected: a loser to a *registered*
  (or, on the anonymous route, *anonymous*) winner still answers 200.

The client-visible answer of `ClaimRefusedUnderLock` and `OtherActiveGrantHeld`
is identical — both are `ClaimRefused`, 403 `operation_not_allowed` — so the
raced answer now matches the deterministic one on the wire and differs only in
the internal log event's `cause`.

Two new cases pin it (one per claim route), plus a new
`_race_lost_to_another_source` entry in each file's `POST_CLAIM_OUTCOMES` so the
consumption control covers the branch. Mutation-probed: replacing the source
test with the old `if held:` fails both new cases.

### WR-61 — the replayed store notification returns 200 while still holding the buyer's locks

**Files:** `src/nativespeaker/api/services/subscriptions.py`,
`tests/unit/test_subscription_attribution.py`
**Commit:** `ae5e77d`

Moved the `read_event` replay question above `lock_grants`, to the first
database read of `ingest`, and added `await self.session.rollback()` before the
return. `read_event` reads `audit.subscription_events`, which none of the grant
or usage locks protect, so a redelivery now takes no lock at all and gives its
read transaction back before the 200 is serialized. `get_db`
(`app/dependencies.py:45-56`) rolls back only on an exception and its teardown
runs after the response is on the wire, which is what made the old return leak
the locks.

New case `test_a_replay_takes_no_lock_and_gives_its_read_transaction_back`
asserts `writer.locked == []`, `writer.timeline == []` and
`(commits, rollbacks) == (0, 1)`. Mutation-probed by stashing the source hunk:
the case fails without it.

### WR-62 — `GET /examples` rejects a configured language whose example list is empty

**Files:** `src/nativespeaker/api/services/chats.py`,
`tests/unit/test_services.py`
**Commit:** `dbe34d9`

`get_examples` now tests membership (`lang not in self.examples`) rather than
truthiness of the value, which is the same question `create_chat` asks through
`supported_languages`. Config does not forbid an empty list —
`config.py:163` is `examples: dict[str, list[str]]` with no non-empty
validation — so the state is reachable.

`TestGetExamples::test_empty_list` pinned the old behaviour and was **updated to
the correct expectation**, not weakened: it now asserts the response is
`("en", [])` and that `"en"` is still in `supported_languages`.

### WR-63 — `chats_limit` is read, then the transaction ends and a provider call runs before the insert

**Files:** `src/nativespeaker/api/services/chats.py`,
`tests/unit/test_services.py`
**Commit:** `f10f3eb`

`create_chat` re-reads `count_chats` in the transaction that writes, after the
provider call and before `create_chat(chat)` — the pattern `send_message`
already uses at line 134 for the chat-existence re-read. There is no database
constraint behind the limit
(`migrations/20260818_01_initial-release.sql:53-61` declares none), so the last
read before the insert is the only guard there can be without adding one.

New case `test_a_chat_that_reached_the_limit_across_the_provider_call_is_not_inserted`
drives `count_chats` to answer 49 then 50 and asserts `create_chat` was never
called. Mutation-probed by stashing the source hunk: the case fails without it.

Scope note: `send_message`'s sibling guard (line 121) has the same shape. It was
left alone — the finding's cited lines are 90-109, and a correct re-check there
needs the re-read row rather than the identity-mapped `chat` object, which is
the WR-40 hazard again and a larger change than this finding asks for.

<!-- batch C -->

### WR-80: The conversion case seeds a state the anonymous writer can never produce

**Files modified:** `tests/e2e/test_claim_registered_grant.py`
**Commit:** `a98bbee`

Added `_mark_free_grant_consumed`, a helper that writes `ExternalIdentity.free_grant_consumed_at`
the way `crud/grants.py::activate_anonymous_device_grant:219` writes it unconditionally for every
anonymous grant. `TestTheConversionOfAnActiveAnonymousGrant` now seeds the marker at an instant two
hours before the request and asserts it is still that instant after the conversion. The case
previously ran the `stored.free_grant_consumed_at is None` arm of `crud/grants.py:330-332` — the
one arm the real conversion path can never reach — and never read the column.

Confirmed first that seeding the marker does not divert the case: `_claim_registered_grant`
consults `has_prior_free_grant` only on the `held == []` arm (`services/auth.py:255-258`), so the
conversion arm is unaffected.

**Mutation probe:** replaced `crud/grants.py:330-332` with an unconditional
`stored.free_grant_consumed_at = evaluated_at` — the conversion overwriting the instant the account
really spent its slot.

- pre-fix tree: `tests/e2e/test_claim_registered_grant.py` **16 passed**,
  `tests/unit/test_claim_precedence_registered.py tests/unit/test_grant_sources.py` **80 passed**
- with the strengthened case: **1 failed, 15 passed** — the failure is the new assertion

Mutation reverted in the same call; `git checkout -- src/nativespeaker/api/crud/grants.py`.

### WR-81: `refusal_sites.py` reads the package source with the locale encoding

**Files modified:** `tests/e2e/refusal_sites.py`
**Commit:** `aca2264`

`files_raising_the_refusal()` now calls `path.read_text(encoding="utf-8")`, with a comment naming
the reason. Scoped to this one call site; the many other bare `read_text()` calls under `tests/`
are outside this finding and outside this batch.

**Mutation probe** (the mutation here is the environment, not the source):

- before, `LC_ALL=C PYTHONCOERCECLOCALE=0 PYTHONUTF8=0`:
  `FAILED: UnicodeDecodeError 'ascii' codec can't decode byte 0xc2 in position 13137`
- after, same environment:
  `OK: ['app/dependencies.py', 'auth/app_store.py', 'auth/google_play.py']`

One correction to the finding, recorded rather than acted on: the two controls it names cannot be
run under `LC_ALL=C` even with this fix, because `EnvironmentConfig` also reads `config.yaml`
without an encoding and raises first (`ValidationError: 'ascii' codec can't decode byte 0xe2`).
That is a separate `src/` defect, outside this batch's six findings, and it does not make the
`refusal_sites.py` fix wrong — the scan is the module the finding is about, and it is now
locale-independent. Under the normal locale both webhook modules stay green (59 passed).

### WR-82: `_SpyLogger` turns an unanticipated log line into an `AttributeError`

**Files modified:** `tests/e2e/conftest.py`
**Commit:** `4146d73`

`_SpyLogger` now binds all six structlog levels (`debug`, `info`, `warning`, `error`, `critical`,
`exception`). The levels a case declared reach `spy.record`; every other level is bound to
`_discard`, so an unanticipated line runs on and is recorded by nobody instead of raising inside
the handler that wrote it.

I kept the declared-level filter rather than folding every level into one list, which the finding's
prose loosely suggested. The `levels` argument is load-bearing: `refusal_records`, `error_records`
and `info_records` each name one level over modules that log at three, and recording every level
would fold unrelated lines into assertions like
`assert [event for event, _ in spy.entries] == [...]`. The finding's own code block does the same
thing, so this follows the fix as written.

**Mutation probe:** added `logger.error("mutation_probe_extra_line")` at the top of
`app/error_handlers.py::app_error_handler`, a module `refusal_records` spies at `("warning",)` only.

- pre-fix `conftest.py`: **9 failed, 6 passed** in
  `TestEveryVerificationFailureAnswersTheOneBody` — the `AttributeError` surfacing as unrelated
  failures
- with the fix: **15 passed**, the warning assertions unchanged

Mutation reverted in the same call.

### WR-83: the post-commit DeviceCheck write failure has no e2e case

**Files modified:** `tests/e2e/test_claim_registered_grant.py`
**Commit:** `b2b9165`

Confirmed the seam is dead at the e2e tier: `script_write` / `write_answer` on
`tests/e2e/conftest.py::FakeDeviceCheckAdapter` are referenced by no e2e test, and
`tests/unit/test_claim_precedence*.py` drive their own separate fake with a fake grants seam.

Added `TestAFailedBitWriteAfterTheGrantIsDurable`, one case that scripts a failing `write_bits`
and pins the arm at `services/auth.py:283-290`: 200 with the `registered_account_grant`
entitlement, one grant row and one usage row really in PostgreSQL, `free_grant_consumed_at` set,
the challenge consumed, the read once and the write once per retry attempt, exactly one
`devicecheck_bit_write_failed` record, and neither the device token nor Apple's body anywhere in
the record.

**Mutation probe A** — deleted the swallow (`except Exception: raise`), so Apple's failure becomes
the caller's answer:

- pre-fix tree, whole e2e suite: **355 passed**
- with the new case: **1 failed, 16 passed**

**Mutation probe B** — leaked the label set
(`failure=str(failure), device_token=device_token`):

- pre-fix tree, whole e2e suite: **355 passed**
- with the new case: **1 failed, 16 passed**

Both mutations reverted in the same call; `git checkout -- src/nativespeaker/api/services/auth.py`.

### WR-84: the shared-error-body quota case asserts no status

**Files modified:** `tests/e2e/test_quota.py`
**Commit:** `bc7f689`

`test_the_no_grant_refusal_carries_the_shared_error_body` now asserts
`response.status_code == 429` and `response.json() == {"code": "quota_exceeded"}`, which subsumes
the key-list check. Comment follows the `# WR-90:` style the two already-hardened cases in the same
file use.

**Mutation probe:** replaced the no-grant `QuotaExceededError` raise in `services/quota.py:60`
with `MissingUsageRowError(uuid7())`, which answers a real 500 `{"code": "internal_error"}` — the
exact body the case's docstring rules out.

- original test under the mutation: **2 passed** (the guard hole, exactly as reported)
- strengthened test under the mutation: **2 failed**

Mutation reverted in the same call. My first probe attempt used a bare `RuntimeError`, which
escaped the ASGI transport rather than rendering a body and failed both versions; it proved
nothing, so I replaced it with the `AppError` above that actually produces the 500 body.

### WR-85: `_contended_challenge` is function-scoped

**Files modified:** `tests/e2e/test_challenge_store.py`
**Commit:** `11a4b0d`

`_contended_challenge` is now `@pytest_asyncio.fixture(scope="class", loop_scope="module")`, and
`store` is widened to `scope="module"` so the class-scoped fixture may depend on it. `store` is one
attribute read off the module-scoped `_app_lifespan.state`, so every other class in the file sees
the identical object. The class-scoped teardown sweep is safe: only `_contended_challenge` commits
rows under this module's issuer — every other class writes through the rolled-back
`_db_transaction`.

**Mutation probe** (structural, so measured on both sides):

- `--setup-show`, before: `SETUP F _contended_challenge` **3 times**;
  after: `SETUP C _contended_challenge` **once**, one `TEARDOWN C`
- shared-race probe, a temporary `print` of the challenge handle in each of the three cases:
  - function-scoped: `1YD3AJbZJ8SjYACnk3mxqg`, `MsQl9QA3FcpNLtkp3wc2gA`,
    `tIYgMBf3lvkTMHIFmX154g` — three independent races, so `test_no_contender_raised` judged a run
    the other two never saw
  - class-scoped: `eXyJiOs50VjdeAMz-zsLSw` three times — one race, which is what the "asserted
    first" contract claims

Probe prints removed before the commit; module: **32 passed**.

<!-- batch D -->

### WR-102: The retry-timing floor equals the actual total backoff to within ~2 ms
**Files:** `tests/unit/test_firebase_retry.py`, `tests/unit/test_devicecheck_adapter.py`
**Commits:** `c3120de`
**Changed:** The review's factual claim is correct — tenacity computes `multiplier * exp_base ** (attempt_number - 1)`, so with base `0.1` the two gaps are `0.1 s` then `0.2 s` (`0.3 s` total), not the `0.2 s`/`0.4 s` the comment claimed. The comment in both files was corrected. A new non-timing case `test_the_configured_gaps_are_the_two_this_floor_was_measured_against` now computes the gaps from `*_BACKOFF_BASE_SECONDS` / `*_BACKOFF_MAX_SECONDS` / `*_ATTEMPTS` and pins them as literals `[0.1, 0.2]` — the magnitude claim the wall clock was being asked to carry with 2 ms of margin. `FLOOR_SECONDS` moved `0.3 -> 0.25`, giving 50 ms of headroom instead of 2 ms.

**Deviation from the review's remedy, deliberately:** the review proposed `FLOOR_SECONDS = 2 * (BASE + 2*BASE) / 3`, deriving the floor from the production base. That is self-defeating: with a derived floor, shrinking `*_BACKOFF_BASE_SECONDS` to `0.001` — precisely the WR-21 regression this class exists to catch — moves the floor down with it and the test stays green. The floor is therefore kept as an absolute number and the derivation put in the new arithmetic case instead, so both properties are held.

**Mutation probe:** `FIREBASE_BACKOFF_BASE_SECONDS` and `DEVICECHECK_BACKOFF_BASE_SECONDS` set to `0.001` -> `6 failed, 78 passed`, including both new arithmetic cases and all four timing cases. Reverted in the same call.

### WR-122: The transient-status set is parametrised over itself
**Files:** `tests/unit/test_resilience_retry.py`
**Commits:** `1d8487e`
**Changed:** Added a module-level literal `RETRY_ELIGIBLE = (408, 409, 429, 500, 502, 503, 504)`, a new case `test_the_set_is_exactly_the_statuses_worth_retrying` asserting `_TRANSIENT_STATUSES == frozenset(RETRY_ELIGIBLE)`, and repointed the parametrisation at the literal so a member leaving the production set fails a case instead of removing one.

**Mutation probe:** `resilience.py:28` -> `_TRANSIENT_STATUSES = frozenset({408})` (a 429/500/502/503/504 reclassified as `PermanentLLMError`, never retried, never counted by the breaker) -> `7 failed, 58 passed` (previously 0 failed). Reverted in the same call.

### WR-123: `_BOUNDED_AUTH_FIELDS` omits both `RestoreRequest` fields
**Files:** `tests/unit/test_models.py`
**Commits:** `7d22ccb`
**Changed:** Confirmed `grep -rn "RestoreRequest" tests/` returns zero hits. Added both rows to `_BOUNDED_AUTH_FIELDS`, so the three existing parametrised cases (oversize refused, bound above the real value, empty refused) now cover them. `REALISTIC_STORE_NAME = len("google_play")` (11, against the source bound 32) and `REALISTIC_RESTORE_PROOF = 4 * 1024` (against the source bound 8192). The `4 KiB` figure is derived from a number already written down in `schemas/webhooks.py:4-7` — chain material for the envelope's three chain copies is "roughly 12 KB", with the two nested copies paying a second 4/3 inflation, so one un-nested copy plus its payload lands near 4 KiB — rather than invented; the comment says so. The control `limit >= 2 * realistic` therefore holds at exactly `8192 >= 8192`, which is the intended tripwire: a chain that grows will fail this and force the source bound to be raised rather than silently narrowing the margin. The class docstring was extended to name `restore_proof`.

**Mutation probe:** `schemas/auth.py` `provider` and `restore_proof` replaced with bare `str` (both `min_length` and `max_length` dropped) -> `6 failed, 60 passed` (previously 0 failed across the whole file). Reverted in the same call.

### WR-124: The unminted-primary-key guard skips any `id` typed `UUID | None`
**Files:** `tests/unit/test_tables_metadata.py`
**Commits:** `bd77770`, `e8a45dd`
**Changed:** Replaced the annotation filter with `_mints_a_uuid_key(model)`, selecting on the mapped column. Widened `test_the_walk_sees_the_tables_control` from a three-name `>=` to the exact nine-name set.

**The review's remedy was wrong and was corrected.** It proposed selecting on "a single primary-key column of type `sqlalchemy.Uuid`". That set includes `UserMonthlyUsage`, whose single UUID primary key is `grant_id` — a key this package never mints, because it is the grant's own id — and which has no `id` field at all, so `test_no_uuid_keyed_table_leaves_its_id_unminted` would have raised `KeyError: 'id'`. Verified against the live metadata: the review's predicate yields ten models, nine of which are the intended set. The implemented predicate additionally requires the column to be named `id`, which yields exactly the nine names the review itself lists.

**Mutation probe (two):** `tables/grants.py:63` -> `id: UUID | None = Field(default=None, primary_key=True)` -> `test_no_uuid_keyed_table_leaves_its_id_unminted` red (previously green). Repeated on `tables/purchases.py` `StorePurchase`, which carries no bespoke control of its own -> the same case red and nothing else. Both reverted in the same call.

### WR-120: The barrier's "no state filtering in SQL" guard reads only the text after `WHERE`
**Files:** `tests/unit/test_identities_crud.py`
**Commits:** `92223c3`, `98069b5`
**Changed:** Added `test_the_join_predicate_is_the_link_alone_and_filters_nothing`, which extracts the text between `LEFT OUTER JOIN core.users ON` and `WHERE` and asserts it equals `core.external_identities.user_id = core.users.id` exactly.

**The review's remedy was wrong and was corrected.** It proposed asserting `"identity_state" not in sql and "core.users.active" not in sql` over the *whole* compiled statement. That fails immediately: both columns appear in the statement's SELECT list (`core.external_identities.identity_state`, `core.users.active`) because `resolve` selects both entities and reads the state columns in Python. An absence assertion over the whole statement can say nothing here, so the predicate is pinned as an equality instead. The review also wrote the ON clause reversed (`core.users.id = core.external_identities.user_id`); SQLAlchemy renders it the other way round.

**Mutation probe:** `crud/identities.py:34` -> `.join(User, and_(col(ExternalIdentity.user_id) == col(User.id), col(User.active).is_(True)), isouter=True)` -> the new case red, `1 failed, 38 passed` (previously all 38 green). Reverted in the same call.

### WR-121: The charge's three statements are never checked against the values they are keyed on
**Files:** `tests/unit/test_quota_resolver.py`
**Commits:** `c172a4d`, `200deeb`
**Changed:** Ported `test_sync_resolver.py`'s `_bound()` helper and added `TestEveryLockedReadIsKeyedOnWhatTheOneBeforeItNamed` with four cases: the grant lock keyed on `USER_ID`, both grant bounds carrying the one captured instant, the usage lock keyed on the returned grant's `id`, and the allowance read keyed on that grant's own `tier_id`.

**Mutation probe (three, each reverted in the same call):**
- `lock_effective_grants(uuid4(), evaluated_at)` -> `test_the_grant_lock_is_keyed_on_the_caller_the_handler_named` red, `1 failed, 79 passed`.
- `lock_usage(uuid4())` -> `test_the_usage_lock_is_keyed_on_the_grant_the_first_lock_returned` red, `1 failed, 79 passed`.
- `monthly_credits('some-other-tier')` -> `test_the_allowance_read_is_keyed_on_that_grants_own_tier` red, `1 failed, 79 passed`.

All three previously left 76/76 green.

### WR-125: Three of the registered-claim writer's five refusal labels are pinned nowhere
**Files:** `tests/unit/test_spent_free_grant_refusal.py`
**Commits:** `599f0bf`, `35eeeee`
**Changed:** Added `_a_grant()` and `_locks_returning()` helpers (rescripting both lock tiers plus the usage lock a non-empty effective set makes the writer take) and three cases to `TestEachRefusalNamesTheArmThatFiredIt`, one per unpinned label.

**Label contract check, as instructed.** The three strings are not written down in `errors.py` or in `SHARED-INVARIANTS.md` — `errors.py` carries only a generic `cause: str | None` log field, and the specs do not enumerate `cause` values. The *arms* are written down, in `42-CONTEXT.md` D-09 and in `07-claim-registered-grant.md` step 11.2. Each case therefore constructs the arm's condition from that contract and asserts the label the arm carries, and each docstring cites the arm rather than the implementation:
- `other_grant_held` -> D-09(b), an active grant that is neither anonymous nor the caller's own registered one; driven by returning a `subscription` grant from `lock_effective_grants`.
- `unseen_active_grant` -> the concurrency tripwire for a row `ix_access_grants_one_active_per_user` sees and the effective read does not; driven by a row from `lock_active_grants` alone.
- `registered_grant_held` -> D-09(e), driven on the **conversion** arm. This is the only reachable driver: `_prior_free_grant_statement` covers both free sources with no status predicate, so `holds_grant_of_source(registered) == True` implies `has_prior_free_grant == True`, and the earlier `superseded is None and has_prior_free_grant` block would swallow every `held == []` case. The review's suggested `has_prior_free_grant` False / `holds_grant_of_source` True setup is a state the schema cannot produce.

**Mutation probe:** all three `return ActivationOutcome.refused, "<label>"` in `crud/grants.py` replaced with `None` -> the three new cases red, `3 failed, 116 passed` across `test_spent_free_grant_refusal.py`, `test_claim_ordering.py`, `test_claim_precedence_registered.py`, `test_conversion_carries_usage.py` and `test_grant_sources.py` (previously all 114 green). Reverted in the same call.

### WR-126: `iat` temporal validity is named by the spec and pinned by no case
**Files:** `tests/unit/test_jwt_security.py`
**Commits:** `9e59f1a`, `decb4c7`
**Changed:** Added `test_rejects_a_token_issued_in_the_future` (`iat = now + 3600`, expecting `BoundedReason.expired`, which is where `bounded_reason_for` maps PyJWT's `ImmatureSignatureError`) and its control `test_accepts_a_token_issued_inside_production_leeway` (`iat = now + 10`, inside the 30 s `DEFAULT_LEEWAY`).

**Mutation probe:** `DECODE_OPTIONS` given a `"verify_iat": False` entry — the exact "an added `options` entry" the finding names, and a real PyJWT option (`jwt/api_jwt.py:57`) — -> `test_rejects_a_token_issued_in_the_future` red, `1 failed, 65 passed` (previously 0 failed). Reverted in the same call.

### WR-100: The registered claim's D-09(e) refusal is never driven
**Files:** `tests/unit/test_claim_precedence_registered.py`
**Commits:** `cefd3cc`, `b3690a2`
**Changed:** Confirmed `_RecordingGrants.grant_of_source` is assigned by no test anywhere under `tests/`. Added `test_a_spent_registered_slot_refuses_the_conversion_and_still_consumes` — an active anonymous grant plus `grant_of_source = {registered_account_grant}`, asserting 403 / `REFUSED` / one consumption / no activation / no Apple call — and a matching `_registered_slot_spent` setup added to this module's `POST_CLAIM_OUTCOMES` tuple.

Note: the review directed the setup at `POST_CLAIM_OUTCOMES` "line 623", i.e. the tuple in `test_claim_precedence.py`. That tuple drives the *anonymous* route, where the registered lifetime row is not consulted; this module has its own `POST_CLAIM_OUTCOMES` (now line 664) and that is where the setup landed. The service code has also moved since the review snapshot — the D-09(e) guard now sits at `services/auth.py:246-249`, ahead of `read_active_grants`, and `_settle` has grown the `source` parameter from WR-60.

**Mutation probe:** `services/auth.py` -> `if False and await self.grants_db.holds_grant_of_source(...)` -> the new case red, `1 failed, 150 passed` across `test_claim_precedence_registered.py`, `test_claim_ordering.py`, `test_grant_sources.py` and `test_claim_precedence.py` (the review measured 145 passed / 0 failed for this same mutation). Reverted in the same call.

### WR-101: No unit test can see the registered claim writing the wrong tier
**Files:** `tests/unit/test_claim_precedence.py`, `tests/unit/test_claim_precedence_registered.py`
**Commits:** `4512f10`
**Changed:** `_RecordingGrants` grew `self.tiers: list[str]`, appended in `activate()`. `assert grants.tiers == ["registered"]` added to both mutating registered arms (`test_the_conversion_reaches_the_writer_without_reaching_apple_and_still_consumes` and `test_the_new_grant_reaches_the_writer_after_one_read_and_one_write`), and the mirror `assert grants.tiers == ["anonymous"]` to the anonymous claim's success case. The pre-existing `response.json()["entitlement"]["type"]` assertions are left in place — they are answered by `_RegisteredStubSync`, which is a legitimate separate seam; the tier is now pinned at the writer, which is where the decision is actually made.

**Mutation probe (two, both reverted in the same call):**
- `services/auth.py:275` `tier_id=REGISTERED_TIER_ID` -> `ANONYMOUS_TIER_ID` (a 10-credit allowance where 50 is owed) -> both registered cases red, `2 failed, 109 passed` across `test_claim_precedence_registered.py`, `test_claim_ordering.py`, `test_grant_sources.py`, `test_conversion_carries_usage.py` (the review measured 107 passed / 0 failed).
- `services/auth.py:213` `tier_id=ANONYMOUS_TIER_ID` -> `REGISTERED_TIER_ID` -> the anonymous success case red, `1 failed, 43 passed`.

<!-- batch E -->

### WR-143: The schema suite runs `DROP DATABASE ... WITH (FORCE)` against whatever host `.env` names

**Files modified:** `tests/schema/conftest.py`, `tests/schema/test_harness_guards.py` (new)
**Commit:** `ccc4153`

`admin_dsn()` is the one DSN that `CREATE DATABASE` and `DROP DATABASE ... WITH (FORCE)` execute
on, and `pyproject.toml:61`'s `env_files = [".env"]` loads whatever `.env` names into the
environment before collection. Added `_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})`
and a fail-closed check in `admin_dsn()`, with `NS_SCHEMA_TEST_ALLOW_REMOTE` as the deliberate
opt-out. A guard nothing tests is a comment, so a new `tests/schema/test_harness_guards.py` pins
the refusal, the opt-out, and all three loopback spellings.

**Mutation probe:** replaced the guard condition with `if False:` —
`test_a_remote_host_is_refused` FAILED (`1 failed, 4 passed`). Reverted in the same call.

### WR-144: Two concurrent pytest sessions destroy each other's scratch database

**Files modified:** `tests/schema/conftest.py`, `tests/schema/test_apply_rollback.py`,
`tests/schema/test_harness_guards.py`
**Commit:** `dd34d3c`

`SCHEMA_TEST_DB` is now `f"ns_schema_test_{os.getpid()}"`. The finding cited only
`conftest.py:18`, but `test_apply_rollback.py:12` carries the identical defect —
`ROLLBACK_TEST_DB = "ns_schema_test_rollback"` is a second fixed name that setup force-drops — so
it is per-session too. Both still satisfy `_SAFE_IDENTIFIER`, and both teardown drops are kept.
A new case asserts each name carries this process id and is still a usable identifier.

**Mutation probe:** restored `SCHEMA_TEST_DB = "ns_schema_test"` —
`test_the_name_carries_this_process_id[ns_schema_test]` FAILED. Reverted in the same call.
Confirmed after a full run that `datname LIKE 'ns_schema_test%'` returns no rows.

### WR-145: The `conn` fixture leaks its asyncpg connection when the transaction fails to start

**Files modified:** `tests/schema/conftest.py`, `tests/schema/test_harness_guards.py`
**Commit:** `5ec8d85`

`connection.transaction()` and `await tx.start()` moved inside a `try:` whose `finally:` closes the
connection, keeping the existing inner rollback guard. A new case drives the fixture's own async
generator with `asyncpg.connect` patched to a double whose `start()` raises
`TooManyConnectionsError`, and asserts `close()` still ran.

**Mutation probe:** restored the pre-fix shape (`tx.start()` outside the guard) —
`test_a_transaction_that_cannot_start_still_closes_the_connection` FAILED. Reverted in the same
call.

### WR-146: Setup outside the `try` leaks a connection and commits a tier row into the shared scratch database

**Files modified:** `tests/schema/test_subscription_ingestion.py`
**Commit:** `64be87f`

`insert_tier` and `insert_user` moved inside the `try:`, with `tier_id = user_id = None` ahead of
it, `_clean` guarded on `tier_id is not None`, and `conn.close()` in an outer `finally`.

**Mutation probe:** drove the case with `insert_user` patched to raise, against a throwaway
migrated database, on both shapes.

| shape | connection closed | stray `core.access_tiers` rows left committed |
|---|---|---|
| pre-fix | `False` | `1` |
| fixed | `True` | `0` |

### WR-147: `test_any_violation_the_loser_saw_was_the_unique_one` cannot fail on the SQLSTATE it names

**Files modified:** `tests/schema/test_restore_race.py`
**Commit:** `b7ee1e0`

Confirmed the finding: `_RecordingSession` writes `sqlstate` only inside `except IntegrityError`
handlers that also raise `integrity_at_flush` or `integrity_at_commit`, so with both flags `False`
the code is necessarily `None` and `in (None, "23505")` could not fail.

Took the strengthening option, not the deletion option. The existing case now asserts
`loser.sqlstate is None` — stronger than the tautology, and correct on a path the conditional owner
UPDATE arbitrates — and a new class
`TestTheUniqueIndexArbitratesWhereTheOwnerUpdateCannot` reaches the path the docstring names: one
account restoring two different subscriptions concurrently, so each CAS claims a row of its own and
`ix_access_grants_one_active_per_user` is the real arbiter. Its loser genuinely carries `23505` at
the flush, answers the retryable 500, and the account is left holding exactly one active grant.

**Mutation probes (two, both reverted in the same call):**
- `CREATE UNIQUE INDEX ix_access_grants_one_active_per_user` → `CREATE INDEX` in the migration:
  4 of the 5 new cases FAILED; the 25 pre-existing cases stayed green.
- `UNIQUE_VIOLATION = "23505"` → `"23503"` in `crud/violations.py` (the writer stops reading the
  index refusal as a lost race): all 5 new cases ERRORED; the 24 pre-existing cases stayed green.

### WR-140: The anonymous claim writer's lock-tier proof never runs the arm that writes

**Files modified:** `tests/schema/test_grant_locks.py`
**Commit:** `c0f8ec7`

`activation_statements` was refactored into `_anonymous_writer_run(uri, *, holding_grant)`,
mirroring `_registered_writer_run`, with two fixtures over it: `activation_statements`
(`holding_grant=True`, the refused arm, unchanged) and the new `anonymous_activated_statements`
(`holding_grant=False`, the arm that inserts the grant, the usage row and the identity marker).
Two new cases assert the activating arm's lock tiers and its plain identity re-read.

The divergent inline filter is gone: the SELECT-anchored predicate is now a shared
`plain_identity_re_reads` helper used by both arms, so the refused arm and the writing arm read the
statements the same way.

**Mutation probes (two, both reverted in the same call):**
- replaced the whole activating arm with `raise RuntimeError(...)`: both new cases ERRORED; the
  three pre-existing cases in `TestTheActivationAddsNoThirdLockTier` stayed green — the hole the
  finding described.
- added a third lock tier on the insert path (`SELECT ... FROM core.users ... FOR UPDATE`):
  `test_the_activating_arm_locks_the_grant_tier_alone` FAILED alone; the three pre-existing cases
  stayed green.

### WR-141: `relation_of` and `locking` cannot see a third lock tier taken by a join or a non-`FOR UPDATE` lock

**Files modified:** `tests/schema/test_grant_locks.py`
**Commit:** `b5489c5`

`locking()` now matches `_LOCK_CLAUSE = FOR (?:NO KEY )?UPDATE|FOR (?:KEY )?SHARE`, and
`relation_of` is replaced by `relations_of`, which returns every `core.`/`audit.` relation a
statement draws rows from. Deviating from the finding's sketch in one place: the relation pattern is
anchored on `FROM`/`JOIN`/`,` rather than the finding's bare `\b((?:core|audit)\.[a-z_]+)`, because
the bare form also matches the enum casts SQLAlchemy renders inside `WHERE` clauses
(`'active'::core.access_grant_status`) and would report them as locked relations. It preserves the
old loud-failure behaviour: a statement naming no relation is returned whole rather than as an empty
list every membership assertion passes.

All 14 third-tier assertions in the file were migrated. The ordered ones are now stronger than
before — `[["core.access_grants"], ["core.access_grants"], ["core.user_monthly_usage"]]` fails on a
joined statement, where the old one-relation-per-statement form could not. A new
`TestTheLockReaderSeesEveryTierAndEverySpelling` class pins both blind spots directly.

**Mutation probes (all reverted in the same call):**
- restored both blind spots in the reader alone (`FOR UPDATE` literal, `FROM (…)` first match): the
  three non-`FOR UPDATE` spellings and the joined-relation case FAILED (`4 failed, 37 passed`).
- end-to-end: added a real `SELECT ... FROM core.users ... FOR NO KEY UPDATE` third tier to the
  anonymous writer's insert path. With the fixed reader,
  `test_the_activating_arm_locks_the_grant_tier_alone` FAILED. With the pre-fix reader, all 14
  third-tier cases passed — the lock was invisible.

### WR-142: The "exact-set object inventory" pins no columns except `core.users`, and no index key columns at all

**Files modified:** `tests/schema/test_inventory.py`
**Commit:** `e8bdc80`

Two catalogue captures added in the file's existing `assert_exact_set` style, both read out of
`pg_catalog` on a live apply under `PINNED_SEARCH_PATH` rather than transcribed from the migration:

- `COLUMNS` / `EXPECTED_COLUMNS` — every column of every `core` and `audit` table as
  `schema.table.column: type [NOT NULL] [DEFAULT …|GENERATED …]`, 118 entries.
- `INDEX_KEYS` / `EXPECTED_INDEX_KEYS` — every index's key columns and its uniqueness flag, 44
  entries. This also closes a second hole beside it: `INDEXES` already selected `indisunique` and no
  case had ever asserted it, so an index stripped of `UNIQUE` passed the whole inventory.

**Mutation probes (three, each reverted):**
- `ix_access_grants_one_active_per_user ON (user_id)` widened to `(user_id, tier_id)` — the exact
  mutation the finding names: `TestIndexKeys::test_every_index_key_matches_capture` FAILED alone;
  the index-name set and the predicate cases stayed green.
- a `probe_column TEXT` added to `core.access_grants`: both `TestColumns` cases FAILED.
- `event_type TEXT NOT NULL` → `event_type TEXT` on `audit.subscription_events`:
  `test_every_column_spec_matches_capture` FAILED.

## Skipped Issues

<!-- batch A -->

### WR-02, the `db:` block half — ratified, and already refused once on the same ground

`db.pool_size: 12` stays in `config/config.yaml`. **Phase 41 D-16** (`41-CONTEXT.md:168`,
`STATE.md:670`) ratified exactly this placement and costed exactly this loss: "the tracked
YAML forecloses `DB_POOL_SIZE` from `.env`". Removing the block also drops the pool from 12
to the field default of 5 and reopens **STATE.md blocker A-15** (pool exhaustion at three
concurrent chat posts), which D-16 was taken to close, and breaks D-16's own conformance
case `TestTheTrackedPoolSizeMergesWithTheEnvironmentCredentials`. Phase 40's WR-03 was the
same finding and was skipped for the same reason.

**A correction to the review's own ground:** WR-02 cites Phase 44 D-16 (`REQUIREMENTS.md:400`)
as ratifying its rule. That passage is about the two stores' product catalogues — "only the
catalogue is tracked in `config/config.yaml`; the three deployer values stay in the
environment" — and its "three deployer values" are the store settings, not `db.pool_size`.
The decision that actually governs this block is Phase **41** D-16, which settled it the
other way.

### WR-24, the raise half — ratified, and the remedy is the failure it was built out of

The proposed split (`DefaultCredentialsError` → `None`, `RefreshError`/`TransportError` →
`RuntimeError`) reverses a settled contract and restores a known outage.

- `.planning/REQUIREMENTS.md:599`, keep-rule 14, states the contract as the reason the
  function exists at all: "`auth/firebase.py::_application_default_credential` | KEEP | Rule
  — its name *is* the contract: ADC if the environment supplies it, `None` if it does not,
  **never a raise**."
- The `except` arm's own comment records the executed case: "Caught narrowly, those escaped
  `build_admin_apps` and `lifespan` and **crashlooped the pod**, under a docstring promising
  the opposite."
- `tests/unit/test_firebase_adapter.py::TestBuildAdminApps::test_every_adc_failure_is_that_absent_state_and_never_a_dead_pod`
  is parametrized over `DefaultCredentialsError`, `RefreshError`, `TransportError` and
  `MutualTLSChannelError` and pins the outcome as "never a dead pod". Making the proposed fix
  pass would mean rewriting a case that exists to forbid it.

The finding's underlying observation is real and unfixed: a Ready pod whose boot-once probe
failed cannot create a user for the life of the process. Closing it properly means either a
readiness signal that reflects degraded capability, or a credential read that can be retried
after boot — both change behaviour the config layer settled deliberately ("an absent
credential lets boot proceed and the route fail closed"), and both are decisions to reopen
rather than a code-review fix. The wording half, which promised the operator a recovery that
cannot arrive, was fixed above.

<!-- batch B -->

- **WR-42** — *The App Store envelope bound turns an oversized notification into
  a permanently lost lifecycle event.* Skipped: the remedy is self-defeating and
  two of its premises are false. Details below.

### Why WR-42 was skipped

**Its "200-and-drop contract" does not exist on this route.** The fix text says
moving the size check into `verify_app_store_notification` lets "the route keep
its 200-and-drop contract". It has no such contract: every verification failure
raises `NotificationRejected`, which is `status = 401`, `code = "auth_required"`
(`errors.py:503-507`). A bad Apple envelope already earns a non-2xx that Apple
retries.

**The remedy makes the loss it names worse, not better.** Today an over-limit
body is a 422 that Apple retries on its bounded schedule (~72 hours), and it
leaves a `validation_error` WARNING naming `body.signedPayload` /
`string_too_long` (`app/error_handlers.py:53-64`) — a window in which an
operator can raise the bound and redeploy. The proposed 200-and-drop removes
that window and makes the loss immediate and unrecoverable. Both end in loss;
only one of them can be repaired in flight.

**The claimed symmetry with the Pub/Sub sibling does not hold.** The reason
`PubSubPushMessage.data` gives for being unbounded is stated in its own comment:
"Pub/Sub acknowledges 2xx alone and **redelivers every other status**, so a body
pydantic refuses is a 422 this subscription retries **forever**." Apple does not
redeliver forever — it retries a bounded number of times and stops. The property
the Pub/Sub decision turns on is exactly the property Apple lacks, so the review's
"only one of the two directions was reasoned about" is not right: the two
transports were reasoned about separately because they differ.

**The bound is a prior ratified review fix on an unauthenticated route.**
`43-REVIEW.md` WR-01 ("`signedPayload` has no length bound on an unauthenticated
route") added it, and phase 37's review raised it from 16 KiB to 64 KiB. The
proposed `signedPayload: str = ""` deletes it at the model.

**The residual risk does not justify a change.** 65536 is ~2.7x the 18-24 KB the
module's own comment calls typical, and `STATE.md:506` records that no real Apple
notification has ever reached this route. Under AGENTS.md ("don't over-engineer"),
speculatively re-shaping a working guard is not warranted.

<!-- batch C -->

None. All six findings held against the live code.

<!-- batch D -->

None. All ten findings held, and all ten are fixed.

<!-- batch E -->

None. All eight findings held on the current code.

## Verification

Run by the orchestrator at HEAD `e8bdc80`, after every batch had finished. The schema and e2e suites need their marker; without it pyproject's default `addopts` deselects them silently.

```
.venv/bin/ruff check src tests                                   All checks passed!
.venv/bin/pytest tests/unit -q -p no:cacheprovider               1831 passed
.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema    277 passed
.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e          356 passed
.venv/bin/ty check src                                          All checks passed!
git status --short                                              (clean)
```

Baseline before the fix pass was ruff clean / unit 1791 / schema 251 / e2e 355 / ty 0 diagnostics. Nothing regressed. The suites gained 40 unit cases, 26 schema cases and 1 e2e case, all of them guards that fail against the mutation the matching finding named. No test was weakened to make it pass, and no failure was excused as pre-existing.

---

_Fixed: 2026-09-10T04:51:50Z_
_Fixer: Claude (gsd-code-fixer, five sequential batches)_
_Iteration: 1_
