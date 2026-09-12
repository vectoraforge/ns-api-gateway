# Phase 47: Stop threading an evaluation instant through the layers - Research

**Researched:** 2026-09-11
**Domain:** Internal refactor of this codebase — dependency removal, parameter removal, clock placement
**Confidence:** HIGH (every claim below is read from a file in this repository or measured against the project's own PostgreSQL in this session)

## Summary

There is no library question in this phase. `get_evaluated_at` is one FastAPI dependency in
`app/dependencies.py`; its instant reaches **308 occurrences** across `src/` and `tests/` under two
names, `evaluated_at` and `now`. In `src/` there are **145 occurrences in 13 files**. Removing it is
mechanical everywhere except two places, and both are load-bearing.

**The first is criterion 3's `now()`.** Only **two** SQL statements in the whole codebase compare a
column against the current time: the effective-grant predicate in `crud/grants.py` and the challenge
claim in `crud/challenges.py`. Rewriting the first one to `now()` **breaks 11 of the 41 e2e quota
tests**, measured in this session, not reasoned about. The cause is that `tests/e2e/conftest.py`
wraps each test in one outer transaction joined by `create_savepoint`, and PostgreSQL's `now()` is
`transaction_timestamp()` — fixed at the **outer** transaction's start, which is before the test
seeds its grant. `clock_timestamp()` in the same place passes all 41. This is the phase's one real
decision and it needs the user, not the planner.

**The second is the flagged conflict.** `SHARED-INVARIANTS.md:44` binds every phase to "ONE captured
evaluation time or one consistent snapshot per request", and `REQUIREMENTS.md:226` records SYNC-01 as
met on exactly that property. This phase deletes it. Per the milestone rule at `ROADMAP.md:98` —
"flag conflicts, never resolve them silently" — the phase owes a recorded flagged conflict, on the
precedent of the six this milestone already carries.

**Primary recommendation:** plan five waves — (1) the leaves that take a parameter and read no clock
(`auth/app_store.py`, `auth/google_play.py`), (2) `crud/` writers, each reading `datetime.now(UTC)`
**once at the top of the method** so the timestamps a single write stamps stay equal to each other,
(3) the services and `ChallengesDB.now`, (4) `dependencies.py`, `routers/auth.py` and the test pass,
(5) the flagged-conflict record. Gate the `now()` decision behind a blocking checkpoint in wave 1.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Reading the current time | API / Backend | Database / Storage | Every read is server-side; the open question is only whether the clock is Python's or PostgreSQL's |
| Effective-grant window | Database / Storage | — | `_effective_grants_statement` is the one predicate; it runs in SQL either way |
| Challenge expiry | Database / Storage | — | `ChallengesDB.claim`'s WHERE is the only expiry evaluation anywhere (`services/auth.py:139` comment) |
| Term/status judgement from a store proof | API / Backend | — | `_transaction_status`, `_status_for` are pure Python over a decoded payload |
| Written timestamps (`created_at`, `starts_at`, …) | API / Backend | Database / Storage | Columns carry `DEFAULT CURRENT_TIMESTAMP` but the crud always overrides it |

## Project Constraints (from CLAUDE.md / AGENTS.md)

`CLAUDE.md` is `@AGENTS.md`. Binding directives that touch this phase:

- **Comments — only where necessary; default to none. One line each.** A comment "never explains the
  design, the request lifecycle, a rule enforced in another module, or a decision made elsewhere"
  (`AGENTS.md:17-22`). Every comment listed in § Comments and Docstrings to Delete fails this rule
  already; criterion 4 makes deleting them mandatory rather than optional.
- **Docstrings — three lines maximum, stating what the entity does** (`AGENTS.md:8-15`).
- **Package layout** (`AGENTS.md:24-40`): `crud/` is database access, `services/` owns transaction
  boundaries — "`commit()` and `rollback()` are transaction boundaries and therefore business logic;
  they live in `services/`, not in `crud/`". A crud method reading its own clock does **not** violate
  this; it is not a transaction boundary.
- **Function shape** (`AGENTS.md:~68`): "Delete a function that is only a step." A new pure helper
  must state a rule, not name a value. `monthly_period_for` and `seconds_until_rollover` both state a
  rule and stay.
- **Product context:** first version, no users, subscription under $5/month, do not over-engineer.
- **Vocabulary (user memory):** dependency / handler / service / crud / adapter / table. Do not coin
  nouns. "The instant" and "the evaluation instant" are this phase's subject, not new nouns.
- **Worktrees (user memory):** `use_worktrees: true` in `config.json`, but this repo is a submodule
  whose `.git` is a file, so GSD's `IS_WORKTREE` detection is always true here and tracking writes
  vanish. **Tell executors it is false.**

## User Constraints

No `47-CONTEXT.md` exists — `/gsd:discuss-phase` was not run. The ROADMAP entry
(`.planning/ROADMAP.md:788-806`) is the authoritative scope. Nothing below invents a user decision;
every choice the roadmap leaves open is in § Open Questions with a recommendation.

## Phase Requirements

No requirement IDs are mapped. The phase is behavior-preserving: every route must answer as before.
Two *existing* requirement records are nevertheless touched — see § The Flagged Conflict.

---

## Finding 1 — `now()` breaks the e2e harness (measured)

### The PostgreSQL fact

Probed against this project's own database this session
[VERIFIED: live probe, PostgreSQL 17.11 (Debian 17.11-1.pgdg13+)]:

```
now() stable across statements in one tx: True
now() == transaction_timestamp():        True
second statement_timestamp moved:        True
clock_timestamp moved:                   True
delta now->clock within tx (s):          0.251678
CURRENT_TIMESTAMP == now():              True
```

`now()` is `transaction_timestamp()`: it is the instant the **transaction** began, not the instant
the statement runs. `clock_timestamp()` is the true wall clock and advances within a transaction.

### The consequence in the e2e harness

`tests/e2e/conftest.py:253-275` opens **one transaction per test** on one connection and swaps the
app's session factory for one bound to that connection with
`join_transaction_mode="create_savepoint"`. Every app session inside the test therefore runs in the
**outer** transaction, and its `commit()` releases a savepoint rather than ending it. `now()` inside
a route is frozen at the moment `_db_transaction` began.

Probed directly [VERIFIED: live probe this session]:

```
rows visible to  starts_at <= now():             0
rows visible to  starts_at <= clock_timestamp(): 1
```

— for a row inserted with a Python `datetime.now(UTC)` **after** the transaction opened, which is
exactly what `tests/e2e/conftest.py:647` (`seed_grant`) does.

### The falsification run

I patched `_effective_grants_statement` to `func.now()` and ran the e2e quota suite
[VERIFIED: `.venv/bin/pytest -q -m e2e tests/e2e/test_quota.py`, this session]:

```
11 failed, 30 passed
assert response.status_code == 200
E   assert 429 == 200
```

429 is `no_effective_grant`. Every seeded grant became invisible. I then replaced it with
`func.clock_timestamp()` and re-ran the same file plus the sync and anonymous-claim suites:

```
tests/e2e/test_quota.py                                     41 passed
tests/e2e/test_sync.py + test_claim_anonymous_grant.py      25 passed
```

The source file was restored from a backup afterwards and the baseline re-confirmed green
(`41 passed`); `git diff --stat` shows only `.planning/` files, unchanged from session start.

### What this means for the plan

There is a second, production-side half of the same hazard. `_claim_anonymous_grant`,
`_claim_registered_grant` and `restore` all write a grant and then read the entitlement back in the
same request (`routers/auth.py:125,148,176`). In production the service `commit()`s first, so the
entitlement read runs in a **new** transaction whose `now()` is later than the written `starts_at` —
safe. In e2e the commit is a savepoint release, so it is **not** safe. The e2e harness is where this
surfaces, and it surfaces as a red suite, not as a silent wrong answer.

Three ways out, in the planner's order of preference — **but see Open Question 1: this is a user
decision, not the planner's.**

---

## Finding 2 — only two SQL statements compare against the current time

Exhaustive: `grep -rn "func.now\|now()\|current_timestamp" src/` returns **one hit** and it is a
comment (`crud/grants.py:49`). Nothing in `src/` uses a database clock today. The two statements that
compare a column against *the instant the caller supplied* are:

**(a) `crud/grants.py:26-38` — `_effective_grants_statement`** [VERIFIED: src/nativespeaker/api/crud/grants.py:26-38]

```python
def _effective_grants_statement(user_id: UUID, evaluated_at: datetime):
    """Every grant of `user_id` effective at `evaluated_at`, ascending by id."""
    return (
        select(AccessGrant)
        .where(col(AccessGrant.user_id) == user_id,
               # `== active`, not `!= revoked`: a NULL or a future member must fail closed here.
               col(AccessGrant.status) == AccessGrantStatus.active,
               col(AccessGrant.starts_at) <= evaluated_at,
               or_(col(AccessGrant.ends_at).is_(None),
                   col(AccessGrant.ends_at) > evaluated_at))
        # No `.limit(...)`: the caller must see a second effective grant and fail closed on it.
        .order_by(col(AccessGrant.id).asc())
    )
```

This is **a comparison against the current time** → criterion 3 says `now()`. Four callers:
`lock_effective_grants` (grants.py:104) and `read_effective_grants` (grants.py:111), reached from
`services/quota.py:50`, `services/sync.py:28`, `services/auth.py:177,226,288`, `crud/grants.py:172`
and `crud/grants.py:235`.

**(b) `crud/challenges.py:64-75` — `ChallengesDB.claim`** [VERIFIED: src/nativespeaker/api/crud/challenges.py:64-75]

```python
    async def claim(self, session: AsyncSession, *,
                    challenge_id: str,
                    now: datetime) -> bool:
        """Move issued -> claimed. The one serialization point and the only expiry check; `True` wins it."""
        result = await session.exec(
            update(AuthChallenge)
            .where(col(AuthChallenge.challenge_id) == challenge_id,
                   col(AuthChallenge.claimed_at).is_(None),
                   col(AuthChallenge.expires_at) > now)
            .values(claimed_at=now)
            .returning(col(AuthChallenge.id)))
        return len(result.all()) == 1
```

Mixed: `expires_at > now` **is** a comparison against the current time; `claimed_at = now` is a
written value. If both become `func.now()` they stay self-consistent, which is the desirable
property. The same `now()`-vs-savepoint hazard does **not** bite here, because `expires_at` is
`issue`-time + 300s in the future — an *earlier* `now()` only makes a challenge look more alive,
never less. The unit suites that script an expired challenge write `expires_at` in the past and still
work.

**Every other `evaluated_at` in `crud/` is a written Python value**, not a comparison:
`crud/subscriptions.py` (28 occurrences, all `created_at` / `updated_at` / `ends_at` / a
`monthly_period_for` argument), `crud/identities.py` (11, all `created_at` / `updated_at` /
`registered_at`), the write half of `crud/grants.py`.

`_hold_clock_statement` (subscriptions.py:68-75) and `_claim_owner_statement` (54-65) compare against
a value the **caller read**, never against the current time. They keep a bound Python parameter.

---

## Finding 3 — the call chains, router → service → crud

Remove in this order, so no wave leaves a dangling argument.

### Chain A — the quota charge (`POST /chats`, `POST /chats/{id}/messages`)

```
get_chat_service(evaluated_at=Depends(get_evaluated_at))   dependencies.py:109,116
  ChatService.__init__(evaluated_at)                       services/chats.py:36,45
    .charge(user_id, evaluated_at=self.evaluated_at)       services/chats.py:99,131
      QuotaService.charge(user_id, evaluated_at)           services/quota.py:41
        seconds_until_rollover(evaluated_at)               services/quota.py:26,43   [pure helper — keeps its parameter]
        lock_effective_grants(user_id, evaluated_at)       services/quota.py:50  → SQL comparison
        monthly_period_for(evaluated_at)                   services/quota.py:70      [pure helper — keeps its parameter]
        usage.updated_at = evaluated_at                    services/quota.py:92      [written value]
```

`ChatService` then holds **no** time at all: its only use is the two `charge` calls. Delete the
constructor field outright. `QuotaService.charge` reads `instant = datetime.now(UTC)` once at the
top — it drives the retry-after, the SQL window, the period and `updated_at`, and the phase's
existing property ("one captured instant decides both the predicate and the period",
`tests/unit/test_quota_resolver.py:408`) survives **inside the method**.

### Chain B — `/auth/sync` and the three write routes that answer with a sync body

```
get_sync_service(evaluated_at=Depends(get_evaluated_at))   dependencies.py:149,150
  SyncService.__init__(evaluated_at)                       services/sync.py:19,22
    monthly_period_for(self.evaluated_at)                  services/sync.py:26       [pure helper]
    read_effective_grants(user_id, self.evaluated_at)      services/sync.py:28   → SQL comparison
```

`read_entitlement` reads `instant = datetime.now(UTC)` once. `SyncService.__init__` then takes `db`
alone. **Note the test that pins the shape:** `tests/unit/test_sync_resolver.py:432` asserts
`set(vars(service)) == {"grants_db", "evaluated_at"}` — it becomes `{"grants_db"}`.

### Chain C — `/auth/challenge` (the `now=` carrier)

```
issue_challenge(evaluated_at=Depends(get_evaluated_at))    routers/auth.py:57
  ChallengesDB.issue(..., now=evaluated_at)                routers/auth.py:71 → crud/challenges.py:35,38,55
```

The router is the only handler that declares the dependency directly. `issue` computes
`expires_at = now + timedelta(...)` **and returns it in the response body**, so it should read
`datetime.now(UTC)` in Python rather than move to SQL.

### Chain D — `AuthService` (create-user, upgrade, both claims)

```
get_auth_service(evaluated_at=Depends(get_evaluated_at))   dependencies.py:140,145
  AuthService.__init__(evaluated_at)                       services/auth.py:68,78
    challenge_store.claim(now=self.evaluated_at)           services/auth.py:138  → SQL comparison + written value
    challenge_store.consume(now=self.evaluated_at)         services/auth.py:396  → written value only
    read_effective_grants(user_id, self.evaluated_at)      services/auth.py:177,226,288  → SQL comparison
    activate_anonymous_device_grant(evaluated_at=…)        services/auth.py:208  → crud/grants.py:167
    activate_registered_account_grant(evaluated_at=…)      services/auth.py:264  → crud/grants.py:229
    identities_db.flip_provider(evaluated_at=…)            services/auth.py:333  → crud/identities.py:128
    identities_db.insert_account(evaluated_at=…)           services/auth.py:362  → crud/identities.py:91
```

After the sweep `AuthService` holds no instant. Every crud method it calls reads its own.

### Chain E — restore

```
get_restore_service(evaluated_at=Depends(get_evaluated_at))  dependencies.py:162,164
  RestoreService.__init__(evaluated_at)                       services/restore.py:36,47
    starts_at = min(proof.purchased_at or inst, inst)         services/restore.py:68    [Python read]
    end > self.evaluated_at                                   services/restore.py:101   [Python read — the boundary]
    insert_subscription(evaluated_at=…)                       services/restore.py:114   → crud/subscriptions.py:155
    claim_subscription_owner(evaluated_at=…)                  services/restore.py:129   → crud/subscriptions.py:236
    insert_purchase(evaluated_at=…)                           services/restore.py:146   → crud/subscriptions.py:264
    write_subscription_grant(evaluated_at=…)                  services/restore.py:159   → crud/subscriptions.py:321
    _this_month()  →  self.evaluated_at.astimezone(UTC)…      services/restore.py:176   [Python read]
    app_store.verify_transaction(proof, self.evaluated_at)    services/restore.py:198   → auth/app_store.py:120
    play.read_for_restore(evaluated_at=…)                     services/restore.py:203   → auth/google_play.py:134,324
```

`restore()` is the one service method where **four** separate uses want the same instant: the
`starts_at` clamp (line 68), the term-open check (line 101), `_this_month()` (lines 82 and 128) and
the crud writes. Read `instant = datetime.now(UTC)` once at the top of `restore()` and pass it to
`_this_month(instant)` and to the term helper. The crud methods below still read their own — see
Open Question 2.

### Chain F — the Google Play webhook dependency

```
verify_google_play_notification(evaluated_at=Depends(get_evaluated_at))   dependencies.py:181,211
  play_subscriptions.read(..., evaluated_at=…)                            auth/google_play.py:129,275
    _status_for(state, expiry, evaluated_at)                              auth/google_play.py:198,316  [pure helper]
```

### Chain G — ingestion (both webhooks)

```
get_subscriptions_service(evaluated_at=Depends(get_evaluated_at))   dependencies.py:154,156
  SubscriptionsService.__init__(evaluated_at)                        services/subscriptions.py:24,29
    starts_at = min(notification.purchased_at or inst, inst)         services/subscriptions.py:105  [Python read]
    term_ends_at <= self.evaluated_at                                services/subscriptions.py:109  [Python read]
    append_event / upsert_subscription / insert_purchase /
    write_subscription_grant (evaluated_at=…)                        87,120,135,144,156
```

---

## Finding 4 — where each Python read of the instant should move

| Site | Today | Recommendation |
|------|-------|----------------|
| `services/quota.py::charge` | 4 uses of the parameter | one `instant = datetime.now(UTC)` at the top of `charge` |
| `services/sync.py::read_entitlement` | 2 uses | one read at the top of `read_entitlement` |
| `services/restore.py::restore` | 4 uses + 2 seam calls | one read at the top of `restore`; pass it to `_this_month(instant)` and the term helper |
| `services/subscriptions.py::ingest` | 3 uses | one read at the top of `ingest` |
| `crud/grants.py::activate_anonymous_device_grant` | 9 uses | **one read at the top of the method** — see below |
| `crud/grants.py::activate_registered_account_grant` | 10 uses | one read at the top of the method |
| `crud/subscriptions.py` (7 writer methods) | 1-6 uses each | one read at the top of each method |
| `crud/identities.py::insert_account` / `::flip_provider` | 6 and 4 uses | one read at the top of each method |
| `crud/challenges.py::issue` | 2 uses (`expires_at` base, `created_at`) | one read at the top of `issue` |
| `auth/app_store.py::verify_transaction` | 1 use | one read, handed to `_transaction_status` |
| `auth/google_play.py::read` / `::read_for_restore` | 1 use each | one read each, handed to `_status_for` |

**One read per method, not one per assignment.** Two e2e tests assert exact equality between two
columns a single crud write stamps:

- `tests/e2e/test_claim_anonymous_grant.py:106-107` — `assert identity.free_grant_consumed_at == grant.starts_at`
- `tests/e2e/test_claim_registered_grant.py:199-200` — the same assertion

Both survive a single read at the top of `activate_anonymous_device_grant`; both go red if each
assignment calls the clock. The two comments above them ("The one instant: the grant, the marker and
the usage period all came from it.") are comments whose subject is the shared instant and go under
criterion 4, but the **assertions** should stay — they still pin a real property.

### Candidates for "a small pure helper that takes the datetime it computes from"

Three exist already and all three stay, unchanged in shape:

- `tables/grants.py:31` — `monthly_period_for(evaluated_at)` [VERIFIED: src/nativespeaker/api/tables/grants.py:31-33]
- `services/quota.py:26` — `seconds_until_rollover(evaluated_at)`
- `auth/app_store.py:36` / `auth/google_play.py:197` — `_transaction_status`, `_status_for`

Two are worth **adding**, because they are where the deleted dependency's testability lived:

1. **The restore term check.** `services/restore.py:100-101` is the only comparison a test can no
   longer reach once the clock moves inline, and there is a case pinned on its exact boundary
   (`tests/e2e/test_restore_subscription.py:419-439`). Extract it:
   `_open_term(candidates: Iterable[datetime | None], instant: datetime) -> datetime | None`.
   It states a rule ("the first term still open at this instant"), so `AGENTS.md` § Function shape
   admits it. The boundary case then moves to a unit test over the helper.
2. **`RestoreService._this_month`** already is one; change it from reading `self.evaluated_at` to
   taking `instant` as a parameter.

**Do not** add a helper to `auth/` without budgeting for it:
`tests/unit/test_auth_package_shape.py:13` carries `CURRENT = (8, 24, 67)` — files, classes,
functions — and a new function in `auth/app_store.py` or `auth/google_play.py` fails it. Phase 49
also rewrites this tuple; whichever phase lands second re-measures it.

---

## Finding 5 — comments and docstrings to delete (criterion 4)

Every line below names the removed dependency or the shared instant. All fail `AGENTS.md:17-22`
independently of this phase.

| File:line | Text |
|-----------|------|
| `app/dependencies.py:100` | `"""One instant per request, shared by construction: FastAPI caches this dependency per request."""` (goes with the function) |
| `services/sync.py:1` | module docstring — `"…the entitlement one caller holds at one instant, read and never written."` (reword; the module survives) |
| `services/sync.py:21` | `# One instant for this request; nothing below it reads the clock again.` |
| `services/sync.py:25` | `"""Report the entitlement `user_id` holds at the captured instant, …"""` (reword) |
| `services/restore.py:46` | `# One instant for this request; nothing below it reads the clock again.` |
| `services/restore.py:67` | `` # `10-restore-subscription.md:84(3)` requires the clamp to the captured instant. `` — also cites a spec file, already banned by Phase 37.1's cross-cutting constraint |
| `services/restore.py:156` | `# The term checked above, and never a second reading of it that could drift from it.` |
| `services/restore.py:174` | `"""The first day of the captured instant's UTC month, …"""` (reword) |
| `services/quota.py:90` | `` # `updated_at` is stamped from the captured instant, not a clock. `` — becomes **false**, must go |
| `services/auth.py:77` | `# One instant for this request; nothing below it reads the clock again.` |
| `services/subscriptions.py:28` | `# One instant for this request; nothing below it reads the clock again.` |
| `tables/grants.py:66` | `# The timestamps carry no default. The creating transaction owns the clock.` — judgement call; see Open Question 3 |
| `crud/grants.py:27,101,110` | three docstrings naming `evaluated_at` by parameter name (reword) |
| `crud/challenges.py:36` | `` """…from the caller's `now`, never renewed."""`` (reword) |
| `tests/e2e/test_restore_subscription.py:109-111` | the `pinned_evaluation_instant` docstring (goes with the fixture) |
| `tests/e2e/test_claim_anonymous_grant.py:106` | `# The one instant: the grant, the marker and the usage period all came from it.` |
| `tests/e2e/test_claim_registered_grant.py:199` | `# The one instant: the grant, the marker and the usage period all came from it.` |
| `tests/unit/test_quota_resolver.py:408,416` | class and case docstrings about "one captured instant" (reword to what the method now guarantees) |
| `tests/schema/test_subscription_ingestion.py:141,198,334,710` | four docstrings naming the captured instant (reword) |
| `tests/unit/test_restore_proof.py:69,115,231` | `# One captured instant for every case below…` and two docstrings |
| `tests/unit/test_google_play_notifications.py:65,139,328` | the same pattern, plus `` "`evaluated_at` is passed explicitly: left to its default it is the `Depends` object itself." `` |
| `tests/unit/test_subscription_attribution.py:959` | `"""The control: the captured instant is what the guard compares against…"""` |

`crud/grants.py:49-51` — the `now()`-cannot-appear-in-an-IMMUTABLE-index-predicate comment — is
**not** about the shared instant and must **stay**. It explains why `_active_grants_of_statement` has
no time window at all, which is exactly the misreading criterion 3 invites.

---

## Finding 6 — every test that passes, pins or overrides the instant

**Total: 163 occurrences across 27 test files.** Grouped by what the planner must do.

### Delete outright

| File | Why |
|------|-----|
| `tests/unit/test_sync_clock_capture.py` (163 lines, 6 `evaluated_at` occurrences) | Criterion 4 names it. It exists only to pin the one-read-per-request discipline: `TestSyncServiceReadsNoClock` asserts `services/sync.py` makes **no** clock call, which this phase inverts; `TestTheInstantIsCapturedOnceAndSharedByEveryService` asserts `get_evaluated_at` exists and that three service dependencies declare it. Its `_clock_reads` AST walker and 12-case control suite are genuinely good and have **no other caller** — deleting them loses nothing else. |

### Override to remove

| File:line | What |
|-----------|------|
| `tests/e2e/test_restore_subscription.py:107-117` | `pinned_evaluation_instant` — the **only** `dependency_overrides[get_evaluated_at]` in the repository, confirmed by exhaustive grep. Three cases use it. |

Its three consumers, and what replaces each:

1. `test_a_verified_proof_attaches_the_paid_grant_and_the_body_reports_it` (line 243) — asserts
   `scripted_app_store_notifications.restore_calls == [(RESTORE_PROOF, pinned_evaluation_instant)]`.
   The seam stops taking the instant, so the recorded tuple loses its second member. **Replaced by
   nothing** — the assertion existed to prove the threading.
2. `TestTheSameAccountGooglePlayRestore::test_a_live_purchase_token_…` (line 755) — the same, over
   `restore_calls[…]["evaluated_at"]`. Same disposition.
3. `test_a_term_ending_at_the_captured_instant_is_not_open` (line 419) — **this one is real.** It
   proves the predicate at line 101 is `>` and not `>=`: a term ending exactly at the instant is
   over. Its own docstring says "Only a pinned instant names that equality, because a live clock
   never lands on it." **Replaced by a unit test over the new `_open_term` pure helper**, which takes
   the datetime it compares against. Do not drop it; it guards a paid-entitlement boundary.

The scripted-seam signatures in `tests/e2e/conftest.py:369-371, 496-500, 507-512` drop their
`evaluated_at` parameter and the recorded call dicts lose the key.

### Rewrite — the largest cost

| File | Count | What changes |
|------|-------|--------------|
| `tests/schema/test_subscription_ingestion.py` | 35 | A `@dataclass` buyer carries `evaluated_at: datetime` (line 126) and constructs `SubscriptionsService(evaluated_at=…)` (line 133). Roughly a dozen assertions are **exact equality against that instant** — `held[0]["ends_at"] == buyer.evaluated_at` (363, 396, 416), `held[0]["starts_at"] == buyer.evaluated_at - _A_MONTH` (330), `usage["monthly_period"] == buyer.evaluated_at.strftime("%Y-%m")` (341). Exact equality becomes impossible. **Replace with a bracket**: capture `before = datetime.now(UTC)` around the call and assert `before <= value <= after`. Where the value is a **derived offset** (`buyer.evaluated_at + _A_MONTH`), the term comes from the notification the test built, so those stay exact. |
| `tests/schema/test_grant_locks.py` | 22 | Same shape. Line 707 is the sharp one: `evaluated_at=instant - evaluated_before` deliberately activates a grant *in the past*. With the parameter gone the crud writer always stamps now, so that case must **seed the grant row directly** (as `tests/e2e/conftest.py::seed_grant` does) rather than go through `activate_*`. Line 50 `_lock_grants(user_id, evaluated_at=None)` is a raw-SQL helper — unaffected if the predicate stays a bound parameter, rewritten if it becomes `now()`. |
| `tests/unit/test_google_play_notifications.py` | 15 | Line 493-506 `test_a_canceled_term_is_judged_against_the_instant_passed_in` is parametrized over instants — **move it to `_status_for` directly**, which keeps its parameter. Line 521-523 asserts the dependency threaded the instant to the seam — delete. The rest are call-site argument removals. |
| `tests/unit/test_restore_proof.py` | 14 | `EVALUATED_AT` is a module constant passed into `verify_transaction` / `read_for_restore` / `RestoreService(...)`. The boundary cases move to `_transaction_status` / `_status_for` / `_open_term`; the rest are argument removals. Lines 529 and 545 define fake seams whose signatures shrink. |
| `tests/unit/test_quota_resolver.py` | 8 | Lines 287, 299, 423, 459 pass a **past** instant to exercise rollover and the retry-after boundary. **Prefer controlling the stored state, not the clock**: rollover fires on `usage.monthly_period < monthly_period_for(now)`, so setting the stub's `monthly_period` to a past month proves the same branch without a clock. The retry-after-ceiling case (459, `near_the_boundary`) tests `seconds_until_rollover`, which keeps its parameter — call it directly. |
| `tests/unit/test_sync_resolver.py` | 5 | Line 432's `set(vars(service)) == {"grants_db", "evaluated_at"}` → `{"grants_db"}`. Line 122's `_read` helper loses its keyword; line 323's stale-period case moves to controlling `monthly_period`. |
| `tests/unit/test_subscription_store_clock.py` | 3 | `evaluated_at=T2` into `upsert_subscription` / `hold_subscription_clock`. The `clock_read` parameter — the thing these cases actually test — is untouched. Argument removals only. |
| `tests/unit/test_subscription_attribution.py` | 3 | Lines 248, 683 construct `SubscriptionsService(evaluated_at=NOW)`; line 194 reads `fields["evaluated_at"]` off a recorded crud call. |
| `tests/unit/conftest.py` | 2 | Line 149 `recording_charge(self, *, user_id, evaluated_at)` monkeypatches `QuotaService.charge` — its signature must track. Line 175 builds the `ChatService` fixture. |
| `tests/unit/test_quota_seam.py` | 2 | Same two shapes. |
| `tests/unit/test_spent_free_grant_refusal.py`, `test_conversion_carries_usage.py`, `test_claim_precedence.py`, `test_claim_precedence_registered.py`, `test_upgrade_precedence.py` | 2-3 each | Fake crud classes whose method signatures mirror the real ones (`async def lock_effective(self, user_id, evaluated_at)`). Mechanical. |
| `tests/e2e/conftest.py` | 6 | The three scripted seam methods above. |
| `tests/e2e/test_quota.py` | 2 | Argument removals. |
| `tests/schema/test_sync_lock_freedom.py`, `test_restore_race.py`, `test_claim_race.py`, `test_subscription_race.py`, `test_create_race.py`, `test_create_atomicity.py` | 9, 3, 2, 1, 1, 1 | Service/crud construction sites. |
| `tests/unit/test_subscription_grant_write.py`, `test_identity_flip.py`, `test_create_user_rollback.py`, `test_conflict_classification.py` | 1 each | Single call sites. |

### Not affected

`tests/unit/test_monthly_period.py` (3 occurrences) — its `evaluated_at` mentions are **fabricated
string literals** in its own control cases (lines 56-58), not reads of the real source. It passes
unchanged even if `monthly_period_for`'s parameter is renamed. Verified by running it this session.

### Does the repo already freeze time anywhere?

**No.** `grep -rn "freezegun\|freeze_time\|time_machine" src/ tests/` returns **zero hits**
[VERIFIED: exhaustive grep, this session]. There is no installed time-freezing library and no
monkeypatch of `datetime.now` anywhere. **Do not introduce one** — this is a first-version product
under an explicit "do not over-engineer" instruction, and every case above has a cheaper replacement
(a pure helper, a bracketed assertion, or controlling stored state instead of the clock).

The repo does have a **`timing` marker** for exactly this class of test:
`pyproject.toml:75` — *"marks tests whose assertion is wall-clock dependent (report separately with
-m timing)"*. Five tests use it today, including `tests/schema/test_grant_locks.py:216`. Any new
bracketed-window assertion that could flake under load belongs behind `@pytest.mark.timing`.

---

## Finding 7 — the flagged conflict (this phase owes one)

`ROADMAP.md:98`: *"`SHARED-INVARIANTS.md` binds every phase and overrides any conflicting phase brief
— flag conflicts, never resolve them silently."*

`SHARED-INVARIANTS.md:44` [VERIFIED: /home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md:44]:

> - Derive every time-dependent value from ONE captured evaluation time or one consistent snapshot per request; `current_period` is `YYYY-MM`, UTC calendar month.

`SHARED-INVARIANTS.md:41`:

> - Effective-grant selection always uses the shared predicate (`status='active' AND starts_at <= now AND (ends_at IS NULL OR ends_at > now)`), never `status` alone.

`REQUIREMENTS.md:226` [VERIFIED: .planning/REQUIREMENTS.md:226]:

> - [x] **SYNC-01**: The endpoint returns the effective grant, `current_period`, `monthly_used`, and stored `identity_provider`, all derived from one captured evaluation time

And `ROADMAP.md` Phase 38 success criterion 1: *"Grant, `current_period`, and `monthly_used` all
derive from one evaluation time and match what quota enforcement would independently act on at the
same instant."*

**Phase 47 deletes the property all four describe.** Even the `now()` route does not restore it: a
request here spans several transactions (`services/restore.py:164`, `services/auth.py:150,…` each
commit mid-request), so `now()` is one snapshot per *transaction*, not per *request*.

**This is a record to write, not a decision to make.** The milestone carries six flagged conflicts
already and the pattern is established (see the Phase 40, 43, 44, 45 rows in `REQUIREMENTS.md:754-760`).
The planner should add a final-wave plan that amends `REQUIREMENTS.md` under SYNC-01 with a dated
note, exactly as Phase 40's UPGRADE-02 amendment reads, and **does not edit `SHARED-INVARIANTS.md`**.
Phase 38 plan 38-04 did edit that file, but under a blocking decision checkpoint flagged as a one-way
door — so if the planner prefers to strike the invariant instead, that must be its own checkpointed
task.

---

## Finding 8 — what belongs to Phases 48, 49 and 50, not here

| File | Phase 47 changes | Also touched by | Keep out of 47 |
|------|------------------|-----------------|----------------|
| `app/dependencies.py` | delete `get_evaluated_at`; drop the parameter from 6 dependencies | **49** (`get_challenge_store` deleted), **50** (whole-file rewrite onto `get_runtime`) | Do not touch `get_session_factory`, `get_firebase_adapter`, `get_devicecheck_adapter`, or any `request.app.state.*` read. Do not remove `Request` parameters. Phase 50 explicitly depends on 47 leaving this file otherwise intact. |
| `routers/auth.py` | drop `get_evaluated_at` from the import list and `issue_challenge`'s signature | **49** (`get_challenge_store` import), **48** (`AuthIdentity` → `LinkedIdentity` annotations) | Do not change any `AuthIdentity` annotation (48) and do not touch `challenge_store: ChallengesDB = Depends(get_challenge_store)` (49). |
| `crud/challenges.py` | remove the `now` parameter from `issue`, `claim`, `consume` | **49** (`ChallengesDB` construction moves into `AuthService`) | Do not change `__init__`/`__repr__` or how the class is built. 49 owns construction; 47 owns the method signatures. |
| `services/auth.py` | remove the `evaluated_at` constructor field and its 9 uses | **48** (`AuthIdentity`/`LinkedIdentity`), **49** (`challenge_store` constructor arg) | Leave the `challenge_store` parameter and every identity annotation alone. |
| `auth/google_play.py` | drop `evaluated_at` from `read` and `read_for_restore` — **in both the `PlaySubscriptionSource` Protocol (129, 134) and the concrete class (275, 324)** | **49** (deletes the Protocol outright) | 47 must edit the Protocol's method signatures too, or the concrete class stops conforming. 49 then deletes it. If 49 lands first, 47 edits only the concrete class. |
| `tests/unit/test_auth_package_shape.py` | only if a helper is added to `auth/` | **49** (rewrites the tuple at the end) | Prefer adding no function to `auth/`; put the new `_open_term` helper in `services/restore.py`. |
| `tests/unit/test_google_play_notifications.py`, `test_devicecheck_adapter.py`, `test_adapter_interfaces.py` | argument removals only | **49** (deletes whole test classes) | Do not delete `TestThePushTokenSeamIsTheAnnotation` — that is 49's. |
| `app/lifespan.py` | **nothing** | 49, 50 | 47 does not touch this file. |
| `schemas/auth.py` | **nothing** | 48 | |

47, 48 and 49 are declared independent of each other; 50 depends on 47 and 49. The overlap above is
real but small, and the `now()`/parameter split keeps it to signature lines. **Recommend 47 runs
first**, because 50 names it first in its dependency line.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Making a wall-clock test deterministic | A `Clock` protocol, an injectable time source, a test-only `FakeClock` | A pure helper taking the datetime, plus a bracketed `before <= v <= after` assertion | The injectable clock *is* `get_evaluated_at`. Rebuilding it under a new name defeats the phase. |
| Freezing time for the boundary cases | A first use of `freezegun` / `time_machine` | `_open_term(candidates, instant)` and the three helpers that already take their datetime | Zero time-freezing dependency exists today; adding one for three cases is over-engineering under `AGENTS.md`'s product context. |
| Comparing a stored period against the current month | A second `strftime("%Y-%m")` | `monthly_period_for` | `tests/unit/test_monthly_period.py` is a ratchet asserting `tables/grants.py` is the **only** file in `src/` that formats `%Y-%m`. A second copy fails it. |
| Giving a column a default so the write path can drop its value | Adding `default_factory=` to `AccessGrant.starts_at` | Leave the model alone; supply the value | The columns already carry `DEFAULT CURRENT_TIMESTAMP` in the migration (`migrations/20260818_01_initial-release.sql:223`); the crud deliberately overrides it, and services need the written value in memory for the response. |
| Detecting a lost race | A pre-check against the clock | The existing `is_unique_violation` + `ActivationOutcome` path | Untouched by this phase. |

---

## Common Pitfalls

### Pitfall 1: `now()` in the effective-grant predicate silently empties the e2e suite

**What goes wrong:** 11 of 41 e2e quota tests answer 429 instead of 200; sync and claim suites follow.
**Why:** `now()` is `transaction_timestamp()`, and `tests/e2e/conftest.py` joins every app session to
one outer transaction that opened before the test seeded its grant.
**How to avoid:** decide Open Question 1 before any code is written; if `now()` is chosen, the same
plan must move every e2e seed's `starts_at` into the past **and** solve the write-then-read-back
problem on the three routes that answer with a sync body.
**Warning sign:** a 429 with `no_effective_grant` in a test that seeds a grant.

### Pitfall 2: one clock read per assignment breaks two e2e equality assertions

**What goes wrong:** `identity.free_grant_consumed_at == grant.starts_at` goes red.
**Why:** `activate_anonymous_device_grant` stamps 9 fields from one value today.
**How to avoid:** one `instant = datetime.now(UTC)` at the top of each crud writer method.

### Pitfall 3: the restore boundary case has nowhere to go

**What goes wrong:** `test_a_term_ending_at_the_captured_instant_is_not_open` is deleted for
convenience and the `>` / `>=` distinction at `services/restore.py:101` stops being guarded.
**Why:** it is the one case that genuinely needed a pinned clock, and its e2e route is gone.
**How to avoid:** extract `_open_term` and move the case to a unit test over it, in the same commit.

### Pitfall 4: exact-equality assertions in the schema suites

**What goes wrong:** `held[0]["ends_at"] == buyer.evaluated_at` and ~a dozen siblings.
**How to avoid:** bracket the request. Mark anything that could flake `@pytest.mark.timing`.

### Pitfall 5: the Protocol and its implementation drift

**What goes wrong:** `auth/google_play.py:129,134` (the `PlaySubscriptionSource` Protocol) keeps
`evaluated_at` while the concrete class at 275/324 drops it; nothing fails at import, and
`tests/unit/test_adapter_interfaces.py` catches it late.
**How to avoid:** change all four signatures in one commit.

### Pitfall 6: `-m ''` is not the unit suite

**What goes wrong:** a wave is gated on `-m ''` in the belief it needs no database.
**Why:** measured this session — `-m ''` collects **2570** tests, which is *everything* including the
362 e2e and 291 schema. The unit-only run is the bare `.venv/bin/pytest` (addopts already carry
`-m 'not e2e and not schema'`), which collects **1917**.

### Pitfall 7: the worktree flag

Per user memory: this repo is a submodule whose `.git` is a file, so GSD's `IS_WORKTREE` detection is
always true and tracking writes vanish. **Executors must be told it is false.**

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/pytest` | criterion 5 | ✓ | pytest 9.0.2, Python 3.14 | — |
| `uv` | alternative runner | ✓ | 0.12.5 | `.venv/bin/pytest` |
| PostgreSQL (localhost, `.env`) | `-m e2e`, `-m schema`, `-m ''` | ✓ **reachable now** | 17.11 (Debian 17.11-1.pgdg13+) | none — the suites are silently deselected without their marker |
| `ruff` | the project's standing lint gate | ✓ | via `uv run ruff check src tests` | — |
| freezegun / time_machine | — | ✗ | — | not needed; see Finding 6 |

Reachability was confirmed by running `tests/schema/test_sync_lock_freedom.py` (**3 passed**) and the
full `tests/e2e/test_quota.py` (**41 passed**) against the live database this session, plus two
direct `asyncpg` probes. **Nothing in the environment was changed or repaired.**

Exact invocations, confirmed working here:

```bash
.venv/bin/pytest -q              # 1917 collected — the unit suite, no database needed
.venv/bin/pytest -q -m ''        # 2570 collected — EVERYTHING, database required
.venv/bin/pytest -q -m e2e       #  362 collected — database required
.venv/bin/pytest -q -m schema    #  291 collected — database required
```

`pyproject.toml:71` — `addopts = "-v --tb=short -m 'not e2e and not schema'"`. `pyproject.toml:72-76`
declares three markers: `e2e`, `schema`, `timing`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (lines 65-76) |
| Quick run command | `.venv/bin/pytest -q` (1917 tests, no database) |
| Full suite command | `.venv/bin/pytest -q -m ''` then `-m e2e` then `-m schema` |

### Success criterion → test map

| Criterion | Behavior | Test type | Automated command | Exists? |
|-----------|----------|-----------|-------------------|---------|
| 1 — `get_evaluated_at` gone, no `Depends()` supplies a `datetime` | absence | unit | `! grep -rn "get_evaluated_at" src/ tests/` | ❌ Wave 0 — new, and it is the whole of criterion 1 |
| 1 — e2e override gone | absence | unit | `! grep -n "dependency_overrides\[get_evaluated_at\]" tests/e2e/test_restore_subscription.py` | ❌ folded into the grep above |
| 2 — no service or crud takes the parameter | absence | unit | `! grep -rn "evaluated_at" src/nativespeaker/api/services src/nativespeaker/api/crud src/nativespeaker/api/routers src/nativespeaker/api/app` | ❌ Wave 0 |
| 2 — service constructor shape | shape | unit | `tests/unit/test_sync_resolver.py::…` line 432 (`set(vars(service))`) | ✅ **exists, must be edited** to `{"grants_db"}` |
| 3 — SQL comparison uses `now()` | behavior | schema | new case asserting the compiled predicate, or the e2e suites passing | ❌ Wave 0 — **gated on Open Question 1** |
| 3 — one clock read per crud writer | behavior | e2e | `tests/e2e/test_claim_anonymous_grant.py:107`, `test_claim_registered_grant.py:200` (`free_grant_consumed_at == starts_at`) | ✅ **exists and already proves it** — keep both, delete only the comment above them |
| 3 — the restore term boundary survives | behavior | unit | new case over `_open_term`, replacing `tests/e2e/test_restore_subscription.py:419` | ❌ Wave 0 — **must not be dropped silently** |
| 3 — the Play canceled-term boundary survives | behavior | unit | move `test_google_play_notifications.py:493-506` onto `_status_for` | ⚠️ exists, relocates |
| 3 — the quota rollover and retry-after boundaries survive | behavior | unit | `test_quota_resolver.py:287,299,423,459` rewritten against stored state / `seconds_until_rollover` | ⚠️ exists, rewrites |
| 4 — no comment names the dependency or the instant | absence | unit | `! grep -rniE "captured instant\|one instant\|get_evaluated_at\|evaluation time" src/ tests/` | ❌ Wave 0 |
| 4 — the clock-capture test is gone | absence | unit | `! test -f tests/unit/test_sync_clock_capture.py` | ❌ folded in |
| 5 — three suites green | regression | all | the four commands below | ✅ the suites exist |

### Sampling rate

- **Per task commit:** `.venv/bin/pytest -q` (1917, ~seconds, no database) — catches every signature
  break immediately.
- **Per wave merge:** `.venv/bin/pytest -q -m e2e` and `-m schema`. The e2e suite is where the `now()`
  hazard surfaces and it must run at **every** wave that touches `crud/grants.py`, not only at the end.
- **Phase gate:** all four commands plus `uv run ruff check src tests`, run in the closing plan rather
  than copied from an earlier summary — this project's own convention (see the Phase 45 and 46 records
  in `STATE.md`).

### Wave 0 gaps

- [ ] One absence-guard module (a handful of `grep`-equivalent cases over `src/` and `tests/`) covering
      criteria 1, 2 and 4 in one place. There is a precedent for this shape in the repo
      (`tests/unit/test_monthly_period.py::TestTheDerivationIsWrittenExactlyOnce` walks `SRC.rglob`).
      It needs its own **vacuity control**, as every such guard here does.
- [ ] A unit case over `_open_term` carrying `tests/e2e/test_restore_subscription.py:419`'s boundary.
- [ ] No framework install; no new dependency.

**Baseline to beat, measured this session:** 1917 unit / 362 e2e / 291 schema collected, e2e quota
41 passed, schema sync-lock-freedom 3 passed.

---

## Security Domain

This phase changes no authentication, authorization, input validation or cryptography. The admission
matrix, every status code and every response body are unchanged by construction.

| ASVS Category | Applies | Standard control |
|---------------|---------|------------------|
| V2 Authentication | no | Untouched — `get_identity` / `get_linked_identity` are not in scope |
| V3 Session Management | no | — |
| V4 Access Control | **yes, indirectly** | The effective-grant predicate **is** the entitlement gate. A predicate that admits a grant outside its term is an entitlement leak; a predicate that refuses one inside its term is a paid customer locked out. |
| V5 Input Validation | no | No request field changes |
| V6 Cryptography | no | — |

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| A widened effective-grant window grants unpaid access | Elevation of privilege | Keep `<=` / `>` exactly as written; the boundary cases in `tests/e2e/test_restore_subscription.py:419` and `tests/e2e/test_quota.py::TestThePredicateBoundaries` are the guard and must not be lost |
| Challenge expiry evaluated against a stale clock | Spoofing (replay of an expired challenge) | `ChallengesDB.claim`'s WHERE is the only expiry evaluation anywhere; if it moves to `now()`, `claimed_at` must move with it so the two cannot disagree |

Threat-model note from `AGENTS.md`: the product is a sub-$5/month grammar assistant; the value is not
great enough to make stealing it attractive. Normal measures, not paranoid ones.

---

## Open Questions (RESOLVED)

### 1. `now()` or `clock_timestamp()` — or neither? **BLOCKING. Needs the user.**

**Resolved 2026-09-11 by the user:** option (a), `clock_timestamp()` (D-01). Applied in plans 47-01 and 47-06.

**What we know (measured, not assumed):** criterion 3 says `now()`. `now()` in
`_effective_grants_statement` fails 11 e2e quota tests because the e2e harness holds one savepoint-
joined transaction open across each test. `clock_timestamp()` in the same place passes all 41, plus
sync and claim (25 more).

**What's unclear:** whether criterion 3's "`now()`" was written as *the literal function* or as *a
database-side clock*.

**The three options:**

| Option | Criterion 3 | e2e cost | Production semantics |
|--------|-------------|----------|----------------------|
| **(a) `func.clock_timestamp()`** | literal text not met; spirit met | **zero** — measured green | The true wall clock, re-evaluated per row. It is `VOLATILE`, so the planner cannot use it for an index scan on `starts_at`/`ends_at` — a real, if small, cost on a table that today has a handful of rows per user |
| **(b) `func.now()`** | met exactly | **high** — every e2e seed moves `starts_at` into the past, and the three write-then-read-back routes need a separate answer | One consistent snapshot per transaction, which is the closest thing left to `SHARED-INVARIANTS.md:44` |
| **(c) a bound Python parameter, read inside the crud method** | **not met** — the SQL compares against a parameter | zero | Identical to today's behavior; criteria 1, 2 and 4 are still fully met |

**Recommendation: (a) `clock_timestamp()`.** It is the only option that makes the SQL comparison
genuinely database-side, costs nothing in the test harness, and preserves production behavior exactly
(today's `evaluated_at` *is* a wall-clock read, not a transaction timestamp — so `clock_timestamp()`
is the faithful translation and `now()` is the behavior change). The index concern is real but the
grant table is tiny and the statement is already filtered by `user_id` and `status`. If the user
insists on the literal `now()`, the plan must budget a whole wave for the e2e harness.

**Do not let the planner decide this.** Put a blocking decision checkpoint in wave 1.

### 2. Does a crud writer read its own clock, or take one from its service?

**Resolved:** each crud writer reads its own clock once, at the top. Adopted in plans 47-03 and 47-05.

**What we know:** criterion 2 says "no crud method receives one from a service". Criterion 3 says
Python reads happen "at the point of use".
**What's unclear:** `RestoreService.restore` uses the instant four times *and* calls four crud
writers. If each writer reads its own, one restore request makes five clock reads, and `starts_at`
(service) can land microseconds before `ends_at` on a superseded grant (crud) — a sub-millisecond
overlap window. It is harmless (the superseded grant's `status` is already `expired`, and
`_effective_grants_statement` filters on status first), but it is a behavior change.
**Recommendation:** each crud writer reads its own clock, once at the top. Note the overlap in the
plan so a reviewer does not rediscover it; do not build machinery to prevent it.

### 3. `tables/grants.py:66` — keep or delete?

**Resolved:** keep it, cut to `# The timestamps carry no default.` Adopted in plan 47-07.

`# The timestamps carry no default. The creating transaction owns the clock.` The first sentence is
a fact about the model that remains true and prevents a real misreading (a reader who adds
`default_factory=` would break the two e2e equality assertions). The second names the shared instant.
**Recommendation:** keep the comment, cut it to `# The timestamps carry no default.` — one line,
stating the fact, naming nothing this phase removes.

### 4. Should the phase also drop `ChallengesDB`'s `now` parameter?

**Resolved:** yes. Adopted in plan 47-06.

`crud/challenges.py` is **not** in the roadmap's "Touches" list, but `ChallengesDB.issue/claim/consume`
each take `now: datetime` and each receives the shared instant from a router or `AuthService`.
Criterion 2's wording — "no crud method receives one from a service" — covers it.
**Recommendation:** yes, include it. Leaving it is leaving the phase half-done under a different
parameter name. Note the file overlap with Phase 49 (which changes only how the class is *built*).

### 5. Which phase updates `tests/unit/test_auth_package_shape.py`?

**Resolved:** the helpers live in `services/restore.py`; the ratchet is untouched. Adopted in plans 47-04 and 47-05.

`CURRENT = (8, 24, 67)`. Phase 47 changes it only if a function is added to `auth/`; Phase 49 rewrites
it at the end regardless. **Recommendation:** put `_open_term` in `services/restore.py`, not `auth/`,
so Phase 47 never touches the ratchet.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | A `VOLATILE` `clock_timestamp()` in a WHERE clause prevents an index scan on `starts_at`/`ends_at` | Open Question 1 | Low — the argument for (a) does not rest on it, and the table is small. Settle with `EXPLAIN` if the user cares. |
| A2 | 47 running before 49 is the smoother order | Finding 8 | Low — they are declared independent; either order works, the second one re-measures the shape tuple |
| A3 | The rewritten schema-suite assertions will not flake under the `before <= v <= after` bracket | Finding 6 | Low-medium — mitigate with `@pytest.mark.timing`, which the project already uses for exactly this |
| A4 (resolved 2026-09-11 by the user: strike the invariant — D-02, plan 47-02) | The Phase 38 criterion-1 conflict should be *recorded* rather than resolved by editing `SHARED-INVARIANTS.md` | Finding 7 | Medium — `ROADMAP.md:98` says flag, but Phase 38 plan 38-04 set a precedent for striking an invariant under a checkpoint. **User decision.** |

---

## Sources

### Primary (HIGH confidence — read or measured in this session)

- `src/nativespeaker/api/{app/dependencies.py, routers/auth.py, services/*.py, crud/*.py, auth/{app_store,google_play}.py, tables/grants.py}` — read in full or in the cited ranges
- `tests/{unit,e2e,schema}/` — exhaustive grep for `evaluated_at`, `get_evaluated_at`, `datetime.now`, `freezegun`, `dependency_overrides`; the cited files read directly
- Live PostgreSQL 17.11 probe: `now()` / `transaction_timestamp()` / `statement_timestamp()` / `clock_timestamp()` / `CURRENT_TIMESTAMP` semantics, and the savepoint-visibility probe
- Falsification run: `func.now()` → 11 failed / 30 passed; `func.clock_timestamp()` → 41 passed, 25 passed; baseline restored → 41 passed
- Baseline collection counts: 2570 / 1917 / 362 / 291
- `.planning/{ROADMAP.md, REQUIREMENTS.md, STATE.md}`, `AGENTS.md`, `pyproject.toml`, `migrations/20260818_01_initial-release.sql`
- `/home/init/native-speaker/specs/auth-refactor-phases/SHARED-INVARIANTS.md:39-44`

### Secondary / Tertiary

None. No web search was performed and no external documentation was consulted — every claim above is
grounded in this repository or in a measurement against its own database.

---

## Metadata

**Confidence breakdown:**

- Occurrence inventory and call chains: **HIGH** — exhaustive grep plus direct reads, file:line cited
- The `now()` finding: **HIGH** — measured twice (a direct SQL probe and a patched-source suite run), with the counter-case (`clock_timestamp()`) also measured
- Test disposition: **HIGH** for the files read directly; **MEDIUM** for the per-assertion rewrite cost in the two large schema files, which was sampled rather than read line by line
- The flagged conflict: **HIGH** — the invariant, the requirement and the milestone rule are quoted verbatim
- Phase 48/49/50 boundaries: **HIGH** — read from the roadmap entries

**No package legitimacy audit:** this phase installs nothing. `grep` for `freezegun` / `time_machine`
confirms no new dependency is needed and the recommendation is explicitly not to add one.

**Research date:** 2026-09-11
**Valid until:** stable — the findings are about this repository's own source and its own database.
Re-measure the falsification run if `tests/e2e/conftest.py`'s transaction arrangement changes.
