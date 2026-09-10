---
phase: 40-post-auth-upgrade-anonymous
fixed_at: 2026-09-09T00:00:00Z
review_path: .planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md
iteration: 1
fix_scope: critical_warning
findings_in_scope: 33
fixed: 29
skipped: 4
status: partial
---

# Phase 40: Code Review Fix Report

**Fixed at:** 2026-09-09
**Source review:** .planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 33 (all Critical and Warning findings; Info was out of scope)
- Fixed: 29
- Skipped: 4

The fix scope was split across five `gsd-code-fixer` agents that ran strictly
sequentially over the one shared git index, grouped by module. Their reports are merged
below without narrowing. Every finding is accounted for.

## Fixed Issues

One commit per finding, in the order they landed:

| Commit | Finding | Subject |
|---|---|---|
| `a91f9c9` | WR-01 | stop get_db committing after the response is sent |
| `8e6a6f6` | WR-02 | let LOG_LEVEL be a per-deployment lever again |
| `4047306` | WR-04 | declare OPENAI_API_KEY as the seventh boot-blocking setting |
| `ddc63c7` | WR-05 | ping and recycle pooled database connections |
| `e1fa976` | WR-06 | state the Envoy Gateway v1.2 floor where the operator reads it |
| `096878c` | WR-08 | resolve the Apple root certificate against config_dir |
| `b4b4f00` | WR-20 | read the DeviceCheck body before its status and reserve proof_rejected for the token |
| `fd18694` | WR-21 | separate the DeviceCheck and Firebase retry attempts in time |
| `e4985e6` | WR-22 | name every unusable JWKS answer in the operator log, not the connection one alone |
| `0083233` | WR-23 | withhold the record email on the anonymous providerData arm |
| `9b28e5f` | WR-24 | bound the challenge handle and the DeviceCheck token |
| `675bee0` | WR-38 | fail closed on a missing usage row in the anonymous activation |
| `d5fb2ce` | WR-37 | fail closed on two carried usage rows instead of keeping the last |
| `5fe1cf4` | WR-50 | make both DeviceCheck bit-write swallows total, as their comments promise |
| `9c36717` | WR-51 | leave one log line per quota integrity failure, not two |
| `0cced39` | WR-35 | record what the insert's conflict arm actually collapses |
| `22930a6` | CR-90 | restore every logger level setup_logging writes, not just the root's |
| `dfe7cef` | WR-70 | read the commented placeholders and assert they parse |
| `155fed8` | WR-71 | walk every auth module the SDK claim covers, not just adapters |
| `e09fc9b` | WR-72 | assert a successful create-user spends its challenge |
| `2da120a` | WR-91 | assert the one operator record each lost race writes |
| `0faa2f3` | WR-92 | present the Pub/Sub body at the bound the control names |
| `ae1f7ef` | WR-93 | decide every spelling a second grant writer could arrive in |
| `0a6bb2e` | WR-94 | see every spelling of a clock read, not one |
| `597d370` | WR-71 | keep the class docstring inside the three-line bar |
| `98991be` | WR-72 | keep the case docstring inside the three-line bar |
| `e62ff48` | WR-93 | keep the helper docstring inside the three-line bar |
| `58ed4e1` | WR-110 | resolve the admin app before the user starts existing |
| `efe43bb` | WR-111 | record and assert the instant each store restore was checked at |
| `9d1f5cf` | WR-113 | hold the refusal-site scan and the log spy in one place each |
| `8a12627` | WR-112 | assert the stage each refused proof records, so the four arms differ |
| `08feffb` | WR-114 | drive the anonymous writer's platform-pin refusal |
| `b575c84` | WR-113 | keep the module docstring inside the three-line bar |

## Skipped Issues

### CR-20: `term_end_for` picks a term field by a status from another source

**Reason:** already fixed. This re-files phase 37.5 CR-25, landed in `559deaa`, where the
same remedy was examined and declined. Fixer 2 applied the review's suggested fix and
measured it: on the finding's own Apple trace `term_end_for(proof)` returns
`proof.expires_at`, which is already past during grace, so `services/restore.py:116`
refuses on the next line regardless. Applying it broke two settled e2e cases and a unit
control that pins this exact case; it was reverted and the tree carries none of it.
The one case its predecessor did not cover — a Play row still reading `grace_period`
while the live read reports active with a future expiry — is refused today under D-06,
and closing it means deciding whether a live provider read may outrank a stale canonical
row. That is a spec decision, not a code-review fix.

### WR-03: `db.pool_size` in `config/config.yaml` outranks the environment

**Reason:** ratified. Phase 41 D-16 accepted exactly this trade-off, in terms — "this
forecloses `DB_POOL_SIZE` from `.env`". Reverting it reopens the `STATE.md` blocker A-15
that D-16 was taken to close.

### WR-07: the quota credit is charged before an unbounded permit wait

**Reason:** the diagnosis holds but the proposed remedy is self-defeating. The suggested
`wait_for` sits inside `concurrency()`, i.e. after the charge, so it converts "charged and
served late" into "charged and refused".
`tests/unit/test_quota_seam.py::TestAdmissionHoldsNoProviderPermit::test_a_charge_commits_while_every_permit_is_taken`
pins the D-15 invariant the suggested fix would turn into a billed 503. The genuine root
cause — the charge commits before the request is known servable, and `QuotaService` has no
refund path by design — is a ratified decision to reopen, not something to patch in the
`concurrency()` helper.

### WR-36: `lost_race` is returned for any unique violation on the final flush

**Reason:** ratified. Phase 41 D-13 settles the catch-and-re-read outcome and names
`ix_access_grants_one_active_per_user` explicitly. Fixer 3 also measured the residual
harm as near zero: the window needs the rival insert to commit while this writer holds
its locks, but if the caller held any effective or marked-active grant those rows are
locked `FOR UPDATE` and `write_subscription_grant`'s `lock_grants_of` blocks. It can only
arise when the caller holds nothing, and the re-read then returns the rival's
subscription grant — a genuine, better entitlement — with the free slot unspent.

## Per-fixer reports

### Fixer 1 — infrastructure, deployment, app wiring, config, resilience (WR-01 … WR-08)

**Source review:** `.planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md`
**Subset:** WR-01, WR-02, WR-03, WR-04, WR-05, WR-06, WR-07, WR-08

**Summary:**
- Findings in scope: 8
- Fixed: 6
- Skipped: 2 (both settled or provably wrong; see below)

##### Verification

All five gates run from `/home/init/native-speaker/ns-api-gateway` on the finished tree, in the
main checkout (no worktree — `<worktree_override>`), so every number below is reproducible from
the tree as it stands.

| Gate | Baseline (8d45be8) | After |
|---|---|---|
| `.venv/bin/ruff check src tests` | clean | clean |
| `.venv/bin/pytest tests/unit -q` | 1674 passed | **1684 passed** (+10 new guards) |
| `.venv/bin/pytest tests/schema -q -m schema` | 249 passed | 249 passed |
| `.venv/bin/pytest tests/e2e -q -m e2e` | 354 passed | 354 passed |
| `.venv/bin/ty check src` | 3 diagnostics | 3 diagnostics |

No regression was introduced, so no failure had to be attributed to a pre-existing cause.

##### Fixed Issues

###### WR-01: `get_db` commits after the response body is sent

**Files modified:** `src/nativespeaker/api/app/dependencies.py`,
`src/nativespeaker/api/routers/auth.py`, `src/nativespeaker/api/services/sync.py`,
`tests/unit/test_sync_resolver.py`, `tests/unit/test_quota_seam.py`,
`tests/unit/test_challenge_endpoint.py`, `tests/e2e/test_users_me.py`, `tests/e2e/test_sync.py`
**Commit:** `a91f9c9`

Took the finding's second option: the teardown commit is deleted and `get_db` is a rollback-only
guard. Verified the premise before editing — every mutating path already commits for itself
(`ChatService` ×4, `AuthService` ×4, `SubscriptionsService` ×2, `RestoreService`, `QuotaService`
in its own session, and `routers/auth.py:74`), so the teardown commit was an unobservable second
write channel and nothing else.

The finding's first option (`Depends(get_db, scope="function")` at every use site) was not taken:
it leaves the write channel in place and spreads a keyword across every router, where deleting it
from one site silently restores the defect.

Proved empirically rather than by reading: the **e2e suite (354) and schema suite (249) both pass
against the live PostgreSQL**, which is what would fail if any route had been relying on the
removed commit for durability.

Also corrected the six comments and docstrings across `src/` and `tests/` whose stated rationale
was "`get_db` commits on teardown" — that sentence is now false, and a stale rationale is how the
next reader re-introduces the hazard. No assertion was changed.

###### WR-02: `config.yaml` pins `log_level`, so `LOG_LEVEL` is silently ignored

**Files modified:** `config/config.yaml`, `.env.example`, `k8s/values.yaml`,
`tests/unit/test_config.py`
**Commit:** `8e6a6f6`

Reproduced first (`log_level: INFO (env said DEBUG)`), then deleted the key. `AppConfig.log_level`
already defaults to `INFO`, so the shipped behaviour is unchanged and the lever is now live —
re-measured: unset → `INFO`, `LOG_LEVEL=DEBUG` → `DEBUG`.

Documented the variable in `.env.example` (which never mentioned it) and above the chart's
`env: []` escape hatch in `k8s/values.yaml`, with the reason a value in `config.yaml` cannot be
overridden there.

Added `TestTheLoggingLevelIsAPerDeploymentLever` (3 cases, including a control and a guard that the
tracked file declares no `log_level`). This defect was silent by construction and was filed once
before as IN-63 in `39-REVIEW.md`; without a guard it returns the next time someone tidies the file.

###### WR-04: `OPENAI_API_KEY` is boot-blocking but is in no config model and neither chart list

**Files modified:** `src/nativespeaker/api/config.py`, `src/nativespeaker/api/services/llm.py`,
`src/nativespeaker/api/app/lifespan.py`, `tests/unit/test_config.py`,
`tests/e2e/test_llm_schema.py`, `k8s/values.yaml`, `k8s/templates/deployment.yaml`, `.env.example`
**Commit:** `4047306`

Reproduced the boot failure (`OpenAIError: The api_key client option must be set…`) — real, and
raised by `init_chat_model`, not `ChatOpenAI` directly as the finding says; the consequence is the
same.

Corrected the finding's proposed remedy. It suggested `ModelConfig.api_key` fed by `MODEL_API_KEY`,
"or keep `OPENAI_API_KEY` via `validation_alias`". I tested the alias route: pydantic-settings does
**not** consult a nested `BaseModel`'s `validation_alias` when splitting environment names, so it
does not work (`ValidationError: model Field required`). And `MODEL_API_KEY` would silently retire
the variable name `.env.example`, the chart, and `tests/e2e/test_llm_schema.py` all already use.

Built instead the shape this codebase already uses for provider credentials (`devicecheck:`,
`app_store:`, `google_play:`): a provider-named block `openai:` with one required `SecretStr`
field, which `OPENAI_API_KEY` populates through the existing nested delimiter — verified before
writing it. The key is now passed explicitly to `init_chat_model` rather than left ambient, and
both chart lists say seven settings, not six.

Added `TestTheProviderKeyIsADeclaredSetting`: an absent key is a `ValidationError` naming `openai`,
and the key never renders in a repr or a dump — the secrecy the other six credentials already have.
Re-ordered the `llm_service` fixture's dependencies so `tests/e2e/test_llm_schema.py` still *skips*
without a real provider key rather than erroring on the now-required field.

###### WR-05: no `pool_pre_ping` or `pool_recycle` on the database engine

**Files modified:** `src/nativespeaker/api/app/lifespan.py`, `tests/unit/test_config.py`
**Commit:** `ddc63c7`

Applied as suggested, plus one structural change: the engine construction moved out of the
`lifespan` body into `build_db_engine(db)`, named and placed like its three existing siblings
(`build_app_store_verifier`, `build_google_push_verifier`, `build_jwt_verifier`). Inline, the pool
settings were unassertable, so the fix could not be pinned — which is what let the gap exist.

Added `TestThePoolChecksAConnectionBeforeHandingItOut` (3 cases, with a control proving the builder
does not ignore its arguments). Measured: `pre_ping=True`, `recycle=1800`, `size=5`, `overflow=0`.

###### WR-06: `SecurityPolicy.spec.jwt.optional` is silently dropped on Envoy Gateway < v1.2

**Files modified:** `k8s/templates/NOTES.txt`, `k8s/values.yaml`
**Commit:** `e1fa976`

Documentation only, which is the whole available fix: the chart cannot read a CRD schema, and
`oft-conventions.md` puts `k8s/` outside the trace inputs. The floor, the pruning behaviour, the
resulting wrong body, and the post-install check (`curl -s $GATEWAY_URL/ | jq -e .code`) are now
stated in the two places an operator actually reads — the install notes and above the `gateway:`
block — instead of only in a template comment.

###### WR-08: the Apple root certificate path is resolved independently of `config_dir`

**Files modified:** `src/nativespeaker/api/config.py`, `tests/unit/test_config.py`, `.env.example`
**Commit:** `096878c`

Took the finding's primary remedy (derive it) rather than its "at minimum" fallback (log the
resolved path), since the fallback leaves the two roots free to diverge.

Corrected one detail of the proposed implementation. The finding suggested
`mapping.setdefault("app_store", {}).setdefault("root_certificate_path", …)` — writing into
`mapping` makes the derived value `init_settings`, which would **outrank**
`APP_STORE_ROOT_CERTIFICATE_PATH` and destroy the only way to point the certificate elsewhere. I
verified that variable currently works, so the derived value is filled *after* `AppConfig` is
constructed, where it fills an absent value only.

Measured all three behaviours: default `config/` → `config/certs/AppleRootCA-G3.cer` (unchanged,
D-10 intact); `CONFIG_DIR=/tmp/x` → `/tmp/x/certs/AppleRootCA-G3.cer`; explicit env →
`/etc/ns/apple.cer`. Rewrote `TestTheDefaultRootCertificateIsTheCommittedAppleRoot` to assert the
*resolved* path through `EnvironmentConfig` (it previously asserted the literal default, which no
longer exists) and added the two cases the old suite could not express.

##### Skipped Issues

###### WR-03: `config.yaml` pins `db.pool_size`, so the pool cannot be sized per deployment

**File:** `config/config.yaml:18-19`
**Reason:** settled by a ratified decision that costed this exact trade-off.

**Phase 41 D-16** (`41-02-SUMMARY.md:45`) reads:

> "D-16: `db.pool_size: 12` lives in the tracked config.yaml, **accepting that this forecloses
> `DB_POOL_SIZE` from .env**"

and `41-PATTERNS.md:653` states the same thing at the point of implementation:

> "YAML is authoritative for anything it declares, so a `db:` block forecloses `DB_POOL_SIZE` from
> `.env` — **that is the trade-off**, and `config.py:25` is the alternative site."

The finding argues D-16 "was never costed against `replicaCount`". That is a narrower framing of a
decision that explicitly costed the loss of environment overridability — which is precisely what
this fix would reverse. Removing the block would also reopen **STATE.md blocker A-15** (pool
exhaustion at three concurrent chat posts, `41-02-PLAN.md:330`, threat T-41-13), since the field
default is 5 and D-16 raised it to 12, and would break D-16's own conformance case
`TestTheTrackedPoolSizeMergesWithTheEnvironmentCredentials`.

Re-sizing the pool per deployment is a live concern worth raising, but it is a decision to reopen,
not a defect to patch inside a code-review fix.

###### WR-07: the quota credit is charged before an unbounded wait for a provider permit

**File:** `src/nativespeaker/api/resilience.py:115-119`, `:208-210`, `config/config.yaml:6-13`
**Reason:** the diagnosis is right, but **both proposed remedies provably fail to achieve the
finding's own stated goal, and the primary one makes the named harm worse.**

The ordering claim is correct and I confirmed it: `services/chats.py:100-102` charges inside
`admission()`, and the permit wait is in `ainvoke` (`resilience.py:210`), i.e. **after** the charge
has committed.

That is exactly why the suggested fix does not work. The finding states its goal as bounding the
wait "so a request that cannot be served promptly is refused **before it is charged**" — but it
puts the `asyncio.wait_for` inside `concurrency()`, which is entered after the charge. Applied, it
would convert "charged and served late" into "charged and refused with a 503", with no refund path.
The repository already records this as the wrong direction:

- **Phase 41 D-15** (`41-CONTEXT.md:44-46`): "Rejected: charging before admission (a 503 would have
  already paid, and **the quota code deliberately has no refund path**)".
- **Phase 37.5 A-02** (`37.5-CONTEXT.md:485-487`): "both admission rejections are 503s and **both
  currently bill; neither should**."
- The in-code rationale at `resilience.py:180-184`, ratified with D-14, rests on the wait being
  unbounded: "the permit above is an unbounded wait, so re-deciding here what `admission()` already
  decided refuses a request that has made no provider call while its caller's quota charge …
  stands. **A charged request always reaches the provider at least once.**"

`tests/unit/test_quota_seam.py::TestAdmissionHoldsNoProviderPermit::test_a_charge_commits_while_every_permit_is_taken`
pins that invariant against the real gate: with every permit held, the charge commits and closes,
and the request then waits. The suggested fix turns that green case into a billed 503.

The finding's "cheaper alternative" — cut `queue_size` — does not reach the goal either, by its own
arithmetic: one wave alone is `3 × 30 + 1.5 ≈ 91.5 s`, already six times Envoy's 15 s route
timeout, so no `queue_size ≥ 1` puts the worst case under it. Shedding *does* already happen before
the charge, instantaneously, at the 30-slot `inflight_slot` boundary.

The real root cause of "charged for nothing" is that the charge commits before the request is known
servable and `QuotaService` has no refund path by design. Fixing that means charging on success or
building a refund — an architectural change against a ratified decision, not a review fix. Filing
it as such is the honest disposition; patching `concurrency()` would be a symptom workaround that
increases the harm it names.

### Fixer 2 — auth/ adapters and schemas/ (CR-20, WR-20 … WR-24)

**Source review:** `.planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md` (reviewer 2)
**Iteration:** 1

**Summary:**
- Findings in scope: 6
- Fixed: 5
- Skipped: 1 (CR-20, the group's only blocker — already settled and its suggested fix disproven)

Every fix was negative-controlled: the source hunk was reverted in place, the new cases were
confirmed to fail, and the fix was restored. All work was done directly in the main checkout on
`gsd/v2.0-authentication-entitlements`; no worktree was created.

##### Fixed Issues

###### WR-20: every DeviceCheck 400 was a definitive `proof_rejected`

**Files modified:** `src/nativespeaker/api/auth/devicecheck.py`,
`tests/unit/test_devicecheck_adapter.py`
**Commit:** `b4b4f00`

Both halves were real and both are fixed. `REQUIREMENTS.md:38` records the first half as phase 41
**WR-02, still open**, so nothing settled it.

(a) `_parse_bit_state` called `_reject_or_retry` before it read the body, so a `400` carrying
`Failed to find bit state` — the eligible first-ever claim, the only case the free grant exists
for — raised `ProofRejected` and the anonymous grant granted nothing to anybody. The body is now
read first. Narrower than the review's version in one way: the pre-status read is skipped for a
`5xx`, so an outage page that happens to echo that text cannot mint the grant it must deny. A
control case pins that.

(b) `_reject_or_retry` mapped every `400` to `ProofRejected`, including Apple's faults in the
request *this service* built — `Invalid or missing timestamp` follows from pod clock skew alone.
Spec 06:83 reserves `proof_rejected` for vendor **material** failures and routes a dependency fault
to `verification_temporarily_unavailable` (`native_claim_unavailable`). Those 400s now retry and
then 503.

**Deviation from the suggested fix, deliberate:** the review proposed a frozenset of two exact
bodies. Used a `"device token"` phrase test instead. `tests/unit/test_devicecheck_adapter.py:2-3`
states that these literals are `[ASSUMED]` from secondary sources (`41-RESEARCH.md` A3), and an
exact table would reclassify a genuine token rejection as a 503 on any wording drift. The phrase
covers both documented device-token bodies and matches none of the request-fault ones. Both shapes
fail closed; this one is robust to the assumption the test file itself flags.

Tests: `test_arm_one_a_400_is_a_definitive_refusal_after_exactly_one_attempt` asserted the wrong
expectation — its body, `Missing or badly formatted authorization`, faults this service's own
bearer, not the caller's device. Replaced by two parametrised cases splitting the two kinds of 400,
plus a 400-carrying-never-set case and its 5xx control. Six cases fail with the fix reverted.

###### WR-21: both provider retry budgets had no backoff

**Files modified:** `src/nativespeaker/api/auth/devicecheck.py`,
`src/nativespeaker/api/auth/firebase.py`, `tests/unit/test_devicecheck_adapter.py`,
`tests/unit/test_firebase_retry.py`
**Commit:** `fd18694`

All three `AsyncRetrying` constructions passed no `wait`, so tenacity used `wait_none()` and both
three-attempt budgets were spent inside a few milliseconds. Added
`wait_exponential(multiplier=…, exp_base=2, max=…)` in `resilience.py`'s own shape, from named
module constants beside the existing `*_ATTEMPTS`.

**Values chosen against the review's implied ones, deliberate:** `0.1 / 0.5` (0.2 s then 0.4 s), not
`resilience.py`'s `0.5 / 4`. Two reasons, in order of weight. First, latency: each adapter already
carries an 8-second per-attempt timeout, so an exhausted budget is 24 seconds deep before any
backoff, well past Envoy's default route timeout — seconds of idle waiting spend what is left of a
caller's patience on nothing, while sub-second gaps still separate the attempts in time, which is
the whole point. Second, and lesser: `0.5 / 4` measured the unit suite at 90 s against a 38 s
baseline; the chosen values cost ~11 s.

Tests: a new `TestTheAttemptsAreSeparatedInTime` in each file measures elapsed time across an
exhausted budget against a 0.3 s floor, each with a not-exhausted control so the floor is proven to
discriminate. Four cases fail with the `wait=` hunks stripped.

###### WR-22: an unusable-but-reachable JWKS endpoint produced a silent fleet-wide 401 storm

**Files modified:** `src/nativespeaker/api/auth/jwt_verifier.py`, `tests/unit/test_jwks_offload.py`
**Commit:** `e4985e6`

The operator line was gated on `PyJWKClientConnectionError` alone. Verified against the installed
PyJWT rather than inferred — all three conditions the finding names are real, and one of them does
not reach the arm the finding cites:

| endpoint answer | what PyJWT raises |
|---|---|
| an error page served at 200 | `json.JSONDecodeError` — **not** a `PyJWTError` |
| a body that is not an object | `PyJWKClientError("… did not return a JSON object")` |
| a set holding no signing key | `PyJWKClientError("… did not contain any signing keys")` |

`fetch_data` converts `URLError` and `TimeoutError` only, so the first lands on the bare
`except Exception` arm. Fixing only the `PyJWKClientError` arm would have left a third of the filed
defect live, so both arms now log. The condition is inverted to "every `PyJWKClientError` that is
not the definitive key-id miss", and the event is renamed `jwks_endpoint_unreachable` →
`jwks_endpoint_unusable` with a `failure=<class name>` field — the old name would have lied for a
reachable endpoint. Renaming is free here: nothing is deployed. Only the class name travels, never
the exception text, which embeds the JWKS URL or the served body.

`PyJWKClientConnectionError` became an unused import and was dropped.

Tests: the existing assertion was updated to the new event name, and a parametrised case covers all
three answers, built from the measured table above. The existing "a bogus key id over a healthy
endpoint logs nothing" control still passes unchanged, which is what keeps the new line from being
one written for every refusal. Four cases fail with the fix reverted.

###### WR-23: an anonymous Firebase record carried a verified address onto the account

**Files modified:** `src/nativespeaker/api/auth/firebase.py`, `tests/unit/test_firebase_adapter.py`
**Commit:** `0083233`

`_read` computed `email=_verified_email(...)` regardless of which arm `_resolve_provider` took, so
a record with `providerData == []` and a populated verified `email` — what Firebase leaves after a
client unlinks its last provider — produced `VerifiedProviderIdentity(provider=anonymous,
email=<address>)`, against the invariant `adapters.py:17-18` states. `services/auth.py:315-321`
wrote it, and `crud/identities.py:155-157` then refuses to overwrite a non-NULL `user.email`, so a
later genuine upgrade kept the stale address forever with no repair route
(`04-users-me.md:53`). The address is now withheld on the anonymous arm.

Tests: three cases in `TestTheEmailRuleIsAppliedInsideTheRead` measured the copy rule through an
anonymous record, where it is now unconditionally `None` — they would have become tautologies.
Moved onto a classified record so they still discriminate, which is a strengthening, not a
weakening: `test_every_other_combination_yields_none` now has something to withhold. One new case
pins the rule itself; it fails with the fix reverted.

###### WR-24: `challenge_id` and `device_token` carried no upper bound

**Files modified:** `src/nativespeaker/api/schemas/auth.py`, `tests/unit/test_models.py`
**Commit:** `9b28e5f`

`REQUIREMENTS.md:38` records this as phase 41 **WR-09, still open**. Applied as suggested:
`challenge_id` at 64 (the handle is minted at 22), `device_token` at 4096 — the value is relayed
verbatim into the body this service posts to Apple, at this service's expense and inside its own
8-second timeout. Every neighbouring field in the module was already bounded and says why.

Tests: a new `TestTheAuthBodyStringsAreBounded` follows the existing
`TestTheUnauthenticatedWebhookBodiesAreBounded` table shape — the bound is read off the model, and
each case is paired with a control asserting the bound stands at least twice above the real value,
so a bound set below a genuine request fails. `CHALLENGE_ID_CHARACTERS` is measured by calling
`new_challenge_id()` rather than restated. Six cases fail with the fix reverted.

##### Skipped Issues

###### CR-20: `term_end_for` reads the term field chosen by a status from a different object

**File:** `src/nativespeaker/api/auth/store_notifications.py:62-67`
**Reason:** already settled by phase 37.5 **CR-25**, and the suggested fix is disproven — applied
and reverted.

CR-20 is a re-file of `37.5-REVIEW.md:483`, **"An Apple restore of a subscription in `grace_period`
is always refused, because the status is read off the row and the term off the proof"** — the same
defect, the same three files, the same Apple trace. It was fixed in `559deaa`
(`fix(37.5): CR-25 read the restore term from whatever decided the status`). The fix is the
`recorded_term` list at `services/restore.py:106-109`: where a canonical row decided the status, the
term is read from the grant that row's own webhook wrote, which `lock_grants_of` already holds — one
source for both.

`37.5-REVIEW-FIX.md:529-532` records that CR-20's exact suggested fix was considered and declined
there, with the reason:

> Deliberately **not** taken: the review's narrow fallback ("fall back to the proof's paid expiry
> when the row says `grace_period`"). During grace the paid expiry is by definition in the past, so
> `term_ends_at <= evaluated_at` still fires and the subscriber is still refused — it does not fix
> the defect.

Confirmed against the code rather than taken on trust. `_transaction_status`
(`app_store.py:55-65`) can only answer `active`, `expired` or `revoked`, and it answers `expired`
exactly when `expires_at <= evaluated_at`. So on CR-20's own Apple trace, `term_end_for(proof)`
returns `proof.expires_at`, which is in the past during grace, and `restore.py:116` refuses on the
next line. The fix does not change the outcome of the trace it is filed for.

Three further reasons it should not be taken:

1. **It does not remove the crossing it names.** `write_subscription_grant` is still called with
   `status=status` (the canonical row's word) and `ends_at=term_ends_at` (the proof's term)
   — `restore.py:159-168`. Making `term_end_for` single-argument relocates the crossing from the
   helper to the call site; it does not close it.
2. **The residual refusal is ratified, not accidental.** `tests/unit/test_restore_proof.py:871-875`,
   `test_a_grace_row_with_no_recorded_term_is_still_refused_control`, pins CR-20's exact case with
   the reason: *"with nothing recording the window, nothing entitles anything."*
3. **Empirically it breaks the settled contract.** Applied, `tests/e2e/test_restore_subscription.py`
   fails two cases, including
   `TestTheTermTheProofCarriesDecidesWhetherThereIsAnythingToAttach::test_a_stored_grace_row_and_an_apple_proof_attaches_nothing`,
   which exists to hold this line. The change was reverted; the tree carries none of it.

**The one case CR-20 raises that CR-25 did not**, recorded for a later reader: a Play subscription
whose canonical row still reads `grace_period` while the live `subscriptionsv2.get` read reports
`SUBSCRIPTION_STATE_ACTIVE` with a future expiry, and where no grant records a term. It is refused
today. That refusal is defensible under D-06 — the row owns the status, the row's grace window is
recorded nowhere, and the webhook that will correct the row is in flight — and closing it means
deciding whether a live provider read may outrank a stale canonical row, which is a decision for a
spec, not for a code-review fix. It is not a defect in `term_end_for`.

##### Verification

Run from `/home/init/native-speaker/ns-api-gateway`, in the **main checkout** (no worktree), at
`9b28e5f`:

| gate | result | baseline at `096878c` |
|---|---|---|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1712 passed | 1684 passed |
| `pytest tests/schema -m schema` | 249 passed | 249 passed |
| `pytest tests/e2e -m e2e` | 354 passed | 354 passed |
| `ty check src` | 3 diagnostics | 3 diagnostics |

Unit is +28: every one is a new case added with a fix, none removed. No suite regressed and the `ty`
count did not rise.

### Fixer 3 — crud/, tables/, routers/, services/ (WR-35 … WR-38, WR-50, WR-51)

**Source review:** `.planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md`
**Subset:** WR-35, WR-36, WR-37, WR-38 (reviewer 3), WR-50, WR-51 (reviewer 4)

**Summary:**
- Findings in scope: 6
- Fixed: 5 (one of them partially — WR-35, see its entry)
- Skipped: 1

Every commit was made directly on `gsd/v2.0-authentication-entitlements` in the main
checkout, with no worktree, as the run instructions require.

##### Fixed Issues

###### WR-38: `activate_anonymous_device_grant` discards a missing usage row

**Files modified:** `src/nativespeaker/api/crud/grants.py`
**Commit:** `675bee0`

**Applied fix:** The lock loop kept the return value and raised `MissingUsageRowError(grant.id)`
for a `None`. The finding is correct and unqualified: `SubscriptionsDB.lock_grants_of`
(`crud/subscriptions.py:93-96`), the registered sibling (`crud/grants.py:270-274`),
`services/sync.py` and `services/quota.py` all raise on the same state, and SHARED-INVARIANTS
§ "Grants and evaluation time" says "A missing usage row for an existing grant fails closed —
never lazily minted." This was the only grant-locking site that dropped it.

Nothing is minted and no lock order changed — the raise happens at the same point the read
already happened, so the fixed order (grants ascending, then usage) is untouched.

###### WR-37: `write_subscription_grant` takes the last carried usage row instead of failing closed

**Files modified:** `src/nativespeaker/api/crud/subscriptions.py`
**Commit:** `d5fb2ce`

**Applied fix:** The carry loop now filters this account's superseded rows into `mine` first and
raises `MultipleEffectiveGrantsError(len(mine), user_id)` when there is more than one, instead of
overwriting `carried` and silently keeping the last row by grant id. Verified the loop is only
reached on the `entitled` arm (the `if not entitled: return` above it), so `superseded` is always
the `user_id`-or-`subscription_id` list the finding describes.

The reviewer's suggested code was adopted as written, because it is the tripwire the three sibling
sites already use (`crud/grants.py:172-174`, `:236-239`, `services/quota.py`) and because
SHARED-INVARIANTS § "Grants and evaluation time" forbids the alternative outright: "More than one
`status='active'` grant is an internal integrity failure: log and fail closed — no tie-break."
Last-wins was a tie-break, and it was the fail-open one: a lower `monthly_used` erased a higher one.

The new failure mode on a store webhook is a 500, which the store retries — the same shape the
`MissingUsageRowError` raise three lines below already had on this path.

###### WR-50: The DeviceCheck bit-write swallow is narrower than the fail-open contract it states

**Files modified:** `src/nativespeaker/api/services/auth.py`
**Commit:** `5fe1cf4`

**Applied fix:** Both swallows (`:230-235` anonymous, `:293-298` registered) widened from
`except AppError` to `except Exception`, keeping the closed-set `failure=type(failure).__name__`
label and adding a comment naming why the total catch is the correct one.

The finding's trace holds against the current code: `write_bits_with_retry` only retries
`RetryableDeviceCheckError`, `AppleDeviceCheck._post` only converts `httpx.HTTPError` into that
marker, and `_service_jwt`'s `jwt.encode` failures are neither. `except Exception` is the idiom
`_consume_quietly` in the same module already uses for the same reason. `CancelledError` derives
from `BaseException`, so cancellation still propagates.

###### WR-51: `QuotaService.charge` logs the three integrity failures twice

**Files modified:** `src/nativespeaker/api/services/quota.py`
**Commit:** `9c36717`

**Applied fix:** Deleted the three `logger.error("quota_integrity_failure", branch=...)` calls at
`:71`, `:80` and `:94`. Confirmed first that all three raised classes declare
`log_level = logging.ERROR` (`errors.py:234`, `:244`, `:255`) and that `app_error_handler` logs on
`exc.log_level is not None`, so each failure now leaves exactly one record under its own class
name — which is what SHARED-INVARIANTS § "Fail-closed defaults" requires ("A rejection leaves
exactly one structured security-log line") and what `services/sync.py` already does for the same
three classes.

The two `logger.warning("quota_rejected", ...)` lines were deliberately kept: `QuotaExceededError`
inherits `RateLimited.log_level = None`, so those explicit lines are the only record of the two
quota-rejection branches, not a duplicate. No test referenced `quota_integrity_failure`.

###### WR-35: `insert_account` reports a provider-account race as `IdentityAlreadyLinked` — PARTIAL

**Files modified:** `src/nativespeaker/api/crud/identities.py`,
`tests/unit/test_conflict_classification.py`
**Commit:** `0cced39`

**Applied fix (documentation half):** The comment at `identities.py:132` claimed "The only
uniqueness this insert can lose is `(issuer, subject)`." That is false, and the finding is right
about the schema: `ix_external_identities_provider_account` over
`(issuer, provider, provider_uid) WHERE provider_uid IS NOT NULL` (`migration:106-108`) and
`core.store_purchase_tokens`' own unique constraint are both reachable from the same flush. The
comment now states the three reachable rules, names 37.4 D-06 as what collapses them into one
answer, and records that the cost is bounded to the race path. The identical false sentence in
`TestTheInsertsUniqueViolationIsTheSubjectRace`'s docstring was corrected the same way; no
assertion was changed, added, or removed.

**Behavioural half NOT applied — forbidden by a ratified decision.** Phase 37.4 **D-06**
(`37.4-CONTEXT.md:90-101`) settles exactly the behaviour the finding wants changed:

> **D-06: The `IntegrityError` arm collapses.** ... The cause-chain walk for `constraint_name` and
> its three-way mapping collapse: **any `IntegrityError` from the insert becomes one already-linked
> exception.** Two consequences the developer accepted when choosing this:
> - `ProviderAccountAlreadyLinked` stops answering its own 403 `operation_not_allowed` and answers
>   the already-linked 409 instead. **Flagged conflict 4.**
> ... Only the **race** path loses the distinction.

and `37.4-06-SUMMARY.md:216` records it in the shipped behaviour table:
`| race-path provider-account conflict | 403 operation_not_allowed | 409 identity_already_linked |
D-06; only the race path loses the distinction, the pre-check keeps it |`.

**The finding's suggested fix is also wrong on its own terms**, independently of D-06:
`ProviderAccountAlreadyLinked.__init__` takes `identity_row_id: UUID` and its `log_fields` does
`str(self.identity_row_id)` (`errors.py:472-483`), so the proposed
`ProviderAccountAlreadyLinked(identity_row_id=None, ...)` is a type error that would log the string
`"None"` as a row id. Its `stored_provider=provider, live_provider=provider` also makes the class's
whole purpose — naming the disagreement — vacuous. And the `if provider_uid is not None` test it
proposes would misroute the ordinary `(issuer, subject)` race loser, which
`02-create-user.md:64` (step 12) requires to answer `identity_already_linked`.

The finding's own fallback (roll back and re-resolve on a fresh transaction) is the only shape that
could be correct, and it is precisely the savepoint-and-mapping machinery D-06 deleted.

##### Skipped Issues

###### WR-36: `activate_registered_account_grant` returns `lost_race` where no winner row exists

**File:** `src/nativespeaker/api/crud/grants.py:308-317`
**Reason:** skipped — the outcome is ratified by Phase 41 **D-13**, which names this exact index.

`41-CONTEXT.md:133-139` states:

> **D-13: The loser answers 200, as a repeat would.** For a first claim there is no grant row to
> lock, so the `FOR UPDATE` step locks nothing and the arbiter is the database: the unique indexes
> `ix_access_grants_one_free_grant_per_user_source` **and `ix_access_grants_one_active_per_user`**
> refuse the second insert. The `IntegrityError` is caught without naming a constraint or parsing a
> message ... the transaction rolls back, and the same path the repeat uses re-reads and returns.

`42-RESEARCH.md:99` repeats it for the registered writer: "`IntegrityError` is caught without naming
a constraint; the loser re-reads and answers 200." The decision explicitly enumerates
`ix_access_grants_one_active_per_user` — the very index the finding says needs a different answer —
so splitting the outcome by which slot was lost is the thing D-06/D-13 refused, not an unconsidered
gap. Adding a fourth `ActivationOutcome` member resolved by `_settle` after its rollback is a
redesign of the crud contract against a ratified one.

**The residual harm was also traced and is close to nil.** The window the finding needs requires the
rival's insert to commit while this writer holds its locks. If the caller held any effective or
marked-active grant, this writer locked those rows `FOR UPDATE`, and `write_subscription_grant`'s
own `lock_grants_of` blocks on them — the rival cannot commit. So the window exists only when the
caller holds nothing at lock time, and then the re-read after rollback returns the rival's
subscription grant, which is a real, current, strictly better entitlement than the free registered
grant that was asked for. The free slot is not spent (nothing was written), and a retry takes the
preflight's `OtherActiveGrantHeld` arm and earns its 403. D-10 already requires the loser's body to
be the current entitlement, and it is truthful here.

The `lost_race` docstring (`grants.py:84`, "Another writer holds the slot, and the caller re-reads
the winner's row") is accurate in this case too — the rival is the winner of the one-active slot and
its row is what the re-read returns — so no documentation correction is owed either.

##### Verification

All five gates were run from `/home/init/native-speaker/ns-api-gateway` in the **main checkout**
(no worktree), at commit `0cced39`, against the live PostgreSQL on `localhost:5432`:

| Gate | Result | Baseline at `9b28e5f` |
|---|---|---|
| `.venv/bin/ruff check src tests` | All checks passed | clean |
| `.venv/bin/pytest tests/unit -q -p no:cacheprovider` | 1712 passed | 1712 passed |
| `.venv/bin/pytest tests/schema -q -p no:cacheprovider -m schema` | 249 passed | 249 passed |
| `.venv/bin/pytest tests/e2e -q -p no:cacheprovider -m e2e` | 354 passed | 354 passed |
| `.venv/bin/ty check src` | Found 3 diagnostics | 3 diagnostics |

No regression was introduced and none was inherited. One transient failure was caused and repaired
during the run: the WR-35 test docstring first landed at four lines and
`tests/unit/test_docstring_bar.py` measured `tests/unit` at 1 against its recorded baseline of 0;
the docstring was rewritten to three lines and the ratchet returned to 0.

### Fixer 4 — tests/unit (CR-90, WR-70 … WR-72, WR-91 … WR-94)

**Source review:** `.planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md`
**Subset:** CR-90, WR-70, WR-71, WR-72, WR-91, WR-92, WR-93, WR-94 — the tests/unit
findings from reviewers 5 and 6.

**Summary:**
- Findings in scope: 8
- Fixed: 8
- Skipped: 0

Every fix was proved the same way: mutate the source the guard names, show the guard
fails, revert, show it passes. No test was weakened. One finding's stated mechanism did
not reproduce and the correction is recorded under CR-90.

##### Verification

Run in the main checkout at `/home/init/native-speaker/ns-api-gateway`, on branch
`gsd/v2.0-authentication-entitlements`. No worktree was created (`use_worktrees` treated as
false per the repository-shape instruction: this is a submodule whose `.git` is a file).
The numbers below are therefore reproducible from the tree as it stands.

| Gate | Baseline (0cced39) | After |
|------|--------------------|-------|
| `ruff check src tests` | clean | clean |
| `pytest tests/unit` | 1712 passed | 1743 passed |
| `pytest tests/schema -m schema` | 249 passed | 249 passed |
| `pytest tests/e2e -m e2e` | 354 passed | 354 passed |
| `ty check src` | 3 diagnostics | 3 diagnostics |

The 31 added unit cases are the new controls and parametrisations listed below. No source
file under `src/` was changed by this fixer: every finding in this subset is a test defect.

##### Fixed Issues

###### CR-90: the reset fixture restores only the root logger

**File:** `tests/unit/test_logging.py`
**Commit:** `22930a6`

**Correction to the finding.** The headline claim — that the quieted-library assertions
"cannot fail" — does **not** reproduce. Deleting the guard in `logs.py` (replacing the
`setLevel(logging.WARNING)` loop body with `pass`) fails 11 cases when the file is run
whole, and 10 when only the two affected classes are run:

```
FAILED ...::TestRaisingTheLevelNeverOpensAContentChannel::test_a_quieted_library_stays_quiet_at_debug[google.auth]
FAILED ...::TestOnlyOneAccessLineIsWrittenPerRequest::test_uvicorn_writes_no_access_line_at_the_configured_level
FAILED ...::TestOnlyOneAccessLineIsWrittenPerRequest::test_it_stays_silent_when_an_operator_raises_the_level_to_debug
11 failed, 24 passed
```

The review's tautology proof called `setup_logging(log_level="INFO")` *before* emptying
`_QUIETED_LIBRARIES`, so its own first call did the quieting. That is not the shape of any
regression: a real deletion removes the quieting from every call, and the levels then fall
back to the root's DEBUG and the assertions fire. So the content-leak guard is not inert,
and this is not a blocker.

**The defect the finding does name is real:** the fixture restores the root's handlers and
level but not the nine named-logger levels `setup_logging` writes, so those nine stay at
WARNING for every later test in the session. Measured with a probe appended to the same run:

```
LEAKED: {'httpx': 30, 'httpcore': 30, 'sqlalchemy.engine': 30, 'openai': 30,
 'langchain': 30, 'langchain_core': 30, 'urllib3': 30, 'google.auth': 30,
 'uvicorn.access': 30}
```

**Applied fix:** snapshot the nine levels alongside the root's and put them back after the
yield. Added `test_no_quieted_library_level_outlives_the_test_that_set_it`, which reads what
the cases above left behind, so the leak is caught inside the file that causes it rather
than by a later, unrelated test.

**Mutation proof:** with the restore loop removed, the new case fails
(`1 failed, 35 passed`); with it in place, `36 passed`.

###### WR-70: the App Store `.env.example` case was a bare default construction

**File:** `tests/unit/test_config.py`
**Commit:** `dfe7cef`

**Confirmed:** all three `APP_STORE_*` assignments ship commented, `_uncommented` drops
them, and the comprehension yielded `{}` — measured against the tracked file. The case was
`isinstance(AppStoreConfig(), AppStoreConfig)`.

**Applied fix, with one correction.** The review's second option is the right one and
matches what `.env.example` itself promises ("They ship commented out, with values that
parse if you uncomment them"), so `_uncommented` became `_assignments`, which reads every
assignment commented or not. A regex on the key shape keeps the prose lines that also carry
an `=` (`.env.example:41,155,156`) out of the result.

The review's suggested assertion is **not sufficient**, and I did not stop there. Both
`AppStoreConfig` validators degrade an unusable value to `None` rather than raising, so
`isinstance(AppStoreConfig(**fields), AppStoreConfig)` stays green for exactly the
placeholders CR-04 is about — verified: shipping `APP_STORE_APP_APPLE_ID=<your-apple-id>`
passed with the review's version of the fix. The case now asserts the parsed values, which
is the property the file promises. The control was rewritten to name the prefix under test.

**Mutation proof:** three regressions to `.env.example`, each caught, each reverted.

| Mutation | Result |
|---|---|
| `APP_STORE_APP_APPLE_ID=<your-apple-id>` | `test_the_app_store_lines_it_ships_are_constructible` FAILED |
| `APP_STORE_ENVIRONMENT=Xcode` | same case FAILED |
| the block renamed out of the prefix | the control case FAILED |

###### WR-71: `TestNoProviderDependency` claimed package-wide coverage

**File:** `tests/unit/test_adapter_interfaces.py`
**Commits:** `155fed8`, `597d370`

**Confirmed** in a fresh interpreter: importing `adapters` loads
`['nativespeaker.api.auth', 'nativespeaker.api.auth.adapters']` and nothing else, because
`auth/__init__.py` exposes nothing. Only `auth/firebase.py` imports `firebase_admin`.

**Applied fix:** the module set is read off the package directory rather than listed, so a
module added later is covered without editing this file — that is stronger than the
review's hand-written tuple, which also omitted `app_store`. `firebase` is the one
exclusion. Two controls were added: one pinning the set to the directory contents, one
asserting `firebase` really does hold the SDK, so the exclusion cannot quietly start hiding
a module the class should walk.

**Mutation proof:** a `import firebase_admin` line added to each of the five other modules
in turn, each caught by its own parametrisation, each reverted.

```
FAILED ...test_importing_the_module_does_not_import_firebase_admin[devicecheck]
FAILED ...test_importing_the_module_does_not_import_firebase_admin[google_play]
FAILED ...test_importing_the_module_does_not_import_firebase_admin[store_notifications]
FAILED ...test_importing_the_module_does_not_import_firebase_admin[jwt_verifier]
FAILED ...test_importing_the_module_does_not_import_firebase_admin[app_store]
```

###### WR-72: no unit case asserted that a successful create-user spends its challenge

**File:** `tests/unit/test_create_user_precedence.py`
**Commits:** `e09fc9b`, `98991be`

**Confirmed:** `consume_calls` appears only in `test_claim_precedence_registered.py` and the
conftest fake; the create-user success case asserted neither it nor `row.consumed_at`.

**Applied fix:** the three assertions the rejection arms already make, added to the success
case. A replay-after-success case was added alongside.

**Mutation proof:** removing the `_consume_and_commit` call from the success path of
`services/auth.py::_complete` fails
`test_one_recognized_entry_with_a_uid_reaches_the_consuming_transaction`.

**Recorded honestly:** the replay case did *not* fail under that single mutation, because
the claim gate refuses the replay independently. It fails only once both spend mechanisms
are gone (verified by mutating the claim gate as well), so its docstring now says it pins
the outcome rather than either mechanism. The case above is what pins the spend itself.

###### WR-91: the lost-race record is asserted nowhere

**Files:** `tests/unit/test_restore_proof.py`, `tests/unit/test_subscription_attribution.py`
**Commit:** `2da120a`

**Confirmed:** deleting both `logger.warning` calls left `119 passed`. `InternalError`
carries no `log_level`, so the 500 is otherwise completely silent to an operator.

**Applied fix:** a `race_warnings` monkeypatch spy per file — the pattern already used by
`test_google_play_notifications.py::play_logs`, chosen over `capture_logs` for the same
stated reason (the module logger caches its binding at import). Each class now asserts the
one record and its single closed-set label. A "wins, so reports no race" control was added
to each, so a line written unconditionally cannot pass instead.

The label is `{"provider": "apple"}`: `PurchaseProvider` renders as its value, not
`PurchaseProvider.apple` as the review guessed.

**Mutation proof:** both records deleted →

```
FAILED tests/unit/test_restore_proof.py::...::test_a_violation_at_commit_is_the_lost_race_the_flushes_report
FAILED tests/unit/test_subscription_attribution.py::...::test_a_violation_at_commit_is_the_lost_race_the_flushes_report
2 failed, 119 passed
```

###### WR-92: the Pub/Sub "bound off by one" control never went near the bound

**File:** `tests/unit/test_models.py`
**Commit:** `0faa2f3`

**Confirmed:** the payload was about eighty bytes against a 16384 bound, so
`len(payload) <= PUBSUB_DATA_LIMIT` was trivially true.

**Applied fix:** the envelope is padded so the base64 text lands on exactly
`PUBSUB_DATA_LIMIT`, and the assertion is equality. That is the one length a `>` and a `>=`
disagree about.

**Mutation proof:** `google_play.py:140` changed from `>` to `>=` →
`test_a_body_at_the_bound_still_reaches_the_decoder` FAILED. Reverted, `60 passed`.

###### WR-93: the single-writer walk matched one spelling

**File:** `tests/unit/test_grant_sources.py`
**Commits:** `ae1f7ef`, `e62ff48`

**Confirmed:** all five spellings the review lists escape the walk, reproduced against the
file's own helpers.

**Applied fix, in the shape the review proposes:** `_is_access_grant` now accepts the
qualified `tables.AccessGrant`; `_tree_and_aliases` resolves an aliased enum import so
`AccessGrantSource as S` is the same enum; `_undecidable_sites` reports the three shapes the
walk cannot rule on (`**fields`, an indirection in `source=`, and `getattr` on the enum)
rather than passing over them as absent. `src/` is clean of all three today. Two control
classes were added: one proving the detector fires and does not fire on a plain
construction, one proving the two newly decidable spellings are counted while an unrelated
alias still is not.

**Mutation proof:** a second subscription-grant writer appended to `services/restore.py` —
the specific future writer `:214` names — in each of five spellings, each caught, each
reverted.

| Spelling | Caught by |
|---|---|
| `AccessGrant(**fields)` | `test_no_module_builds_a_grant_this_file_cannot_rule_on` |
| `AccessGrant(source=SOURCE)` | same |
| `getattr(AccessGrantSource, "subscription")` | same |
| `tables.AccessGrant(source=AccessGrantSource.subscription)` | `test_the_whole_tree_holds_exactly_one_construction_site` |
| `from ... import AccessGrantSource as S; AccessGrant(source=S.subscription)` | same |

###### WR-94: the sync clock walk matched one spelling of a clock read

**File:** `tests/unit/test_sync_clock_capture.py`
**Commit:** `0a6bb2e`

**Confirmed:** five of the six spellings measured returned zero clock calls.

**Applied fix:** `CLOCK_CALLS` became `CLOCK_MEMBERS`, covering the monotonic sources as
well as the wall clock; `_clock_aliases` resolves both `import time as t` and
`from datetime import datetime as dt`; the walk reads `datetime.datetime.now` as well as
`datetime.now`. `_clock_calls` became `_clock_reads` and now counts *references*, not
calls, which is what closes the `now = datetime.now` indirection the review lists — a
reference is the same second read, deferred by one line.

`fromtimestamp` was deliberately **not** included, against the review's suggested set: it
converts a supplied value and reads no clock, so counting it would be a false positive.

Nine escaping spellings and three near misses were added to
`TestTheClockWalkIsNotVacuous`, so the widening is measured rather than asserted.

**Mutation proof:** a second clock read added to `services/sync.py` in four spellings and to
`app/dependencies.py` in one, each caught, each reverted.

| Second read | Caught by |
|---|---|
| `time.monotonic()` | `test_sync_service_makes_no_clock_call_on_any_path` |
| `import datetime as dt; dt.datetime.now()` | same |
| `from datetime import datetime as _dt; _dt.now()` | same |
| `datetime.datetime.now(UTC)` | same, plus the annotation-only case |
| `time.perf_counter()` in `dependencies.py` | `test_the_walk_finds_the_clock_call_dependencies_genuinely_makes` |

##### Note on the extra commits

Three follow-up commits (`597d370`, `98991be`, `e62ff48`) shorten docstrings this fixer
wrote past the three-line bar that `tests/unit/test_docstring_bar.py` enforces. Each is
labelled with the finding whose file it corrects. The bar is a project rule measured by a
test, and the full unit run caught the breach before this report was written.

### Fixer 5 — tests/e2e and tests/schema (WR-110 … WR-114)

**Source review:** `.planning/phases/40-post-auth-upgrade-anonymous/40-REVIEW.md`
**Subset:** WR-110, WR-111, WR-112, WR-113, WR-114 only. Every other finding was ignored.
**Working tree:** the main checkout at `/home/init/native-speaker/ns-api-gateway`, branch
`gsd/v2.0-authentication-entitlements`. No worktree was created (per the run's worktree override).

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

Every fix carries a mutation proof: the source the guard names was broken, the guard was shown to
go red, the source was restored, and the guard was shown to go green again. All proofs were run in
the main checkout against the live PostgreSQL on `localhost:5432`.

##### Fixed Issues

###### WR-110: `anonymous_firebase_credential` leaks a permanent Firebase user

**Files modified:** `tests/e2e/conftest.py`
**Commit:** `58ed4e1`

**Applied fix:** `firebase_admin.get_app(name=f"issuer:{...}")` now runs *before* the `signUp` call,
as `google_linked_firebase_credential` already does. Nothing between the user starting to exist and
the `try` that deletes it can raise. The comment states why the guard above it does not cover this
(`_admin_credential_configured()` asks whether a credential is findable, not whether an app carries
that name).

**Proof.** `get_app` cannot be made to raise against the live project, so the fixture body was
driven off-network with the four Firebase seams faked (`/tmp/wr110_proof.py`): `get_app` raises
`ValueError`, `signUp` returns a user, `delete_user` records. Pre-fix and post-fix, same script:

```
pre-fix  (git stash): get_app raised: no app named issuer:...  users created: ['uid-1'] users deleted: []  LEAKED
post-fix:             get_app raised: no app named issuer:...  users created: []        users deleted: []  NO LEAK
```

**Note on the remaining window.** `resp.json()` and `data["localId"]` still run outside the `try`.
That is not fixable: the delete needs `local_id`, so a response that does not carry one leaves
nothing to delete. The Google twin has the same shape for the same reason.

###### WR-111: the Apple restore fake drops `evaluated_at`

**Files modified:** `tests/e2e/conftest.py`, `tests/e2e/test_restore_subscription.py`
**Commit:** `efe43bb`

**Applied fix:** `FakeAppStoreNotifications.verify_transaction` records the pair
`(signed_transaction, evaluated_at)`. A new `pinned_evaluation_instant` fixture overrides
`get_evaluated_at` with a fixed instant for the request, and both store happy paths now assert the
recorded pair against it — Apple's `restore_calls == [(RESTORE_PROOF, pinned)]`, Play's
`[(call["purchase_token"], call["evaluated_at"])] == [(purchase_token, pinned)]`.

**Correction to the review's suggested fix.** The review said to "compare the recorded instant to
the one the response reports". The restore response reports no instant (`entitlement.type`,
`.status`, `.tier_id`, `identity_provider`), so that comparison cannot be written. Pinning the
request's captured instant through `dependency_overrides` — the spelling the unit suite already
uses — is what makes a second clock read observable, and it is exact rather than a `>= before`
bound.

**Proof.** `services/restore.py:_verify` mutated so both seams are called with `datetime.now(UTC)`
instead of `self.evaluated_at`:

```
2 failed, 33 passed
  TestTheSameAccountAppleRestore::test_a_verified_proof_attaches_the_paid_grant_and_the_body_reports_it
  TestTheSameAccountGooglePlayRestore::test_a_live_purchase_token_attaches_the_paid_grant_and_the_body_reports_it
```

Reverted: `35 passed`. Before this fix both mutations were invisible.

###### WR-112: `APPLE_REJECTION_STAGES` is one code path repeated three times

**Files modified:** `tests/e2e/test_restore_subscription.py`
**Commit:** `8a12627`

**Applied fix:** took the review's first option — assert the distinguishing detail. The four arms
carry one status and one body by design, and `stage` reaches only the log, so the test now asserts
the record each arm leaves:

```python
assert [(event, fields["stage"]) for event, fields in refusal_records.entries] == [
    *(("proof_rejected", stage) for stage in APPLE_REJECTION_STAGES),
    ("proof_rejected", PLAY_REJECTION_STAGE)]
```

`PLAY_REJECTION_STAGE` is the seam's own `RESTORE_TOKEN_GONE_STAGE`, imported rather than restated,
so the fourth cause is pinned to the classifier that produces it. The `refusal_records` fixture is
new in this file and is built on the `spy_on` helper WR-113 lifted into `tests/e2e/conftest.py`.

**Correction to the review's suggested fix.** Its snippet asserts only the three Apple stages and
uses a `refusal_records` fixture that does not exist in this module. Asserting only the Apple arms
would have left the Google arm — the one cause reached through real production code — unmeasured,
so the Play stage is included.

**Proof.** Two mutations, because the Apple seam is scripted by the test itself and the real
regression this guard names is the loss of the operator's only record:

1. `errors.py::ProviderLookupError.log_fields` returning `{}` instead of `{"stage": self.stage}` →
   `1 failed` (`test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`).
2. `google_play.read_for_restore` raising `ProofRejected(stage="VERIFICATION_FAILURE")` on the gone
   token — the Play arm impersonating an Apple one → `1 failed`, same case.

Reverted after each: `35 passed`. The pre-fix test passed under both.

###### WR-113: ~96 lines duplicated verbatim between the two webhook e2e files

**Files modified:** `tests/e2e/refusal_sites.py` (new), `tests/e2e/conftest.py`,
`tests/e2e/test_app_store_webhook.py`, `tests/e2e/test_google_play_webhook.py`,
`tests/e2e/test_sign_out_all.py`
**Commits:** `9d1f5cf`, `b575c84` (docstring bar)

**Applied fix:** the AST scan and its control constant moved to `tests/e2e/refusal_sites.py` —
`REFUSAL_FILES`, `COMPUTED`, `refusal_calls`, `files_raising_the_refusal`, and
`raised_refusal_stages(sources)`, which takes each route's own `_REFUSAL_SOURCES` as its parameter
because that is the part that genuinely differs. `LogSpy` and `spy_on` moved to
`tests/e2e/conftest.py`; each module keeps its own fixtures, because which loggers and which levels
a route spies on is what differs between them and the spy never was. Net: 174 lines removed, 115
added, and one `REFUSAL_FILES` where there were two.

**Scope note.** The third verbatim copy of the spy, in `tests/e2e/test_sign_out_all.py`, is
deduplicated in the same commit; the finding names it. The `_RecordedLogs` variant in
`tests/schema/test_subscription_ingestion.py` was left alone: it is another suite with its own
conftest, and sharing across the two would need a `tests/`-level module that nothing else wants.

**Proof of the single control.** A fourth raise site was added to the package
(`services/restore.py` gaining `raise NotificationRejected(stage="probe")`):

```
2 failed  test_app_store_webhook.py::...::test_no_raise_site_lives_where_neither_route_control_reads_it
          test_google_play_webhook.py::...::test_no_raise_site_lives_where_neither_route_control_reads_it
```

Adding `"services/restore.py"` to the **one** `REFUSAL_FILES` then turned both green (`2 passed`) —
which is the property the fix buys: pre-fix the same repair had to be made in two files, and doing
it in one left the other route red for a reason that no longer described the code. Both mutations
reverted.

###### WR-114: the anonymous claim's platform-pinning refusal has no test

**Files modified:** `tests/schema/test_grant_locks.py`
**Commit:** `08feffb`

**Applied fix:** `TestTheAnonymousWriterNamesWhyItRefused` gains
`test_material_from_the_other_platform_is_refused_once_the_pin_is_set`: the account activates from
iOS, then a claim carrying `android_play_integrity` is refused, the one grant row is unchanged, and
the pin still reads `ios_devicecheck`.

**Correction to the review's suggested fix.** Its snippet constructs `GrantsDB(account.session)`
inline and restates the writer's five keyword arguments, which is the drift the `_Account` helper
exists to prevent. Instead `_Account.activate_anonymous` gained a defaulted `claim_platform`
parameter, so every existing case is unchanged and the new one differs only in the argument under
test. A `_Account.claim_platform()` read-back was added so "never restamps the identity row" — the
half of the docstring the review's snippet asserted nothing about — is measured.

**Proof.** The guard at `crud/grants.py:170-175` deleted:

```
E   AssertionError: assert <ActivationOutcome.lost_race: 'lost_race'> is <ActivationOutcome.refused: 'refused'>
1 failed
```

which is exactly the failure the case docstring predicts. Restored: `32 passed`.

##### Skipped Issues

None. All five findings held on inspection.

##### Verification

Run from `/home/init/native-speaker/ns-api-gateway` in the **main checkout** (no worktree), against
the live PostgreSQL on `localhost:5432`, at commit `b575c84`:

| Gate | Baseline (`e62ff48`) | Result |
|---|---|---|
| `ruff check src tests` | clean | **clean** |
| `pytest tests/unit` | 1743 passed | **1743 passed** |
| `pytest tests/schema -m schema` | 249 passed | **250 passed** (+1: the WR-114 case) |
| `pytest tests/e2e -m e2e` | 354 passed | **354 passed** |
| `ty check src` | 3 diagnostics | **3 diagnostics** |

One regression was caused and repaired before finishing: `tests/unit/test_docstring_bar.py`
recorded a zero baseline for over-three-line docstrings under `tests/e2e` and `tests/schema`, and
the new module docstring in `refusal_sites.py` and the new case docstring in `test_grant_locks.py`
each ran to four lines. Both were shortened to three; the WR-114 shortening was amended into
`08feffb`, the WR-113 one is `b575c84`.

---

_Fixed: 2026-09-09_
_Fixer: Claude (gsd-code-fixer) x5, sequential, merged by the code-review orchestrator_
_Iteration: 1_
