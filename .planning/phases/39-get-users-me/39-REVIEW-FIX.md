---
phase: 39-get-users-me
fixed_at: 2026-09-09T22:41:00Z
fix_scope: critical_warning
iteration: 1
findings_in_scope: 13
fixed: 12
skipped: 0
partial: 1
status: all_fixed
---

# Phase 39: Code Review Fix Report

**Source review:** `.planning/phases/39-get-users-me/39-REVIEW.md`
**Baseline:** `a6ff85f` — ruff clean; unit 1658; schema 249; e2e 354; ty 3 diagnostics.
**Scope:** the 13 Warnings. The 25 Info findings were out of scope and are untouched.

**Summary:** 12 findings fixed outright. One (WR-42) is fixed in its sharper half and its other
half is refused with the reason recorded below — the review's suggested fix for that half creates a
worse defect than it removes. Nothing was skipped for being unreachable or already fixed.

Every source fix carries a regression test, and for the five where a test could distinguish a real
fix from a green one, the test was proven by re-introducing the defect and watching it fail
(WR-40, WR-42, WR-70, WR-71, WR-02/WR-20 by construction).

## Fixed

### WR-01 — an attributes-only Pub/Sub push logged at ERROR under the bound's name

**Commit:** `76f6e1e`
**Files:** `src/nativespeaker/api/auth/google_play.py`, `tests/unit/test_models.py`,
`tests/unit/test_google_play_notifications.py`

Split the two arms of `developer_notification_from`. An empty `data` now records
`google_play_message_without_data` at INFO; only a body past `PUBSUB_DATA_LIMIT` keeps
`google_play_message_out_of_range` at ERROR with its length. The parametrised case in
`test_models.py` that ran both inputs through one id named "out_of_range" is split in two, and a new
class in `test_google_play_notifications.py` asserts the level and the event name of each arm
against the module's logger spy.

### WR-02 — the stale-success guard held only while the breaker was open

**Commit:** `1240d43` (docstring trim `45e404a`)
**Files:** `src/nativespeaker/api/resilience.py`, `tests/unit/test_resilience_retry.py`

`CircuitBreaker` now carries a `_generation` counter bumped on every trip, and `record_success`
takes the generation the attempt was stamped with instead of reading `_opened_at`. `attempt()`
stamps it immediately before the provider call, so an answer from an attempt admitted before the
trip is discarded however long it took to land. `record_failure`'s own "do not accumulate while
open" guard is unchanged: reading the current state is exactly the property that arm wants.

The new case opens the breaker, lets `before_call`'s elapsed arm reset it, records two fresh
failures with a straggler success between them, and reads the reopen off the trip counter; its
control shows a success stamped after the reset still clears the tally.

### WR-03 — `json_log_path` was a config field nothing read

**Commit:** `7b49d09`
**Files:** `src/nativespeaker/api/config.py`, `tests/unit/test_config.py`

Deleted the field, which is the option the review preferred and the one AGENTS.md asks for. Nothing
in `src/`, `tests/`, `config/`, `k8s/` or `.env.example` set it, so no deployment value had to
follow. `extra="forbid"` now makes `JSON_LOG_PATH` a loud refusal instead of a silent no-op. A new
class asserts every `AppConfig` field whose name mentions "log" is a parameter `setup_logging`
accepts, so the two surfaces cannot drift apart again, with a control that fails on an empty walk.

### WR-20 — `Chat.id` minted no id, so a `Chat()` without one inserted NULL

**Commit:** `ea8d003` (docstring trim `eb1df06`)
**Files:** `src/nativespeaker/api/tables/chats.py`, `src/nativespeaker/api/services/chats.py`,
`tests/unit/test_tables_metadata.py`

`Chat.id` now has the `default_factory=uuid7` every sibling table declares, and the redundant
`id=uuid4()` at `services/chats.py:94` is gone — with it the only uuid4 identifier in the schema.
Verified empirically: `Chat(user_id=uuid4(), title='x').id` is now a uuid7, where it was `None`.

The regression guard walks every mapped model the `tables` package exports rather than pinning
`Chat` alone. It is scoped by annotation to UUID-typed `id` fields: `AccessTier.id` is a `str` (the
seeded tier name) and `StorePurchaseToken`/`UserMonthlyUsage` have composite keys and no `id`
field at all, so a blanket "every id is uuid7" would have been false.

### WR-40 — the out-of-order guard was skipped when the pre-lock read saw no row

**Commit:** `adf0d03`
**Files:** `src/nativespeaker/api/services/subscriptions.py`,
`src/nativespeaker/api/crud/subscriptions.py`, `tests/unit/test_subscription_attribution.py`

The guard now re-reads the whole canonical row under the grant locks (`read_subscription`, which
already forces `populate_existing`) and reads every conjunct off it, including the `subscription`
and both tier ids the superseded event row records. The `stored is not None` conjunct — the one
that short-circuited the guard when the rival's *insert* was what the pre-lock read missed — is
gone. `SubscriptionsDB.read_signed_at` had no other caller and was deleted; leaving a
column-select of the stale clock behind invites the same shape back.

The recording stand-in gained a `rival` hook that runs once, immediately after the unlocked
`read_subscription`, so the under-lock read answers with the row it committed — which is how the
staleness arises in production rather than a restatement of it. The two existing clock cases were
moved onto that hook. The new case is the one the review describes: no pre-lock row, one buyer on
both deliveries (so the owner guard has nothing to say), different `notification_uuid`s (so the
replay arm has nothing either), and an older `active` payload against a committed `revoked` row.

**Proven:** re-introducing the `stored is not None` conjunct fails the new case and nothing else;
restoring the fix returns 49 passed.

**Not folded in:** IN-41 asks for `old_tier_id` to come from the same under-lock read. It is Info
and out of scope, so `old_tier_id` is still taken at `:53`. The under-lock row is now in hand, so
that fix is a one-line follow-up.

### WR-41 — the `no_effective_grant` 429 sent a `Retry-After` of up to 31 days

**Commit:** `7b84811`
**Files:** `src/nativespeaker/api/services/quota.py`, `tests/unit/test_quota_resolver.py`

The shared value is now `min(seconds_until_rollover(evaluated_at), RETRY_AFTER_CEILING_SECONDS)`
with the ceiling at 300 s. One value still serves both branches, so the anti-oracle clause of
SHARED-INVARIANTS holds and the header is still sent "where computable".

Confirmed the premise the old comment got wrong: `GrantsDB.activate_*` (`crud/grants.py:188,291`)
and `RestoreService.restore` all write `starts_at=evaluated_at`, and
`_effective_grants_statement`'s predicate is `starts_at <= evaluated_at`, so a claimed or restored
grant is effective on the very next request. The absent-grant branch therefore does change before
the period does.

`test_an_exhausted_allowance_names_the_rollover` asserted the raw 10-day value; it is updated to
the correct expectation rather than relaxed, and a new control drives a charge at
2026-08-31T23:59Z to show the cap is a ceiling and not a constant — a header past the boundary
would send a client back after its own allowance had already reset.

### WR-42 — partially fixed: the delete race, not the caps

**Commit:** `fc57619`
**Files:** `src/nativespeaker/api/services/chats.py`, `tests/unit/test_services.py`

**Fixed — the delete race.** `send_message` now re-reads the chat by `(chat_id, user_id)` in the
transaction that writes, after the provider call, and raises `InvalidChatError` when it is gone.
The caller gets the same 404 it would have got a moment earlier instead of an opaque 500 from the
`core.messages.chat_id` foreign key. **Proven:** removing the re-read fails the new case, whose
control shows a chat that is still there is still written.

The residual window between that re-read and the message insert is sub-millisecond, inside one
transaction with no provider call in it, and is the same read-then-write shape as every other
writer in this codebase. A `FOR KEY SHARE` lock would close it exactly, but it is a locking mode
used nowhere else here and is disproportionate to a chat-history row.

**Refused — the cap re-count. The review's fix is wrong.** It proposes re-counting after the
provider call and raising `ChatHistoryLimitError` before the insert. `QuotaService.charge` has by
then already **committed** a monthly credit (`services/chats.py:107-108` records that ordering
deliberately, and `services/quota.py:1-2` states that a failed call is not refunded). So the
suggested fix introduces a new failure mode in which a paying caller loses a credit and receives no
answer — to prevent a 51st row in a 50-row history cap that confers no entitlement and costs
nothing. The delete-race fix does not have this problem: that request fails either way, so
converting its 500 into the correct 404 is a pure improvement.

The cap therefore stays best-effort under concurrency, which is what it has always been: it is read
outside any lock, and only a locking read or a database-level constraint would make it exact.
Neither is warranted for a history cap on a pre-launch, sub-$5 product whose burst is already
bounded at the gateway (AGENTS.md).

### WR-60 — no `.dockerignore`

**Commit:** `827d603`
**File:** `.dockerignore` (new)

Added. It mirrors `.gitignore`'s record of the secret shapes (`.env`, `.env.*` with
`!.env.example`, `*.p8`, `*.pem`, `*.key`, the ADC JSON) and excludes `.git/`, `.venv/`,
`.planning/`, `.claude/`, `.gsd/`, `tests/`, `migrations/`, `k8s/` and the caches. Nothing lands in
a layer today — the Dockerfile copies only four paths and never does `COPY . .` — but the context
transfer is the exposure once the builder is not local.

I first wrote this as a `*` + re-include whitelist, which fails closed and cannot rot. I replaced it
with the denylist because no Docker daemon is reachable from this environment (the socket refuses
the connection), and I will not ship a pattern whose matcher semantics I cannot execute. The
denylist is unambiguous by inspection; the whitelist's directory re-inclusion is not. No test was
added: nothing in `tests/` reads a repository-level packaging file today, and inventing that
surface for one file is machinery this project has not asked for.

### WR-61 — the chart could not attach its routes to a Gateway in another namespace

**Commit:** `86e5dc8`
**Files:** `k8s/values.yaml`, all four `k8s/templates/httproute-*.yaml`

Added `gateway.namespace` (default `""`, meaning the release's own namespace, which is what an
omitted `parentRefs[].namespace` means to Gateway API) and threaded it through all four route
templates with `{{- with }}`, so an empty value renders exactly the YAML that renders today. The
value's comment states the failure mode (green install, passing probes, every request 404ing) and
that a Gateway elsewhere also needs its listener's `allowedRoutes.namespaces` to admit this
namespace, which is outside this chart.

No `helm` binary is available here, so I verified by rendering both branches of the conditional in
Python and parsing the result: empty gives `[{'name': 'eg-gateway'}]`, set gives
`[{'name': 'eg-gateway', 'namespace': 'platform-gw'}]`, on all four templates.

### WR-70 — the request-correlation test exercised no production code

**Commit:** `5db9b45`
**File:** `tests/unit/test_logging.py`

`test_request_id_bound_in_context` is replaced by
`test_the_middleware_binds_the_correlation_fields_onto_every_record`, which drives two real requests
through `RequestLoggingMiddleware` and reads the contextvars from inside a handler — the one place
the bindings are visible, since `capture_logs` does not merge contextvars. It pins the exact key set
(`method`, `path`, `request_id`), both values, and a distinct id per request.

**Proven:** deleting the `bind_contextvars(...)` call from `logs.py` fails the new case, where it
left the old one green. This makes checkable the premise that 38-06-SUMMARY, 37.1-07-SUMMARY and
phase 39 D-10 all rest on.

### WR-71 — the message-text tripwire matched two spellings the code never uses

**Commit:** `afd0a3a`
**File:** `tests/unit/test_conflict_classification.py`

The check now runs on the syntax tree: `_exception_names` collects every name an `except ... as`
clause binds anywhere in `_CREATION_SOURCE`, and `_reads_a_caught_message` reports every `str(name)`
call, every f-string interpolating one, and every `name.args` access on those names. The old
`"str(exc" not in code` / `"str(e)" not in code` substring pair is gone. A control asserts the walk
finds `conflict` and `failure`; a parametrised control asserts each of the three spellings is
reported on a synthetic handler.

**Proven:** replacing `if not is_unique_violation(conflict)` in `crud/identities.py` with
`if "external_identities_issuer_subject" not in str(conflict)` — the exact regression this tripwire
exists to catch, which the old guard passed — now fails
`test_conflicts_are_never_discriminated_by_message_text`.

### WR-90 — two quota cases discarded the response

**Commit:** `965c600`
**File:** `tests/e2e/test_quota.py`

Both cases now capture the response and assert the status the case is about before reading the
counter: `429` + `quota_exceeded` at `:166`, and `500` at `:221`. Any non-charging failure — a 401
at the barrier, a 422, a 503 from an open circuit — leaves the same counter and the same empty
usage table, so neither case proved a refusal before.

### WR-91 — `_contended_challenge` did its risky setup outside the `try`

**Commit:** `d9fa720`
**File:** `tests/e2e/test_challenge_store.py`

The `try` now opens where the engine starts existing, so `issue()`'s committed row and the
ten-connection `max_overflow=0` pool are both covered by the existing `finally`.

**Proven:** raising immediately after `issue()` runs the teardown block with the new code; with the
old shape the `finally` was never entered, the pool was never disposed and the row was never swept.

## Corrections to the review

- **WR-42's cap half is wrong as prescribed.** Re-counting after the provider call refuses a
  request whose credit is already committed, which is a worse outcome than the over-cap row it
  prevents. Recorded in full above; the delete-race half was fixed.
- **WR-40's fix left `read_signed_at` behind.** It has no other caller once the guard re-reads the
  entity, so it was deleted rather than left as a stale-read helper.
- **WR-20's suggested regression test** pins `Chat.id` alone. Generalising it to every mapped table
  required scoping by annotation, because `AccessTier.id` is a seeded `str` key and two tables have
  no `id` field at all.

Everything else the review asserted about these 13 findings held on inspection. In particular I
re-confirmed by execution: `Chat(...)` really did construct with `id = None`; the claim and restore
writers really do set `starts_at=evaluated_at` against a `starts_at <= now` predicate; and
`test_request_id_bound_in_context` really did survive the deletion of the whole `bind_contextvars`
call.

## Verification

Measured after the last fix, at `d9fa720`, on the branch `gsd/v2.0-authentication-entitlements` in
the main checkout (no worktree was created — this repository is a submodule and the workflow's
worktree step was skipped by instruction):

| Gate | Result | Baseline at `a6ff85f` |
|---|---|---|
| `ruff check src tests` | All checks passed | clean |
| `pytest tests/unit` | **1674 passed** | 1658 passed |
| `pytest tests/schema -m schema` | **249 passed** | 249 passed |
| `pytest tests/e2e -m e2e` | **354 passed** | 354 passed |
| `ty check src` | **3 diagnostics** | 3 diagnostics |

The unit suite grew by 16 cases: the new regression tests and their controls, less the one deleted
by WR-70. `tests/unit/test_docstring_bar.py` — the AGENTS.md three-line docstring ratchet — is back
at its recorded baseline of zero for all five roots; three of my new docstrings breached it and
were shortened (commits `45e404a`, `eb1df06`, and inline in `adf0d03`).

---

_Fixed: 2026-09-09_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
