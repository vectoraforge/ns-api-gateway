---
phase: 38-post-auth-sync
fixed_at: 2026-09-09T21:26:58Z
review_path: .planning/phases/38-post-auth-sync/38-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 27
fixed: 26
skipped: 1
iteration: 1
status: partial
---

# Phase 38: Code Review Fix Report

**Fixed:** 2026-09-09T21:26:58Z
**Fix scope:** critical_warning (Critical + Warning; `--all` was not passed, so the 41 Info findings are out of scope)
**Findings in scope:** 27 (1 Critical + 26 Warning)
**Fixed:** 26 · **Skipped:** 1

## Summary

The 27 Critical and Warning findings from `38-REVIEW.md` were applied by four
`gsd-code-fixer` agents run **strictly sequentially** — never in parallel, so no two fixers
ever shared a git index. Each finding got its own `fix(38): <finding-id> …` commit touching
only that finding's files: 26 commits, `62b99a3` through `48d3907`.

One finding was skipped: **WR-02**, because the fix it proposes is forbidden by a binding
clause (see below).

### Fix commits

| Commit | Finding | Change |
|---|---|---|
| `62b99a3` | CR-29 | refuse a superseded grant whose usage row is absent |
| `fb798a3` | WR-30 | drop the unused session handle from SyncService |
| `dc487fb` | WR-31 | normalize the instant before deriving the UTC month boundary |
| `8b98167` | WR-32 | cut the narrating comment blocks AGENTS.md outlawed |
| `14d1bd1` | WR-33 | refuse the absent usage row lock_grants_of discarded |
| `8e45d59` | WR-01 | cover every Play value the boot warning names |
| `951ba7c` | WR-03 | silence uvicorn's duplicate access log |
| `b7352a9` | WR-04 | let the DeviceCheck Secret be absent, as values.yaml documents |
| `c36fb57` | WR-05 | cut the comment register AGENTS.md outlawed |
| `b1ed20a` | WR-15 | stop labelling an absent claim as forgery |
| `66e433b` | WR-16 | drop the dormant second clock from the grant tables |
| `315a2ef` | WR-45 | cover the refused arm in the Google log-hygiene walk |
| `5792e2f` | WR-46 | read the seeded monthly_used off the sync wire |
| `f4cdf4b` | WR-47 | close the two silent narrowings in the refusal-arm control |
| `3f20c5c` | WR-48 | drop the tautological key queries from the unmapped-product case |
| `122347d` | WR-57 | mark the lock-order control timing and measure A's release |
| `9ca06ef` | WR-58 | issue production's own compiled SQL instead of a hand-written mirror |
| `e8760df` | WR-59 | assert the lock order on both registered grant-tier reads |
| `0918843` | WR-60 | exercise the pairing scan on the arm that can break it |
| `f8af386` | WR-61 | assert the reader's transaction spans the charge it races |
| `41b8e62` | WR-69 | script a set opposite bit so the carry-forward is observable |
| `2ae3348` | WR-70 | test the ignored extra tokens instead of the missing required one |
| `106a56f` | WR-71 | drive the preauth-callable case off the literal, not the live routes |
| `9fdf4ec` | WR-83 | assert the bound key and instant of each sync read |
| `3a0dce4` | WR-84 | assert the owner predicate and its bound value on the token read |
| `48d3907` | WR-85 | drive the resolver over every grant source and pin the two enums |

### Skipped

**WR-02 — provider permit acquired with no timeout, after the quota credit has already
committed.** Adding a timeout makes a charged request refuse without ever reaching the
provider, which `AGENTS.md:89-91` forbids: a charged request always reaches the provider at
least once. `resilience.py:167-174` repeats the same clause. The finding's "unbounded" premise
was also disproved — `inflight_slot` caps waiters at `pool_size + queue_size` (30 as
configured), so the ceiling is finite and set by a config value. This needs a product decision
about charge-then-refund, not a patch.

### Review premises corrected rather than coded to

The fixers verified the review's claims before editing and found several wrong. Recorded here
because they matter for the next pass:

- `MissingUsageRowError` was **not** already imported in `crud/subscriptions.py` (CR-29), and
  `UTC` was **not** already imported in `services/quota.py` (WR-31). Both fixes add the import.
- WR-16 implied the DDL leaves the grant columns without a database default. Both
  `core.access_grants` and `core.access_tiers` carry `DEFAULT CURRENT_TIMESTAMP`; verified
  against the live database. The fix drops the application-side clock and relies on an explicit
  loud failure, not on the DDL default.
- WR-03's suggested `--no-access-log` Dockerfile change covers one launch path of three; the
  fix quiets `uvicorn.access` in `setup_logging` instead, which covers all three.
- WR-47's suggested package-wide walk cross-contaminates Apple and Google stages; the fix takes
  the finding's stated minimum instead.
- WR-61's suggested `assert reader.in_transaction()` does **not** catch the regression — a
  `commit()` is followed by reads that autobegin, so the flag is `True` again by assertion
  time. The fix asserts transaction *identity*, which does fail under the mutation.

### Left for a later pass (named by fixers, owned by no finding)

- `src/nativespeaker/api/services/auth.py` lines ~219-221, ~231-234, ~289-291, ~298-300 carry
  the same comment register WR-05 and WR-32 removed elsewhere; neither finding named them.
- `tables/identities.py`, `tables/users.py` and `tables/chats.py` carry the same wall-clock
  factories WR-16 removed from the grant tables.

### Test findings were proved load-bearing

Every test finding (WR-45 through WR-48, WR-57 through WR-61, WR-69 through WR-71, WR-83
through WR-85) was verified by mutation: the production code the test guards was broken from a
backup copy, the repaired test was confirmed to **fail**, then the source was restored and
`git status --short` confirmed clean. No assertion was deleted to get green. WR-48's one
deletion removed three assertions proved incapable of failing under any implementation; the
table counts that carry the claim were kept and do fail under mutation.

## Verification

Run by the orchestrator at `48d3907`, after every fix commit landed.

| Gate | Baseline (`6cd846e`) | After fixes | Verdict |
|---|---|---|---|
| `ruff check src tests` | clean | **clean** | pass |
| `pytest tests/unit` | 1620 passed | **1658 passed** | pass (+38 new cases) |
| `pytest tests/schema -m schema` | 248 passed | **249 passed** | pass (+1 new case) |
| `pytest tests/e2e -m e2e` | 352 passed | **354 passed** | pass (+2 new cases) |
| `ty check src` | 3 diagnostics | **3 diagnostics** | pass (not risen) |

No suite regressed and no test was weakened. The added cases are the load-bearing replacements
the test findings required.

---

## Per-fixer reports

### Fixer 1

# Phase 38: Code Review Fix Report (part 1 of 4)

**Assigned block:** CR-29, WR-30, WR-31, WR-32, WR-33.
Every fix is its own commit, containing that finding's source files only.

## Summary

| Finding | Status | Commit |
|---|---|---|
| CR-29 | fixed | `62b99a3` |
| WR-30 | fixed | `fb798a3` |
| WR-31 | fixed | `dc487fb` |
| WR-32 | fixed | `8b98167` |
| WR-33 | fixed | `14d1bd1` |

## Fixed Issues

### CR-29: `write_subscription_grant` read a missing usage row as "zero used"

**Commit:** `62b99a3`
**Files:** `src/nativespeaker/api/crud/subscriptions.py`, `tests/unit/test_subscription_grant_write.py`

The carry-over loop tested `usage is not None and usage.monthly_period == period` in one
condition, so an absent `core.user_monthly_usage` row fell through with `carried = 0` and the
insert below minted a full monthly allowance the account never bought.

Split the `None` arm out of the stale-period arm and raised `MissingUsageRowError(grant.id)` on
it, matching `activate_registered_account_grant` (`crud/grants.py:278`), `QuotaService.charge`
and `SyncService.read_entitlement`. The `usage.monthly_period == period` half is unchanged: a row
naming an earlier month legitimately carries zero. Added the
`from nativespeaker.api.errors import MissingUsageRowError` import — the review said it was
already present at `crud/subscriptions.py:13`; it was not, that line is the `violations` import.
The raise sits in `crud/` per AGENTS.md exception 4 ("a fail-closed read may raise its own
rejection").

Spec ground: `SHARED-INVARIANTS.md` § Grants and evaluation time — "A missing usage row for an
existing grant fails closed — never lazily minted."

**Tests updated (rule 8).** Five unit cases failed on the corrected behaviour:

- `test_a_superseded_grant_with_no_usage_row_starts_at_zero` asserted the defect itself, with the
  docstring "Absent, not fail-closed: this writer mints the row, so there is nothing to refuse."
  Rewritten as `test_a_superseded_grant_with_no_usage_row_fails_closed`, asserting
  `failure.value.grant_id == own.id`, plus a second case
  `test_the_refusal_inserts_no_grant_and_no_counter` pinning that nothing is added. No assertion
  was weakened; the expectation was inverted to the correct one.
- Four supersession cases in `TestTheDestinationLosesEverythingItHolds` constructed
  `_StubSession()` with no usage row while superseding a grant of the destination account. They
  assert supersession, not usage handling, so each now seeds the stub with a usage row for the
  grant it supersedes. `THIS_MONTH` / `LAST_MONTH` moved above the first test class so they are
  readable where they are now used.

### WR-30: `SyncService` held a live handle to the committing session

**Commit:** `fb798a3`
**Files:** `src/nativespeaker/api/services/sync.py`, `tests/unit/test_sync_resolver.py`

`self.session = db` was assigned and never read. Because `get_db` commits on teardown
(`app/dependencies.py:44-51`), it was a writable handle on the one service whose contract
(`03-sync.md` § 7 "Strictly read-only") is that it writes nothing. Deleted the assignment; the
constructor signature is unchanged, so `get_sync_service` is untouched.

Added `TestTheServiceKeepsNoSessionHandle`, asserting `set(vars(service)) == {"grants_db",
"evaluated_at"}`, so the read-only property is structural rather than argued only by a source
grep in plan 38-02's acceptance criteria.

### WR-31: `seconds_until_rollover` derived the UTC month boundary without normalizing

**Commit:** `dc487fb`
**Files:** `src/nativespeaker/api/services/quota.py`, `tests/unit/test_quota_resolver.py`

`evaluated_at.replace(...)` reads the stored wall clock of whatever `tzinfo` it is handed, while
its sibling `monthly_period_for` (`tables/grants.py:34`) calls `.astimezone(UTC)` first. Both are
computed from the same argument in the same `charge` call, so they must name one boundary.
Normalized once, the way the sibling does.

The review said "`UTC` is already imported at `quota.py:5`" — it was not; line 5 is
`from datetime import datetime`. Added `UTC` to that import.

**Guard proved by mutation.** Two new cases in `TestTheRolloverIsDerivedFromTheCapturedInstant`:
one pins that `2026-08-31T20:00-05:00` (which is `2026-09-01T01:00Z`) reports October's boundary
and `monthly_period_for` "2026-09"; the other walks offsets `-12` through `+14` around a month
boundary and asserts the two derivations agree. Reverse-applying the source hunk
(`instant = evaluated_at.astimezone(UTC)` → `instant = evaluated_at`) fails both and only those
two, so the guard is real and not vacuous.

### WR-32: comment blocks broken at scale in crud/routers/services

**Commit:** `8b98167`
**Files:** `services/restore.py`, `services/quota.py`, `services/auth.py`, `services/chats.py`,
`crud/subscriptions.py`, `crud/grants.py`, `crud/identities.py`

`AGENTS.md` § "Comments and docstrings" binds all code in the repository: "**One line each.** A
comment explains the specific line or lines below it. It never explains the design, the request
lifecycle, a rule enforced in another module, or a decision that was made elsewhere." Each cited
block was cut to the one line that resolves the ambiguity at the line below it:

| File | Was | Now |
|---|---|---|
| `services/restore.py:105-115` | 11 lines narrating `verify_transaction`, Apple's grace payload and `10-restore-subscription.md:90` | 1 line: at most one row answers |
| `crud/subscriptions.py:375-381` | 7 lines re-telling a prior finding | 1 line: the allowance is a calendar month's |
| `services/quota.py:75-82` | 8 lines re-telling a prior finding | 1 line: why `<` and not `!=` |
| `crud/grants.py:178-184` | 5 lines | 1 line: why `marked_active` is in the condition |
| `services/auth.py:224-229` | 6 lines on `ix_access_grants_one_active_per_user` | 1 line: why `wrote` guards the bit |
| `services/auth.py:293-296` | 4 lines | 1 line: why both conditions |
| `services/chats.py:145-149` | 5 lines | 1 line: why the log precedes the re-raise |
| `crud/identities.py:88-90` | 3 lines | 1 line: why the parameter is not nullable |
| `crud/identities.py:134-135` | 2 lines citing "02 step 12" | 1 line: which uniqueness this can lose |

51 comment lines deleted, 9 added. No behaviour changed and no test needed updating.

Three of the replacement lines first tripped ruff `E501` (the limit is `pyproject.toml:72`,
`line-length = 120`) and were shortened before the commit.

Two deliberate limits, so this is not a silent partial:

- Only the blocks the finding lists were cut. `services/auth.py:219-221`, `:231-234`, `:289-291`
  and `:298-300` carry the same register but are not named by WR-32; the adjacent
  `AGENTS.md:17-22` finding (WR-05, another fixer's) covers the infra files, and inventing scope
  here would collide with it.
- No repo-wide comment-length ratchet was added. `tests/unit/test_docstring_bar.py` already
  ratchets docstrings and records `src: 0`, so the docstring half of this rule is met; a comment
  ratchet would fail on files this batch does not own.

### WR-33: `lock_grants_of` locked usage rows and discarded the `None`

**Commit:** `14d1bd1`
**Files:** `src/nativespeaker/api/crud/subscriptions.py`,
`tests/unit/test_subscription_grant_write.py`

`await self.grants_db.lock_usage(grant.id)` dropped its return value, so the fail-closed signal
`_usage_statement`'s own docstring names ("`None` is the fail-closed signal, not a cue to mint a
row") was discarded at the exact point the second lock tier is taken. Bound the result and raised
`MissingUsageRowError(grant.id)` on `None`. This is the upstream half of CR-29 and refuses at the
one place where no row has been written and no lock has been spent on anything.

The refusal covers every account the call locks, including the old owner's on a cross-account
move — broader than CR-29's `grant.user_id == user_id` filter, and correct: all three grant
creators (`crud/grants.py:189`, `:292`, `crud/subscriptions.py:392`) insert the usage row with the
grant, so a marked-active grant without one is always a broken invariant.

**Guard proved by mutation.** Added `TestTheSecondLockTierRefusesAnAbsentUsageRow`: the refusal
case, a present-row control, and a lock-order control asserting the grant tier is read before the
refusal fires (`session.reads == 2`). Reverse-applying the source hunk fails the first and third
and leaves the control green.

## Skipped Issues

None. All five assigned findings held on the current code and were fixed.

## Verification

Run from `/home/init/native-speaker/ns-api-gateway` in the main checkout (no worktree — this is a
git submodule, so `.git` is a file and `IS_WORKTREE` is false). Every suite was run after each
finding, not only at the end.

| Gate | Baseline | Final | Result |
|---|---|---|---|
| `.venv/bin/ruff check src tests` | clean | clean | pass |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1620 passed | 1627 passed | pass (+7 new cases) |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 248 passed | 248 passed | pass |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 352 passed | 352 passed | pass |
| `.venv/bin/ty check src` | 3 diagnostics | 3 diagnostics | pass |

The unit count moved from 1620 to 1627: one rewritten case (net zero) plus seven added — two for
CR-29's refusal, one for WR-30's structural read-only proof, two for WR-31's timezone guard, and
three for WR-33's second lock tier. No baseline regressed and no failure was attributed to
pre-existing state.

Working tree is clean; nothing is left uncommitted. This report is **not** committed — the
orchestrator commits it.

---

_Fixer: Claude (gsd-code-fixer), part 1 of 4_
_Iteration: 1_

---

### Fixer 2

# Phase 38 code review fix — part 2 (fixer 2 of 4)

Assigned: WR-01, WR-02, WR-03, WR-04, WR-05, WR-15, WR-16. No other finding touched.
All work done directly in `/home/init/native-speaker/ns-api-gateway` on
`gsd/v2.0-authentication-entitlements`. No worktree created, no branch switched, no push.

**Summary:** 6 fixed, 1 skipped (WR-02, on a ratified clause in `AGENTS.md`).

---

## WR-01 — Google Play boot check never reads `package_name` — FIXED `8e45d59`

**Verified before editing.** `lifespan.py:171` tested only
`google_push_verifier is None or play_credential is None`. `build_google_push_verifier` (`:79`)
reads only `push_audience` and `push_service_account_email`; `_play_credential()` reads only ADC.
`config.google_play.package_name` is `str | None = None` (`config.py:117`) and is read nowhere on
the boot path, yet the warning message named it first. A pod with audience + service account + ADC
but no package name booted silent, and `dependencies.py:220` then compared every genuine
`notification.packageName` against `None` and raised `NotificationRejected` — 401 forever.

**Changed** (`src/nativespeaker/api/app/lifespan.py`): the condition now also covers
`package_name` and `products`, the two values a delivery needs and the check did not read. The
consequence text was corrected with it: an absent package name is a 401 and an empty product map a
500, so the old "fails closed as verification_temporarily_unavailable" was true of only one arm.
It now reads "refuses every delivery", which is true of all three, and names the product map.

No test asserted either boot warning, so nothing was updated or weakened.

## WR-02 — provider permit acquired with no timeout — SKIPPED

The defect as described is real in its ordering: `ChatService.create_chat` enters `admission()`,
calls `quota_service.charge(...)` (which commits a spent credit in its own session), and only then
reaches `ainvoke`, whose `self._gate.concurrency()` (`resilience.py:103-106`) is a bare
`async with self._semaphore`. But the proposed fix must not be applied, for two reasons.

**1. It contradicts a ratified clause the reviewer did not weigh.** The review filed this against
`AGENTS.md:92-93` and argued that clause settles only *where* the permit is taken. The clause the
fix actually breaks is `AGENTS.md:89-91`:

> The first attempt rides the admission verdict instead, because that is the verdict the caller's
> quota charge was committed against: **a charged request always reaches the provider at least
> once.**

`resilience.py:167-174` carries that sentence verbatim as the stated reason for the `if attempted:`
guard. Raising `QueueFullError` on a permit-wait timeout means a charged request is refused before
any provider call — exactly the outcome that clause exists to forbid.

**2. The wait is not unbounded, and refusing is worse for the payer.** `inflight_slot` hands out
`max_concurrency + max_queue` tokens, so at most `pool_size + queue_size` callers can ever be
waiting on the semaphore. Verified live: `LLMExecutionGate(5, 25, 2)._slots.qsize() == 30`. The
worst case is therefore finite (the ~8 minutes the review itself computed) and is set by
`queue_size` — a value in `config/config.yaml`, tunable with no code change. Today a saturated
request eventually reaches the provider and the credit buys the chat it paid for. With the
proposed timeout the credit is still spent and nothing is produced, unless a refund path is added
to the quota seam — which is over-engineering for this product (`AGENTS.md`: sub-$5/month, no
users yet).

Bounding the wait the other way — taking the permit before the charge — is forbidden by
`AGENTS.md:92-93` ("no gate hold spans a database round trip").

If the ~8-minute ceiling is judged too long, the honest lever is `resilience.queue_size` in
`config/config.yaml`. That is a product decision, not a code fix, and it needs a ratified
amendment to `AGENTS.md:89-91` before a refusal path can be built.

## WR-03 — uvicorn's own access log left enabled — FIXED `951ba7c`

**Verified before editing.** `uvicorn.config.LOGGING_CONFIG` gives `uvicorn.access` its own
`access` handler with `"propagate": False`, and `Config.__init__`'s `access_log` default is `True`
(both printed from the installed package). `logs.py`'s `root.handlers.clear()` therefore never
reaches it: every request emitted a second, unstructured line, and `_EXCLUDED_PATHS` did not hold
for the readiness and liveness probes.

**Deviation from the suggested fix, deliberately.** The review proposed `--no-access-log` on the
`Dockerfile` CMD. That covers one launch path of three: `README.md:55`, `PROJECT.md:210` and
`36-UAT.md:16` all start the app with a bare `uvicorn` command, and each would keep emitting the
duplicate. The root cause is that `setup_logging` owns the structured access line and the probe
exclusion but did not own the logger that duplicates them.

**Changed** (`src/nativespeaker/api/logs.py`): added `uvicorn.access` to `_QUIETED_LIBRARIES`,
which already exists for precisely this criterion — its own comment says the list is "a library
that logs a request body, a request line or SQL". Access lines are INFO, so the WARNING pin
silences them on every launch path. `uvicorn.error` is deliberately left alone: it carries startup
and shutdown failures.

**Tests** (`tests/unit/test_logging.py`): new `TestOnlyOneAccessLineIsWrittenPerRequest` — the
logger is silent at the configured level, silent at DEBUG, named in the list, and a control
asserting `uvicorn.error` still reports. Reverse-applied the source hunk: 3 of the 4 fail without
it, and the control stays green.

## WR-04 — `deviceCheckSecretName` is Helm-`required` — FIXED `b7352a9`

**Verified before editing.** `values.yaml:55-59` ships `deviceCheckSecretName: ""` and documents
"Without it both free-grant claims fail closed as 503 for the life of the deployment". The
template's `required` made `helm install` fail at render with that shipped default, so the
documented state was unreachable. The application really does implement it:
`read_private_key(None)` returns `None` (`devicecheck.py:56-57`), `lifespan.py:147-151` logs
`devicecheck_credential_absent` and boots.

**Changed** (`k8s/templates/deployment.yaml`): dropped the `required` and guarded the DeviceCheck
volume and volumeMount with `{{- if }}`, matching the ADC credential one file over. The
`credentials.secretName` `required` is untouched — that Secret carries `db.*` and
`jwt.project_id`, which genuinely have no default and cannot boot.

**One deviation from the suggested fix.** The review also proposed guarding
`DEVICECHECK_PRIVATE_KEY_PATH`. Left unconditional instead: with no Secret named there is simply no
file at that path, which `read_private_key` reads as the absent key — the same degraded outcome,
and it keeps `env:` from rendering empty in a combination I cannot test (helm is not installed
here). The comment above it now states that.

**Verification:** helm is unavailable, so all four credential combinations were rendered with a
minimal evaluator and parsed as YAML. Each produces a valid manifest, no empty list, and no mount
without its volume.

## WR-05 — the comment register `AGENTS.md` outlawed — FIXED `c36fb57`

Scope as assigned: infra + `app/` + top-level `src` only. `crud/`, `routers/` and `services/` were
not touched — fixer 1 covered them under WR-32 in `8b98167`. Per the scope note,
`services/auth.py` lines ~219-221, ~231-234, ~289-291 and ~298-300 were left alone here as well,
since neither finding names them; they remain outstanding for whoever owns that file.

**Changed**, cutting each block to the one line that resolves the ambiguity at the line below it
and deleting the design narration, the cross-module rules and the decisions made elsewhere:

- `src/nativespeaker/api/app/lifespan.py` — the x509 pre-parse, the fatal JWKS raise, the ADC
  exception family, the per-step shutdown guard, the firebase app deletion.
- `src/nativespeaker/api/config.py` — the log-level set, the required `db`/`jwt` blocks, the
  non-mapping raise, the `prompt`/`examples` collision.
- `src/nativespeaker/api/app/dependencies.py` — the nine-line `HTTPBearer` essay (replaced with
  the review's own two-line form), the `(None, None)` label, the linked-identity narrowing, the
  solver-resolved instant.
- `src/nativespeaker/api/logs.py` — the quieted-library rationale, the `colors` default, the
  5xx/4xx split.
- `config/config.yaml` — sixteen lines of pydantic-settings precedence theory cut to four, keeping
  the three rules that bind an editor of that file: no secrets, YAML outranks the environment
  (but a variable can still ADD a map entry), and add a key only when it must not vary.
- `k8s/templates/deployment.yaml` — six blocks: the service account, the security baseline,
  `fsGroup`, `readOnlyRootFilesystem`, the `image` `required`, the `envFrom` `required`.

95 lines deleted, 45 added. No coverage tags were in range (`grep` for `impl->req`/`utest->req`
over all six files returns nothing), so no OFT coverage moved. `config.yaml` still parses and the
template still renders in all four combinations.

## WR-15 — a JWT missing `aud`/`iss`/`exp`/`iat` labelled `bad_signature` — FIXED `b1ed20a`

**Verified before editing, both halves.** `bounded_reason_for` special-cased
`MissingRequiredClaimError` only for `sub`; `MissingRequiredClaimError` subclasses
`InvalidTokenError` and not `DecodeError`, so the other four fell to the line-99 catch-all. Printed
live: `iss aud exp iat -> bad_signature`, `sub -> empty_subject`. And PyJWT calls
`_validate_required_claims` at `api_jwt.py:394`, before `_validate_iss` (`:408`) and
`_validate_aud` (`:411`) — so a token omitting `aud` can never reach `InvalidAudienceError` and
could never be labelled `audience_mismatch`.

The label is provably wrong, not merely imprecise: the signature is verified before claim
validation, so anything reaching this arm carries a **valid** Google signature. It was inflating
the one counter the `invalid_external_jwt` spike alert reads as forgery.

**Changed** (`src/nativespeaker/api/auth/jwt_verifier.py`): `_MISSING_CLAIM_REASONS` maps each
claim in `DECODE_OPTIONS["require"]` onto the label of its present-but-wrong twin
(`iss`→`issuer_mismatch`, `aud`→`audience_mismatch`, `exp`/`iat`→`expired`, `sub`→`empty_subject`),
with `malformed` as the fallback — never the forgery label. No new `BoundedReason` member: the set
is closed, and `SHARED-INVARIANTS.md` § Errors requires reusing a class over minting a near
duplicate.

**Tests updated, not weakened** (`tests/unit/test_jwt_security.py`):
`test_rejects_missing_exp` and `test_requires_the_exp_claim` now expect `expired`. Both assert
*rejection*; neither docstring claims the label is the property under test ("dropping a claim from
it must fail here"), and both still fail if the claim stops being required. Added
`TestAnAbsentClaimIsNotLabelledAsForgery`: all five claims parametrized, a test that the map and
`require` are one list, and a control that a wrong-key signature still carries `bad_signature`.
Reverse-applied the source hunk: 6 cases fail without it; the `sub` case and the forgery control
stay green.

## WR-16 — the grant tables carry a dormant second clock — FIXED `66e433b`

**Verified before editing.** Seven `default_factory=lambda: datetime.now(UTC)` on `AccessTier`,
`AccessGrant` and `UserMonthlyUsage`, including `AccessGrant.starts_at`, half the shared
effective-grant predicate. All four creators pass explicit values (`crud/grants.py:185-197`,
`:288-302`, `crud/subscriptions.py:393-407`), so the factories are the source of no written value
and the comment on `UserMonthlyUsage` was false. `SHARED-INVARIANTS.md` § Grants and evaluation
time: "Derive every time-dependent value from ONE captured evaluation time ... per request."

**One review premise corrected, and re-proved.** The review implied the DDL leaves these NOT NULL
with no default; that is true only of `core.user_monthly_usage` (`:287-288`).
`core.access_grants.starts_at/created_at/updated_at` and `core.access_tiers` both carry
`DEFAULT CURRENT_TIMESTAMP`, so removing the Python factory could have moved the second clock into
Postgres instead of surfacing it. Tested against the live database with a probe table of exactly
that shape: SQLModel leaves the unset field as `None` on the instance, SQLAlchemy inserts an
explicit NULL, and Postgres raises `NotNullViolationError` — the DB default is never reached. The
loud-failure property the fix depends on therefore holds for all seven columns.

**Changed** (`src/nativespeaker/api/tables/grants.py`): dropped all seven factories, matching
`tables/purchases.py` and `tables/auth.py`, and deleted the false claim. `AccessGrant.id`'s
`default_factory=uuid7` stays — the RNG, not the clock. `ends_at`'s `default=None` stays — a
nullable column, not a minted value.

**Tests updated** — three helpers flushed these rows and relied on the factories:
`tests/e2e/conftest.py`, `tests/e2e/test_claim_registered_grant.py`,
`tests/schema/test_grant_locks.py` now pass explicit timestamps, mirroring production, where the
creating transaction owns the clock. The remaining in-memory constructions never flush and never
read the field. Added `TestTheEntitlementTablesHoldNoSecondClock` to
`tests/unit/test_tables_metadata.py` with a control on the surviving `uuid7`; it fails against the
old source.

**Left alone, deliberately:** `tables/identities.py`, `tables/users.py` and `tables/chats.py` carry
the same clock factories (confirmed by walking `model_fields` across the package). The review notes
they belong to another reviewer's scope and no assigned finding names them, so the new pin is
scoped to the three entitlement tables and says so. They remain outstanding.

---

## Verification

Run from `/home/init/native-speaker/ns-api-gateway`, in the main checkout (no worktree), after the
final commit `c36fb57`.

| Gate | Result | Baseline |
|---|---|---|
| `.venv/bin/ruff check src tests` | All checks passed | clean |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1641 passed | 1627 (+14 added) |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 248 passed | 248 |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 352 passed | 352 |
| `.venv/bin/ty check src` | 3 diagnostics | 3 |

The 3 `ty` diagnostics are `invalid-argument-type` in `auth/app_store.py:145` and
`auth/devicecheck.py:127` (twice) — neither file was touched by any finding in this part, and the
count matches the baseline exactly.

No suite reported "deselected": the schema and e2e runs both carry their marker.

---

### Fixer 3

# Phase 38 code-review fix report — part 3 (WR-45..WR-48, WR-57..WR-61)

Branch `gsd/v2.0-authentication-entitlements`, worked directly in
`/home/init/native-speaker/ns-api-gateway` (no worktree, per the submodule instruction).
One commit per finding. Every finding was verified against the live code before coding to it;
all nine held as described.

## Verification (all five, after the last commit)

| gate | result |
|---|---|
| `.venv/bin/ruff check src tests` | All checks passed |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1641 passed |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 249 passed (baseline 248, +1 from the WR-60 parametrize) |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 354 passed (baseline 352, +2 from the two new WR-47 controls) |
| `.venv/bin/ty check src 2>&1 \| tail -1` | Found 3 diagnostics (baseline) |

Working tree clean; every scratch mutation was restored from a backup copy and confirmed reverted
with `git status --short` before the next step.

---

## WR-45 — Google log-hygiene walk checks the wrong credential and the wrong envelope

**Commit:** `315a2ef`
**File:** `tests/e2e/test_google_play_webhook.py`

`_drive_every_recording_arm` now mints the foreign push token once (`foreign`), sends the refused
delivery with it, and collects every envelope it puts on the wire (`sent`), including the
undecodable and refund-review bodies. It returns `([verified, foreign], [each envelope's
message.data])`, and `test_no_record_carries_a_token_the_envelope_or_the_purchase_token` iterates
`(*credentials, *envelopes, ...)`.

**Mutation proof (two, both reverted):**
1. `auth/google_play.py:225` → `raise NotificationRejected(stage=bearer)` (the refusal path logs the
   credential). Repaired test **FAILED**; pre-fix test **PASSED**.
2. `auth/google_play.py:144` → `logger.error("google_play_message_undecodable", data=data)`.
   Repaired test **FAILED**; pre-fix test **PASSED**.

---

## WR-46 — no e2e sync case asserts a non-zero `monthly_used` on the wire

**Commit:** `5792e2f`
**File:** `tests/e2e/test_sync.py`

`test_a_current_period_grant_is_left_untouched` now reads the seeded count back off the response:
`assert response.json()["entitlement"]["monthly_used"] == _CURRENT_USED`.

**Mutation proof:** `services/sync.py:59` → `used = 0` (the handler hard-codes zero).
Repaired file: **1 failed** (this case). Pre-fix file under the same mutation: **14 passed** — the
whole module was blind to a hard-coded zero. Reverted.

---

## WR-47 — refusal-arm completeness control reads a hard-coded 2-tuple and matches only a bare call name

**Commit:** `f4cdf4b`
**Files:** `tests/e2e/test_app_store_webhook.py`, `tests/e2e/test_google_play_webhook.py`

Both narrowings closed, in both files:

1. `_called_name(node)` now returns `func.id` for an `ast.Name` **and** `func.attr` for an
   `ast.Attribute`, so `raise errors.NotificationRejected(...)` is matched. `_raised_refusal_stages`
   goes through the new `_refusal_calls(source)` helper.
2. New control `test_no_raise_site_lives_where_neither_route_control_reads_it` scans every `.py`
   file of the installed application package off disk (no imports) and asserts the set of files
   carrying a `NotificationRejected(...)` call equals `_REFUSAL_FILES` =
   `{app/dependencies.py, auth/app_store.py, auth/google_play.py}`. A raise site added anywhere else
   now fails loudly instead of shrinking both sides of the existing equality.

I did **not** take the review's literal "walk the whole package into `raised`" suggestion: that
would put Apple's stages into the Google control's `reachable` set and vice versa, breaking both
equalities. The file-set control is the review's own stated minimum and is precise.

**Mutation proof (two, both reverted):**
1. Attribute-form raise site added to `auth/google_play.py`
   (`raise errors.NotificationRejected(stage="a_new_arm")` on an unreached branch).
   Repaired `test_every_reachable_arm_is_covered_by_one_parameter` **FAILED**; pre-fix **PASSED**.
2. Raise site added to `services/subscriptions.py` (a module neither `_REFUSAL_SOURCES` reads).
   Both repaired `test_no_raise_site_lives_where_neither_route_control_reads_it` cases **FAILED**;
   both pre-fix completeness controls **PASSED**.

---

## WR-48 — three tautological assertions in the unmapped-product case

**Commit:** `3f20c5c`
**File:** `tests/e2e/test_app_store_webhook.py:410-`

Dropped the dead `notification = _notification()` and the three queries keyed on its `uuid4`
`external_id`/`notification_uuid`. The scripted seam raises before returning, so the application
never receives those keys and no implementation could have written them. What remains is the real
claim: 500, `INTERNAL` body, `_counts(...) == before`, one `unmapped_store_product` ERROR record
carrying `UNMAPPED_PRODUCT_ID`. No assertion with any power to fail was removed.

**Mutation proof (reverted):** `app/dependencies.py::verify_app_store_notification` made to swallow
the refusal and return a synthetic notification, plus `routers/webhooks.py` made to raise
`UnmappedStoreProduct` after `service.ingest(...)` — so the delivery writes all three rows and still
answers 500.
- Repaired case: **FAILED** on `assert (1, 1, 1) == (0, 0, 0)`.
- Pre-fix case: **also FAILED, and on the same line** — the three key queries at `:422-424` ran
  first and all returned `[]` while a subscription, a purchase and an event row had just been
  written. That is the tautology demonstrated empirically: they cannot fail even when the delivery
  ingests.

---

## WR-57 — wall-clock assertion in the lock-order control is not marked `timing`

**Commit:** `122347d`
**File:** `tests/schema/test_grant_locks.py`

`test_the_fixed_order_does_not_deadlock` now carries `@pytest.mark.timing`, and the 50 ms margin is
gone: B stamps `asked_at` before its lock request and `acquired_at` after it, A stamps `released_at`
immediately before its rollback, and the case asserts `asked_at < released_at < acquired_at`. That
is causal, not a threshold — B asked while A still held the row and got it only after A let go.
`_BLOCKED_FOR_SECONDS` is deleted (nothing else referenced it).

`-m "schema and timing"` now selects the case (1 passed, 30 deselected), which is the reporting
property `pyproject.toml:68` defines the marker for.

**Mutation proofs (both reverted):**
1. Contention removed at the source (A issues the two statements without `FOR UPDATE`, so it holds
   nothing): **FAILED** — `asked at 3259534.914, A released at 3259535.116, B acquired at
   3259534.916`. Note the review's own suggested assertion (`started < released_at` alone) does
   **not** catch this — I checked, it passes — which is why the acquisition stamp is in there too.
2. After WR-58 landed, a production drift (`AND source <> 'manual'` added to
   `_effective_grants_statement`) also fails this case: **FAILED** on the same premise. Before this
   batch, that drift left the case green.

---

## WR-58 — the lock "mirrors" are never compared to production

**Commit:** `9ca06ef`
**File:** `tests/schema/test_grant_locks.py`

The two hand-written strings are gone. `_lock_grants(user_id)` and `_lock_usage(grant_id)` compile
the production statements (`_effective_grants_statement(...).with_for_update()`,
`_usage_statement(...).with_for_update()`) against the asyncpg dialect with
`literal_binds=True`, so a raw connection issues exactly what production issues and there is nothing
left to drift. The 13 call sites take the function instead of a constant plus a positional
parameter. `TestTheMirrorsStillMatchProduction` is kept — renamed
`TestTheIssuedStatementsAreProductionsOwn` — because its assertions (FOR UPDATE, the ORDER BY, no
LIMIT, the five predicate terms) are claims about production and still fail if production drops any
of them.

**Mutation proof (reverted):** drift 1 from the finding — `AND source <> 'manual'` added to
`_effective_grants_statement`, which leaves all five substrings present.
- Repaired file: the contention cases **FAILED** (`control: A must actually hold the seeded grant
  row…`, and the deadlock case got `LockNotAvailableError` instead of one victim).
- Pre-fix file: **29 passed**, including every case in `TestTheMirrorsStillMatchProduction`,
  `TestTheGrantLockExcludes` and `TestTheLockOrderIsLoadBearing`. Only two unrelated activation
  cases (which drive `GrantsDB` directly) noticed. That is the finding exactly: the contention cases
  were proving things about a statement production no longer issued.

Drift 2 ("a term deleted from the mirror string") is now unrepresentable.

---

## WR-59 — the registered writer's lock-order case drops the ORDER BY check

**Commit:** `e8760df`
**File:** `tests/schema/test_grant_locks.py`

`test_the_conversion_locks_the_grant_rows_then_their_usage_rows` now loops `taken[:2]` like its
anonymous twin instead of checking `taken[0]`, and
`test_the_new_grant_locks_the_grant_tier_alone_because_it_holds_no_row` keeps the raw statements and
asserts the ordering clause on both of its grant-tier reads.

**Mutation proof (reverted):** `.order_by(col(AccessGrant.id).asc())` removed from
`_effective_grants_statement` (the second grant-tier read on both registered arms).
- Repaired: `TestTheRegisteredWriterAddsNoThirdLockTier` → **2 failed, 9 passed**.
- Pre-fix: **11 passed**. `SHARED-INVARIANTS.md:34` binds the registered path too, and it was the
  one locking two grants at once during a conversion.

---

## WR-60 — half of the registration-pairing assertion can never count anything

**Commit:** `0918843`
**File:** `tests/schema/test_registration_pairing.py`

`test_a_created_registered_account_satisfies_both_halves` is now
`test_a_created_account_satisfies_both_halves`, parametrized over
`[IdentityProvider.google, IdentityProvider.anonymous]`, with `provider_uid` derived as `None` for
anonymous (what the table's CHECK requires) and a generated `uid_…` otherwise. The premise
assertions become `result is provider`. Both scans are now exercised on the arm that can regress
them.

**Mutation proof (reverted):** `crud/identities.py:99` →
`registered_at=evaluated_at` (the conditional flipped, so every anonymous account lands in the third
state).
- Repaired: **1 failed** — `test_a_created_account_satisfies_both_halves[anonymous]`,
  `assert 1 == 0` on `_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY`.
- Pre-fix: **3 passed**. Nothing in the only file that scans the pairing over production-written
  rows noticed.

---

## WR-61 — the converse lock-freedom case asserts no premise

**Commit:** `f8af386`
**File:** `tests/schema/test_sync_lock_freedom.py`

`test_a_charge_is_not_blocked_by_an_open_sync_read` now proves its premise. A new helper
`transaction_started_at(session)` reads `CURRENT_TIMESTAMP`, which PostgreSQL fixes when a
transaction opens and never moves within it, so two equal readings are one transaction. The case
records `opened_at` before the sync read, asserts the read found an active entitlement, then asserts
the reader is still in that same transaction both **after the read** and **after the charge**.

I did not use the review's literal `assert reader.in_transaction()`: I tried it first and it does
**not** catch the regression. A `commit()` inside `read_entitlement` is followed by two more reads,
which autobegin a fresh transaction, so `in_transaction()` is `True` again by the time the assertion
runs — the case stayed green. Transaction identity, not transaction presence, is the premise.

**Mutation proof (reverted):** `services/sync.py` given back `self.session = db` and a
`await self.session.commit()` inside `read_entitlement` — "the day it does commit", which the
finding names.
- Repaired: **FAILED** — `control: the read ended its own transaction, so the charge below races
  nothing`, with the two differing transaction start times printed.
- Pre-fix: **PASSED**.
- (With `reader.in_transaction()` instead: **PASSED** under the same mutation. Recorded above.)

---

## Specs

No fix in this batch needed anything forbidden by `specs/`. `SHARED-INVARIANTS.md` § "Locks and
transactions" line 34 is what WR-59 restores coverage of on the registered path; § "Grants and
evaluation time" line 44 is the single-evaluation-time rule WR-61 protects the observability of.
`00-schema.md` and `oft-conventions.md` bear on none of the nine. No coverage tag
(`[utest->req~…]`) was added, moved or removed.

_Fixed: 2026-09-09_
_Fixer: gsd-code-fixer, part 3 of 4_
_Iteration: 1_

---

### Fixer 4

# Phase 38 code review fix — part 4 (WR-69, WR-70, WR-71, WR-83, WR-84, WR-85)

Worked directly in `/home/init/native-speaker/ns-api-gateway` on
`gsd/v2.0-authentication-entitlements`. No worktree was created. Every gate below ran in the main
checkout, so the numbers are reproducible from the tree as it stands. Each mutation was applied to
a `/tmp` backup copy of the production file, run, then restored; `git status --short` was confirmed
clean of `src/` after every proof.

## WR-69 — the carried DeviceCheck bit could not be told from a hardcoded `False`

**Commit:** `41b8e62`
**Files:** `tests/unit/test_claim_precedence.py`, `tests/unit/test_claim_precedence_registered.py`

The finding held. `_ScriptedDeviceCheck.answer` defaults to `BitState(False, False)`, and every
override in either suite (`bit0=True` on the anonymous side, `bit1=True` on the registered side)
refuses at `DeviceGrantExhausted` before the write, so the carried bit was `False` in every write
either suite observed.

Added one case per suite,
`TestEveryOutcomeFromTheClaimOnwardConsumesExactlyOnce::test_the_other_bit_is_carried_forward_rather_than_fabricated`,
which scripts the *opposite* bit as already set — the arm the completion does not refuse — and
asserts the write carries it forward:

- anonymous: `BitState(bit0=False, bit1=True)` → `write_calls == [(DEVICE_TOKEN, True, True)]`
- registered: `BitState(bit0=True, bit1=False)` → `write_calls == [(DEVICE_TOKEN, True, True)]`

**Mutation proof.** In `src/nativespeaker/api/services/auth.py`, replaced `bit1=state.bit1` with
`bit1=False` (`_claim_anonymous_grant`) and `bit0=state.bit0` with `bit0=False`
(`_claim_registered_grant`) — the exact fabrication the comments forbid. Result over both suites:
**2 failed, 74 passed**, the two failures being exactly the two new cases. The 74 that stayed green
include both pre-existing `# bit N carried forward` assertions, confirming the finding's claim that
they were blind to the mutation. Restored; `git status --short` showed no `src/` change.

## WR-70 — the 422 came from the missing required `device_token`, not from any handling of extras

**Commit:** `2ae3348`
**File:** `tests/unit/test_claim_precedence.py`

The finding held: `GrantClaimRequest` declares no `model_config`, so it takes pydantic's default
`extra='ignore'`, and the body under test omitted `device_token` entirely.

No assertion was deleted. The original case was renamed to what it actually measures —
`test_a_body_naming_no_device_is_rejected_before_the_gate` — keeping the 422, the empty
`read_calls` and `consume_calls == 0`, since nothing else in `tests/unit` covers the
missing-required-token arm on this route. Alongside it, added
`test_a_body_offering_a_second_token_never_reaches_the_gate_with_it`, which keeps a valid
`device_token` so the two extra keys are the only variable, and asserts the claim succeeds with one
device named on the read and on the write.

The alternative the finding raises — `ConfigDict(extra="forbid")` on `GrantClaimRequest` — was not
taken: it changes the wire contract and `03-sync.md` / `SHARED-INVARIANTS.md` do not call for it.

**Mutation proof.** Added `model_config = ConfigDict(extra="forbid")` to `GrantClaimRequest` in
`src/nativespeaker/api/schemas/auth.py`. Result over both claim suites: **1 failed, 76 passed** —
only the new case fails (422 where it asserts 200), while the renamed missing-token case still
passes, which is the finding's point restated as evidence. Restored.

## WR-71 — the pre-auth-callable case was a guarded loop that ran zero times if a route vanished

**Commit:** `106a56f`
**File:** `tests/unit/test_app_wiring.py`

The finding held. Rewrote the case to the shape its sibling at `:75-79` already uses: parametrized
over `sorted(PREAUTH_CALLABLE_PATHS)`, asserting `declared, f"{path} is not a registered route"`
before asserting `get_identity in calls`. The case is now driven off the literal — which D-10 names
as the authoritative record — rather than off the live route table.

**Mutation proof.** Renamed the route in `src/nativespeaker/api/routers/auth.py` from
`/auth/challenge` to `/auth/challenge-renamed`, i.e. the exact "renamed or dropped" case the finding
names. New case: **1 failed, 1 passed** (`[/auth/challenge]` fails on "is not a registered route").
Then reverted the test file to `HEAD` and re-ran the *old* case under the same mutation: **1
passed** — it was structurally unable to fail. Both files restored.

## WR-83 — the sync stub session ignored every lookup key

**Commit:** `9fdf4ec`
**File:** `tests/unit/test_sync_resolver.py`

The finding held: `_StubSession.exec` dispatched on `column_descriptions[0]["entity"]` alone, and
`_compiled()` renders every bound value as a `%(name)s` placeholder.

Rather than wrap `GrantsDB`, the values are read off the statements the stub already keeps, so the
production crud statements stay the thing under test. Added a `_bound(statement)` helper returning
`statement.compile(dialect=postgresql.dialect()).params.values()`, and a class
`TestEveryReadIsKeyedOnWhatTheOneBeforeItNamed` with four cases: the grant read is keyed on
`USER_ID`; both grant bounds carry `EVALUATED_AT` and nothing else; the usage read is keyed on the
id of the grant the first read returned; the allowance read is keyed on that grant's own `tier_id`.
Also added the tenant-scope text assertion its quota sibling already carries —
`test_the_predicate_is_scoped_to_one_owner` — to `TestThePredicateBoundaries`.

**Mutation proof.** All four mutations the finding tabulates were applied to
`src/nativespeaker/api/services/sync.py`, one at a time (baseline 36 passed):

| mutation | before | after |
|---|---|---|
| `read_effective_grants(UUID(int=1), …)` | 30 passed | **1 failed** (`…keyed_on_the_caller…`), 35 passed |
| `read_usage(UUID(int=2))` | 30 passed | **1 failed** (`…keyed_on_the_grant…`), 35 passed |
| `monthly_credits("some-other-tier")` | 30 passed | **1 failed** (`…that_grants_own_tier`), 35 passed |
| `read_effective_grants(user_id, datetime(2000,1,1,UTC))` | 30 + 11 passed | **1 failed** (`…the_one_captured_instant`), 35 passed |

A fifth mutation covering the new text assertion: dropped
`col(AccessGrant.user_id) == user_id` from `_effective_grants_statement`
(`src/nativespeaker/api/crud/grants.py`) → **2 failed** (`test_the_predicate_is_scoped_to_one_owner`
and the caller-key case), 34 passed. All files restored.

## WR-84 — dropping the owner predicate from `PurchasesDB.read_tokens` left both suites green

**Commit:** `3a0dce4`
**Files:** `tests/unit/test_purchases_crud.py`, `tests/unit/test_users_me.py`

The finding held. Both stubs answer `exec()` with the whole seeded mapping regardless of statement,
and neither suite looked at the `WHERE` clause of the one statement it already had in hand.

- `test_purchases_crud.py`: added `_bound()` and a class `TestTheReadIsScopedToOneOwner` with two
  cases — the compiled statement carries `core.store_purchase_tokens.user_id = `, and the value it
  is keyed on is exactly `[USER_ID]`.
- `test_users_me.py`: added `_bound()` and
  `TestTheProfileTakesOneQuery::test_the_read_is_keyed_on_the_barrier_resolved_caller`, asserting
  both the predicate text and that the bound value is `identity.user.id` — the id the barrier
  resolved, not one the test chose.

**Mutation proof.** Two mutations to `src/nativespeaker/api/crud/purchases.py:19` (baseline 36
passed across the two files):

- the finding's own mutation, a predicate matching every row
  (`col(StorePurchaseToken.user_id) == col(StorePurchaseToken.user_id)`): was 33/33 green,
  now **2 failed, 34 passed** — the two bound-value cases fire. The text assertion correctly does
  not, because `user_id = user_id` still renders that text; that is why the bound value is asserted
  separately.
- the predicate removed entirely: **3 failed, 33 passed**.

Restored after each.

## WR-85 — only `manual` of the four spec-enumerated sources reached `EntitlementType(...)`

**Commit:** `48d3907`
**File:** `tests/unit/test_sync_resolver.py`

The finding held: `_grant()` hardcoded `source=AccessGrantSource.manual`, and `grep` confirms the
other three members are reached only in `tests/e2e` and `tests/schema`, both deselected by the
default `addopts`.

Gave `_grant()` a `source=AccessGrantSource.manual` keyword (default unchanged, so no existing case
moved) and added `TestEverySourceIsReportedAsItsOwnType`: a totality case pinning
`{m.value for m in AccessGrantSource} <= {m.value for m in EntitlementType}`, and a case
parametrized over `list(AccessGrantSource)` asserting the resolver reports each source as its own
wire type at `EntitlementStatus.active`.

**Mutation proof.** Baseline 41 passed. Both halves of the finding's failure mode:

- a member renamed on one side only —
  `EntitlementType.subscription = "subscriptions"` in `src/nativespeaker/api/schemas/auth.py`:
  **2 failed** (`test_every_grant_source_has_a_wire_type`, `…[subscription]`), 39 passed.
- a fifth `core.access_grant_source` value — `partner_grant` added to `AccessGrantSource` in
  `src/nativespeaker/api/tables/grants.py`: **2 failed**
  (`test_every_grant_source_has_a_wire_type`, `…[partner_grant]`), 40 passed.

Both restored.

## Verification (all five, main checkout, after the sixth commit)

| gate | result | baseline |
|---|---|---|
| `.venv/bin/ruff check src tests` | All checks passed | clean |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1658 passed | 1641 |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 249 passed | 249 |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 354 passed | 354 |
| `.venv/bin/ty check src` | Found 3 diagnostics | 3 |

Unit rose by 17: WR-69 +2, WR-70 +1, WR-71 +1, WR-83 +5, WR-84 +3, WR-85 +5. No production file was
changed by any of the six commits; `git status --short` is clean.


---

_Fixed: 2026-09-09T21:26:58Z_
_Fixer: Claude (gsd-code-fixer) x4, sequential; merged by orchestrator_
