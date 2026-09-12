# Phase 47: Stop threading an evaluation instant through the layers - Pattern Map

**Mapped:** 2026-09-11
**Files analyzed:** 15 source files modified, 2 pure helpers added (both inside an existing module), 1 test file deleted, 2 test modules added, 27 test files edited
**Analogs found:** 17 / 19 (the two gaps are listed in § No Analog Found)

This phase creates no new module. It removes one parameter from existing dependencies, handlers,
services, crud classes and adapters. Every pattern below is therefore a **target shape already
written somewhere in this repository** — not a new convention.

---

## File Classification

### Source

| Modified file | Role | Data flow | Closest analog | Match quality |
|---------------|------|-----------|----------------|---------------|
| `src/nativespeaker/api/app/dependencies.py` | dependency | request-response | `get_quota_service` in the same file, lines 94-96 | exact |
| `src/nativespeaker/api/routers/auth.py` | handler | request-response | `create_user` in the same file, lines 84-90 | exact |
| `src/nativespeaker/api/services/chats.py` | service | request-response | `ChatService.__init__` minus one field; no analog needed — a pure deletion | exact |
| `src/nativespeaker/api/services/quota.py` | service | CRUD | `tests/e2e/conftest.py::seed_grant` lines 646-655 (one read, then every use) | role-match |
| `src/nativespeaker/api/services/sync.py` | service | request-response | same as above | role-match |
| `src/nativespeaker/api/services/auth.py` | service | CRUD | same as above; the field is deleted outright, nothing replaces it | exact |
| `src/nativespeaker/api/services/restore.py` | service | CRUD | same as above, plus `auth/store_notifications.py::term_end_for` lines 56-61 for the new helper | role-match |
| `src/nativespeaker/api/services/subscriptions.py` | service | event-driven | same as `services/quota.py` | role-match |
| `src/nativespeaker/api/crud/grants.py` | crud | CRUD | `tests/e2e/conftest.py::seed_grant` lines 646-655 | role-match |
| `src/nativespeaker/api/crud/identities.py` | crud | CRUD | same | role-match |
| `src/nativespeaker/api/crud/subscriptions.py` | crud | CRUD | same | role-match |
| `src/nativespeaker/api/crud/challenges.py` | crud | CRUD | same | role-match |
| `src/nativespeaker/api/auth/app_store.py` | adapter | transform | `_ms_to_datetime` / `_transaction_status` in the same file, lines 26-44 | exact |
| `src/nativespeaker/api/auth/google_play.py` | adapter | request-response | `_status_for` in the same file, lines 197-205 | exact |
| `src/nativespeaker/api/tables/grants.py` | table | — | comment edit only; `tables/users.py:23-24` shows the default the comment warns against | exact |

### Added — both inside `services/restore.py`, so no new module and no new package

| New entity | Role | Data flow | Closest analog | Match quality |
|------------|------|-----------|----------------|---------------|
| `_open_term(candidates, instant)` | utility (pure helper) | transform | `auth/store_notifications.py::term_end_for` lines 56-61 | exact |
| `_this_month(instant)` (existing method, re-shaped to take the instant) | utility (pure helper) | transform | `tables/grants.py::monthly_period_for` lines 31-33 | exact |

### Tests

| Test file | Role | Data flow | Closest analog | Match quality |
|-----------|------|-----------|----------------|---------------|
| **new** absence guard (criteria 1, 2, 4) | test | transform | `tests/unit/test_monthly_period.py::TestTheDerivationIsWrittenExactlyOnce` lines 39-65 | exact |
| **new** `_open_term` boundary cases | test | transform | `tests/unit/test_quota_resolver.py::TestTheRolloverIsDerivedFromTheCapturedInstant` lines 464-493 | exact |
| `tests/unit/test_sync_clock_capture.py` | test | — | **deleted**; its vacuity-control shape (lines 122-163) is carried into the new absence guard | exact |
| `tests/unit/test_quota_resolver.py` | test | CRUD | `test_a_matching_period_is_not_rewritten_and_the_count_carries_forward` lines 274-277, in the same file | exact |
| `tests/unit/test_sync_resolver.py` | test | request-response | `tests/unit/test_quota_resolver.py` lines 274-277 | exact |
| `tests/unit/test_google_play_notifications.py` | test | request-response | `TestTheRolloverIsDerivedFromTheCapturedInstant` lines 467-474 (parametrize a pure helper) | exact |
| `tests/unit/test_restore_proof.py` | test | transform | same | exact |
| `tests/unit/conftest.py` | test (fixture) | request-response | the real `QuotaService.charge` signature, `services/quota.py:41` | exact |
| `tests/e2e/conftest.py` | test (scripted seam) | request-response | `_ScriptedAppStore.verify` in the same file, lines 362-367 | exact |
| `tests/e2e/test_restore_subscription.py` | test | request-response | `test_an_open_term_still_attaches_the_grant_control` lines 441-445 (no pinned instant) | exact |
| `tests/schema/test_grant_locks.py` | test | CRUD | `tests/schema/helpers.py::insert_grant` lines 39-60, and the raw seed at lines 690-698 of the same file | exact |
| `tests/schema/test_subscription_ingestion.py` | test | event-driven | **partial** — see § No Analog Found | partial |
| the twelve remaining test files (argument removals only, Finding 6) | test | — | mechanical; the call site loses one keyword | exact |

---

## Pattern Assignments

### Cluster 1 — `app/dependencies.py`: a service factory with no clock

**Analog:** `src/nativespeaker/api/app/dependencies.py:94-96` — the one service factory in the file
that already declares no instant.

```python
def get_quota_service(session_factory: async_sessionmaker = Depends(get_session_factory)) -> QuotaService:
    # The factory, not `get_db`: the charge commits in its own session while the request session stays open.
    return QuotaService(session_factory=session_factory)
```

`get_sync_service` (lines 148-150) becomes exactly this shape with `db` in place of the factory.
`get_chat_service` (105-116), `get_auth_service` (136-145), `get_subscriptions_service` (153-156)
and `get_restore_service` (160-167) each lose one parameter line and one constructor argument line.

`get_evaluated_at` (lines 99-101) goes with its docstring. The `datetime` import on line 2 goes
only if no other annotation in the file needs it — `verify_google_play_notification` keeps
`signed_at`, so check before deleting.

**Do not touch** (Phase 50 owns them): `get_session_factory`, `get_firebase_adapter`,
`get_devicecheck_adapter`, every `request.app.state.*` read and every `Request` parameter.
**Do not touch** (Phase 49 owns it): `get_challenge_store`.

---

### Cluster 2 — `routers/auth.py`: a handler that declares only `Depends()`

**Analog:** `src/nativespeaker/api/routers/auth.py:84-90` — the sibling handler on the same router
that takes no instant.

```python
async def create_user(body: CompletionRequest,
                      identity: AuthIdentity = Depends(get_identity),
                      service: AuthService = Depends(get_auth_service)) -> CompletionResponse:
    """Complete the operation the body's handle stands for."""
```

`issue_challenge` (lines 52-76) drops `evaluated_at: datetime = Depends(get_evaluated_at)` from its
signature and `now=evaluated_at` from the `challenge_store.issue(...)` call at line 71. Then remove
`get_evaluated_at` from the import block (line 15) and `from datetime import datetime` (line 4) if
no annotation is left that needs it.

**Do not touch:** any `AuthIdentity` annotation (Phase 48), and the
`challenge_store: ChallengesDB = Depends(get_challenge_store)` parameter (Phase 49).

---

### Cluster 3 — one clock read at the top of a writer, every column stamped from it

This is the phase's central pattern and it applies to nine crud methods and four service methods.

**Analog:** `tests/e2e/conftest.py:646-655` — `seed_grant`. It is the one place in the repository
that already reads the clock once and stamps a whole row family from that single value.

```python
    now = datetime.now(UTC)
    async with factory() as session:
        grant = AccessGrant(user_id=user_id,
                            tier_id=tier_id,
                            source=source,
                            status=status,
                            starts_at=now if starts_at is None else starts_at,
                            ends_at=ends_at,
                            created_at=now,
                            updated_at=now)
```

**Import convention for `src/`:** `from datetime import UTC, datetime`, then `datetime.now(UTC)`.
Already written that way in `src/nativespeaker/api/auth/devicecheck.py:78` and in
`src/nativespeaker/api/app/dependencies.py:101`. `services/quota.py:5` and `tables/grants.py:2`
already import both names.

**The target shape for `crud/grants.py:161-222` (`activate_anonymous_device_grant`)** — nine uses
today, one read tomorrow. The body from line 196 is what must keep reading one name:

```python
        activated = AccessGrant(user_id=user_id,
                                tier_id=tier_id,
                                source=AccessGrantSource.anonymous_device_grant,
                                starts_at=evaluated_at,
                                created_at=evaluated_at,
                                updated_at=evaluated_at)
        self.session.add(activated)
        self.session.add(UserMonthlyUsage(grant_id=activated.id,
                                          monthly_period=monthly_period_for(evaluated_at),
                                          monthly_used=0,
                                          created_at=evaluated_at,
                                          updated_at=evaluated_at))
        stored.free_grant_consumed_at = evaluated_at
```

Rename `evaluated_at` to `instant`, read it once at the top of the method, and every one of those
assignments still carries the same value. **A read per assignment breaks two e2e equality
assertions** — `tests/e2e/test_claim_anonymous_grant.py:107` and
`tests/e2e/test_claim_registered_grant.py:200` both assert
`identity.free_grant_consumed_at == grant.starts_at`.

**Same pattern, same treatment, per method:**

| File | Method | Uses today |
|------|--------|-----------|
| `crud/grants.py:161` | `activate_anonymous_device_grant` | 9 |
| `crud/grants.py:224` | `activate_registered_account_grant` | 10 |
| `crud/subscriptions.py:148` | `insert_subscription` | 2 |
| `crud/subscriptions.py:169` | `upsert_subscription` | 6 |
| `crud/subscriptions.py:230` | `claim_subscription_owner` | 1 |
| `crud/subscriptions.py:247` | `hold_subscription_clock` | 1 (keeps `clock_read`, which is a caller's read and not a clock) |
| `crud/subscriptions.py:256` | `insert_purchase` | 1 |
| `crud/subscriptions.py:284` | `append_event` | 1 |
| `crud/subscriptions.py:313` | `write_subscription_grant` | 6 |
| `crud/identities.py:90` | `insert_account` | 6 |
| `crud/identities.py:127` | `flip_provider` | 4 |
| `crud/challenges.py:32` | `issue` | 2 (`expires_at` base and `created_at`) |
| `services/quota.py:41` | `charge` | 4 |
| `services/sync.py:24` | `read_entitlement` | 2 |
| `services/restore.py:49` | `restore` | 4, plus the two adapter calls |
| `services/subscriptions.py:31` | `ingest` | 3 |

**Naming:** the research and the roadmap both call the value *the instant*. `instant` is already the
local name in `services/quota.py:28` (`instant = evaluated_at.astimezone(UTC)`) and in
`tests/schema/test_grant_locks.py:696`. Use it. Do not coin a new noun.

**Constructor fields deleted outright, nothing replacing them:** `ChatService.evaluated_at`
(`services/chats.py:36,45`), `SyncService.evaluated_at` (`services/sync.py:19,22`),
`AuthService.evaluated_at` (`services/auth.py:68,78`),
`SubscriptionsService.evaluated_at` (`services/subscriptions.py:24,29`),
`RestoreService.evaluated_at` (`services/restore.py:36,47`). `ChatService` then holds no time at
all: its only two uses are the `charge` calls at `services/chats.py:99` and `131`.

---

### Cluster 4 — the two pure helpers

**Analog for `_open_term`:** `src/nativespeaker/api/auth/store_notifications.py:56-61` — a
module-level pure function in the same domain, over the same value types, with a two-line docstring.

```python
def term_end_for(status: SubscriptionStatus,
                 term: VerifiedNotification | RestoredSubscription) -> datetime | None:
    """The end of the term this status is in, in one spelling both write paths read.
    During grace that is the store's grace window, because the paid term has lapsed."""
    return (term.grace_period_expires_at if status is SubscriptionStatus.grace_period
            else term.expires_at)
```

The expression to lift out is `services/restore.py:100-101`:

```python
        term_ends_at = next((end for end in (*recorded_term, term_end_for(status, proof))
                             if end is not None and end > self.evaluated_at), None)
```

Put `_open_term` in `services/restore.py`, **not in `auth/`** — `tests/unit/test_auth_package_shape.py:13`
carries `CURRENT = (8, 24, 67)` and a new function under `auth/` fails that ratchet, which Phase 49
also rewrites.

**Analog for the re-shaped `_this_month`:** `src/nativespeaker/api/tables/grants.py:31-33` — the
repository's model for a pure helper that takes the datetime it derives from.

```python
def monthly_period_for(evaluated_at: datetime) -> str:
    """The UTC calendar month `UserMonthlyUsage.monthly_period` stores, in `YYYY-MM`."""
    return evaluated_at.astimezone(UTC).strftime("%Y-%m")  # `strftime` reports the stored wall clock.
```

`services/restore.py:173-176` already has this shape except that it reads `self`:

```python
    def _this_month(self) -> date:
        """The first day of the captured instant's UTC month, as the `DATE` column stores it."""
        # Real dates on both sides of the comparison; `monthly_period`'s `YYYY-MM` string is another thing.
        return self.evaluated_at.astimezone(UTC).date().replace(day=1)
```

Change the signature to `_this_month(self, instant: datetime) -> date` and pass the instant that
`restore()` read at its top, at both call sites (lines 82 and 128). Reword the docstring — it names
the captured instant, which criterion 4 forbids.

**Three helpers keep their parameter unchanged and must not be touched:**
`tables/grants.py:31` `monthly_period_for`, `services/quota.py:26` `seconds_until_rollover`,
`auth/app_store.py:36` `_transaction_status` and `auth/google_play.py:197` `_status_for`.

---

### Cluster 5 — the two adapters

**Analog:** `src/nativespeaker/api/auth/app_store.py:36-44` — the pure judgement the adapter already
isolates, which keeps its parameter.

```python
def _transaction_status(transaction: JWSTransactionDecodedPayload,
                        evaluated_at: datetime) -> SubscriptionStatus:
    """The status one signed transaction reports, with no renewal payload to consult."""
    if transaction.revocationDate is not None:
        return SubscriptionStatus.revoked
    expires_at = _ms_to_datetime(transaction.expiresDate)
    # Grace and billing retry need the renewal payload, so an Apple restore reports three words only.
    return (SubscriptionStatus.active if expires_at is not None and expires_at > evaluated_at
            else SubscriptionStatus.expired)
```

`verify_transaction` (`auth/app_store.py:119-120`) drops its `evaluated_at` parameter, reads
`datetime.now(UTC)` once, and hands that value to `_transaction_status`. `read`
(`auth/google_play.py:273-275`) and `read_for_restore` (`auth/google_play.py:323-324`) do the same
and hand it to `_status_for` (line 316).

**Pitfall, from Finding 8:** `PlaySubscriptionSource` is a Protocol at `auth/google_play.py:124-136`
and it declares both methods with `evaluated_at`:

```python
class PlaySubscriptionSource(Protocol):
    """The Play read seam: one live subscription as this project's value type, or a raise."""

    async def read(self, *, package_name: str, purchase_token: str, event_type: str,
                   notification_uuid: str, signed_at: datetime | None,
                   evaluated_at: datetime) -> VerifiedNotification | None:
```

Change **all four** signatures — the Protocol at 127-129 and 133-134, and the concrete class at
273-275 and 323-324 — in one commit. Phase 49 deletes the Protocol; if Phase 49 lands first, edit
only the concrete class.

`dependencies.py:211` then drops `evaluated_at=evaluated_at` from the `play_subscriptions.read(...)`
call, and `services/restore.py:198,203` drop it from both `_verify` branches.

---

### Cluster 6 — `tables/grants.py`: the comment that stays, cut

**Analog:** `src/nativespeaker/api/tables/users.py:23-24` — the default this comment exists to warn a
reader against adding.

```python
    created_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(sa_type=DateTimeType, default_factory=lambda: datetime.now(UTC))
```

`tables/grants.py:66` reads `# The timestamps carry no default. The creating transaction owns the
clock.` The first sentence stays true and prevents a real misreading; the second names the shared
instant. Cut it to one sentence. Change nothing else in the file — a `default_factory` on
`AccessGrant.starts_at` would break the two e2e equality assertions named in Cluster 3.

---

### Cluster 7 — the test that controls stored state instead of the clock

**Analog:** `tests/unit/test_quota_resolver.py:274-277`, in the same file as the four cases that must
be rewritten. It already proves a rollover branch without touching a clock — the stub's stored
period is the whole input.

```python
    async def test_a_matching_period_is_not_rewritten_and_the_count_carries_forward(self):
        grant, usage = _one_effective_grant(monthly_period=PERIOD, monthly_used=7)
        await _consume(grants=(grant,), usage=usage)
        assert (usage.monthly_period, usage.monthly_used) == (PERIOD, 8)
```

The two helpers it stands on, in the same file at lines 101-104 and 119-122:

```python
def _usage(grant: AccessGrant, *, monthly_period=..., monthly_used=0) -> UserMonthlyUsage:
    return UserMonthlyUsage(grant_id=grant.id,
                            monthly_period=PERIOD if monthly_period is ... else monthly_period,
                            monthly_used=monthly_used)


def _one_effective_grant(**usage_kwargs):
    """The ordinary case: one grant and its usage row, varied only by `usage_kwargs`."""
    grant = _grant()
    return grant, _usage(grant, **usage_kwargs)
```

**Apply to:** `tests/unit/test_quota_resolver.py:287,299` (both pass a past instant to reach the
rollover branch — set `monthly_period` to a past month instead, because the branch is
`usage.monthly_period < monthly_period_for(instant)`), `:423` (same shape, forward), and
`tests/unit/test_sync_resolver.py:323` (`_read(session, evaluated_at=...)` → a stored period).

`tests/unit/test_quota_resolver.py:459` (`near_the_boundary`) is a different case: it tests
`seconds_until_rollover`, which keeps its parameter. Call the helper directly, as
`TestTheRolloverIsDerivedFromTheCapturedInstant` already does in the same file.

`tests/unit/test_sync_resolver.py:431-432` changes value only:

```python
        service = SyncService(db=_StubSession(grants=()), evaluated_at=EVALUATED_AT)
        assert set(vars(service)) == {"grants_db", "evaluated_at"}
```

becomes `SyncService(db=...)` and `== {"grants_db"}`.

---

### Cluster 8 — the new unit cases over a pure helper

**Analog:** `tests/unit/test_quota_resolver.py:464-493` — the repository's model for pinning a
boundary on a helper that takes its datetime. Parametrized cases, then a control, then a mirror.

```python
class TestTheRolloverIsDerivedFromTheCapturedInstant:
    """The header's value, computed off the same instant the period is, and never off a clock."""

    @pytest.mark.parametrize(("instant", "expected"), [
        (datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC), 1),
        (datetime(2026, 12, 31, 23, 0, tzinfo=UTC), 3600),
        (datetime(2026, 2, 1, tzinfo=UTC), 28 * 86400),
        (datetime(2026, 1, 1, tzinfo=UTC), 31 * 86400),
    ], ids=["month-end", "year-end", "short-month", "long-month"])
    def test_it_counts_to_the_next_utc_month_boundary(self, instant, expected):
        assert seconds_until_rollover(instant) == expected

    def test_the_boundary_instant_itself_never_says_zero(self):
        """A `Retry-After: 0` invites the immediate retry the refusal exists to stop."""
        assert seconds_until_rollover(datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=UTC)) == 1
```

**Apply to three relocated boundary cases:**

1. **`_open_term`** — carries `tests/e2e/test_restore_subscription.py:420-439`. That case is the only
   proof that `services/restore.py:101` is `>` and not `>=`. Its own words, lines 423-425: *"the
   predicate is `<=`, so a term ending exactly when the request was evaluated is over. Only a pinned
   instant names that equality, because a live clock never lands on it."* The e2e route loses the
   pinned instant, so the equality moves onto the helper. Do not drop it.
2. **`_status_for`** — carries `tests/unit/test_google_play_notifications.py:493-508`, which is
   already parametrized over two instants and only needs to call the helper instead of `reader.read`.
3. **`_transaction_status`** — carries the equivalent Apple boundary in
   `tests/unit/test_restore_proof.py`, whose `_dated(offset)` helper at line 114 already builds a
   transaction around `EVALUATED_AT`.

**Delete rather than relocate:** `tests/unit/test_google_play_notifications.py:517-523`
(`test_the_dependency_forwards_the_solver_resolved_instant_to_the_read`) and the two
`restore_calls` tuple assertions at `tests/e2e/test_restore_subscription.py:243` and `:755`. All
three exist only to prove the threading this phase removes.

---

### Cluster 9 — the new absence guard (criteria 1, 2 and 4 in one module)

**Analog:** `tests/unit/test_monthly_period.py:39-65` — a source walk with three controls, which is
the repository's own precedent for exactly this shape.

```python
class TestTheDerivationIsWrittenExactlyOnce:
    """Five copies is what let two of them each claim to be the only one; the claim is now checkable."""

    def _files_formatting_a_period(self) -> list[Path]:
        return sorted(path for path in SRC.rglob("*.py")
                      if any(spelling in path.read_text() for spelling in SPELLINGS))

    def test_only_the_one_function_formats_a_period(self):
        assert self._files_formatting_a_period() == [DERIVATION]

    def test_the_walk_reads_the_whole_package_control(self):
        """The control: a walk that found no file at all would pass the case above on an empty list."""
        assert len(list(SRC.rglob("*.py"))) > 20
```

Its header, lines 7-11, is the path convention to copy:

```python
REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "nativespeaker"
```

**The vacuity control is mandatory.** The file being deleted,
`tests/unit/test_sync_clock_capture.py:122-163`, carries the fullest example of one in this
repository: a positive control that the walk finds what it should find, and a near-miss control that
it does not report what it should ignore.

```python
class TestTheClockWalkIsNotVacuous:
    """A guard that finds no clock call anywhere would pass for the wrong reason, so it must find some."""
```

Carry that shape into the new guard. The guard's own subject changes — it asserts that
`get_evaluated_at` and `evaluated_at` are **absent** from `src/nativespeaker/api/{services,crud,routers,app}`,
so a walk that reads no file would pass on an empty list.

The AST walkers `_clock_reads` (lines 32-47) and `_clock_aliases` (18-29) have no other caller and go
with the file. A plain text walk over `SRC.rglob("*.py")`, like `test_monthly_period.py`'s, is enough
for an absence guard and is cheaper than an AST walk.

---

### Cluster 10 — the schema suites: seed the row directly

**Analog:** `tests/schema/helpers.py:39-60` — the direct insert, already used by the schema suites.

```python
async def insert_grant(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    tier_id: str,
    source: str = "anonymous_device_grant",
    status: str = "active",
    subscription_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert one core.access_grants row; source and status bind as text against the enum columns."""
```

And the version with an explicit term, in the file that needs the rewrite —
`tests/schema/test_grant_locks.py:690-698`:

```python
            await setup.execute(
                "INSERT INTO core.access_grants "
                "(id, user_id, tier_id, source, status, starts_at, ends_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                grant_id, user_id, tier_id, row.source, row.status,
                instant - row.starts_before,
                None if row.ends_before is None else instant - row.ends_before)
            await insert_usage(setup, grant_id=grant_id)
```

**Apply to `tests/schema/test_grant_locks.py:707`** — `evaluated_at=instant - evaluated_before`
deliberately activates a grant in the past. With the parameter gone the crud writer always stamps
now, so that case must seed the row directly instead of going through `activate_*`. The fixture at
line 690 in the same file already does exactly that, three lines above.

`tests/schema/test_grant_locks.py:50-53` — `_lock_grants(user_id, evaluated_at=None)` — is a raw-SQL
helper that already falls back to `datetime.now(UTC)`. It is unaffected while the predicate stays a
bound parameter, and is rewritten only if Open Question 1 moves the predicate into SQL.

---

### Cluster 11 — the scripted seams in the test conftests

**Analog:** `tests/e2e/conftest.py:362-367` — the sibling method on the same fake class, which
records only the argument the case is about.

```python
    def verify(self, signed_payload: str) -> VerifiedNotification:
        self.calls.append(signed_payload)
        if isinstance(self.answer, BaseException):
            raise self.answer
        assert self.answer is not None, "the seam was called before a case scripted it"
        return self.answer
```

Its neighbour four lines below, at `tests/e2e/conftest.py:369-375`, is what must shrink to that
shape — `verify_transaction` records a `(signed_transaction, evaluated_at)` tuple that loses its
second member. The same edit applies to `read_for_restore` (496-504) and `read` (507-516), whose
recorded call dicts lose the `"evaluated_at"` key.

Same edit, same pattern: `tests/unit/test_restore_proof.py:529` and `:544` define fake seams whose
signatures must track the real ones.

`tests/unit/conftest.py:149` monkeypatches `QuotaService.charge`, so its signature must mirror
`services/quota.py:41` exactly:

```python
    async def recording_charge(self, *, user_id: UUID, evaluated_at: datetime) -> None:
        calls.append(user_id)
```

becomes `async def recording_charge(self, *, user_id: UUID) -> None`. The `ChatService` fixture at
`tests/unit/conftest.py:168-175` loses `evaluated_at=EVALUATED_AT`; the module constant at line 141
goes if nothing else reads it.

---

### Cluster 12 — the flagged-conflict record

**Analog:** `.planning/REQUIREMENTS.md:229-231` — the amendment Phase 38 wrote under SYNC-03. A dated
blockquote **indented under the requirement bullet**, naming the phase, the decision id and the date,
stating what the requirement used to say and what it says now, and stating explicitly that nothing is
withdrawn or unchecked.

```markdown
- [x] **SYNC-03**: Every `/auth/sync` attempt earns exactly one `request` line …
  > **Amended by Phase 38 (D-01/D-02), 2026-09-01 — the decision Phase 37.1 flagged forward is made here.** As written this requirement read *"…"*, and it carried a lead declaring itself blocked on a deleted mechanism plus a choice between two options. Both are gone because the choice has been made. The treatment is **amended**, not **withdrawn**: …
```

**Apply to SYNC-01 at `.planning/REQUIREMENTS.md:226**, whose text is *"…all derived from one
captured evaluation time"* — the exact property this phase deletes. Update the milestone row at
`.planning/REQUIREMENTS.md:754` (`SYNC-01 … SYNC-03 | Phase 38 | …`) and the flagged-conflict count
in the same table.

**Do not edit `SHARED-INVARIANTS.md`.** `ROADMAP.md:98` says flag, never resolve silently. Phase 38
plan 38-04 did strike an invariant, but under a blocking decision checkpoint flagged as a one-way
door — so striking `SHARED-INVARIANTS.md:44` must be its own checkpointed task if the planner
prefers it.

---

## Shared Patterns

### Reading the clock in `src/`

**Source:** `src/nativespeaker/api/auth/devicecheck.py:78` and `src/nativespeaker/api/app/dependencies.py:101`
**Apply to:** every crud writer method, every service method and both adapters

```python
from datetime import UTC, datetime
...
    return datetime.now(UTC)
```

One read per **method**, never per assignment. The value's local name is `instant`.

### Comments and docstrings

**Source:** `AGENTS.md:8-22`
**Apply to:** every file this phase touches

Docstrings are three lines maximum and state what the entity does. Comments are one line, sit above
the line or lines they explain, and never explain the design, the request lifecycle or a rule
enforced elsewhere. Criterion 4 makes deleting the 23 comments and docstrings in Finding 5
mandatory, not optional.

**One comment must stay:** `src/nativespeaker/api/crud/grants.py:49-51`.

```python
    # No time window: a partial index predicate must be IMMUTABLE, so `now()` cannot appear in
    # `ix_access_grants_one_active_per_user`, and its question is therefore asked on the mark alone.
```

Its subject is the index, not the shared instant, and it explains exactly the misreading criterion 3
invites.

### Marking a wall-clock-dependent assertion

**Source:** `pyproject.toml:75` and `tests/unit/test_devicecheck_adapter.py:332-344`
**Apply to:** any rewritten assertion that could flake under load

```python
@pytest.mark.timing
class TestTheAttemptsAreSeparatedInTime:
    """WR-21: the budget was spent inside a few milliseconds, so it bought nothing against a blip."""

    FLOOR_SECONDS = 0.25  # A literal, not derived from the base, so a shrunk base still fails here.
```

Five tests already carry this marker. The `pyproject.toml` addopts do **not** deselect it, so a
marked test still runs in the ordinary suite; the marker exists so a flake can be reported
separately with `-m timing`.

### Do not introduce a time-freezing library

**Source:** Finding 6 — `grep -rn "freezegun\|freeze_time\|time_machine" src/ tests/` returns zero
hits, and there is no monkeypatch of `datetime.now` anywhere.
**Apply to:** every rewritten test

A `Clock` protocol, an injectable time source or a test-only `FakeClock` **is** `get_evaluated_at`
under another name and defeats the phase. Every case has a cheaper replacement: a pure helper that
takes the datetime, a bracketed assertion, or controlling the stored state.

### Running the suites

**Source:** `pyproject.toml:71-76`, measured in RESEARCH Finding "Environment Availability"

```bash
.venv/bin/pytest -q              # 1917 collected — the unit suite, no database needed
.venv/bin/pytest -q -m ''        # 2570 collected — EVERYTHING, database required
.venv/bin/pytest -q -m e2e       #  362 collected — database required
.venv/bin/pytest -q -m schema    #  291 collected — database required
```

`-m ''` is **not** the unit suite. Per-task gate is the bare `.venv/bin/pytest -q`. Every wave that
touches `crud/grants.py` must also run `-m e2e`, because that is where the effective-grant predicate
hazard surfaces.

---

## No Analog Found

| File / need | Role | Data flow | Reason |
|-------------|------|-----------|--------|
| `tests/schema/test_subscription_ingestion.py` — the bracketed `before <= value <= after` assertion | test | event-driven | **No `before <= v <= after` assertion exists anywhere in `tests/`** (exhaustive grep). Roughly a dozen assertions there are exact equality against `buyer.evaluated_at` — `held[0]["ends_at"] == buyer.evaluated_at` (363, 396, 416), `held[0]["starts_at"] == buyer.evaluated_at - _A_MONTH` (330), `usage["monthly_period"] == buyer.evaluated_at.strftime("%Y-%m")` (341). The closest shapes in the repo are the two `@pytest.mark.timing` brackets over `time.monotonic()`: `tests/unit/test_jwks_offload.py:150-154` (`started` / `finished` around the call) and `tests/unit/test_devicecheck_adapter.py:346-353`. Neither brackets a stored column. The planner should state the bracket shape explicitly in the plan rather than point at a file. **Note:** where the asserted value is a derived offset (`buyer.evaluated_at + _A_MONTH`) the term comes from the notification the test itself built, so those assertions stay exact — only the values the writer stamps need a bracket. |
| The SQL comparison against a database clock (criterion 3) | crud | CRUD | `grep -rn "func.now\|now()\|current_timestamp" src/` returns one hit and it is a comment. **Nothing in `src/` uses a database clock today, so there is no analog to copy.** RESEARCH Open Question 1 is blocking and needs the user: `func.now()` fails 11 of 41 e2e quota tests (measured), `func.clock_timestamp()` passes all 41 (measured). Do not let the planner choose. |

---

## Metadata

**Analog search scope:** `src/nativespeaker/api/{app,auth,crud,routers,services,tables}/`,
`tests/{unit,e2e,schema}/`, `.planning/REQUIREMENTS.md`, `AGENTS.md`, `pyproject.toml`
**Files read:** 24 (source and test), all confirmed git-tracked with `git ls-files`
**Pattern extraction date:** 2026-09-11
