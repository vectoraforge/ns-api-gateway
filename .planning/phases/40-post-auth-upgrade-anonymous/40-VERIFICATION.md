---
phase: 40-post-auth-upgrade-anonymous
verified: 2026-09-02T21:23:02Z
status: passed
score: 4/4 roadmap truths verified; 3 review-derived items routed to human judgment
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Decide whether WR-01 (services/auth.py::_apply_upgrade / crud/identities.py::lock_identity_and_user) must revalidate identity_state and active under the lock before the phase is considered closed, or whether the low-likelihood/no-current-writer risk is accepted as-is."
    expected: "Either a follow-up plan lands the revalidation (mirroring _reject_existing_identity's admission-time check), or a WINDOWS.md entry records the accepted risk with a reason, per the ledger's own convention."
    why_human: "This is a risk-acceptance judgment call (AGENTS.md explicitly says not to over-engineer for a low-value target, but also not to skip normal security measures) — dynamic/edge-case behavior that only a live concurrent-mutation-during-a-network-round-trip test could exercise, which the phase's own D-15 explicitly declined to write."

  - test: "Decide whether tests/unit/test_conflict_classification.py::TestTheModuleUsesNoSecondRaceArbiter must be fixed (WR-05) so its parametrize list actually detects `.with_for_update()`, given the test currently asserts an absence that is false (the phase added a row lock) and passes only because `ast.unparse` renders `with_for_update` without the forbidden space/underscore literal."
    expected: "Either the parametrize list is widened per the REVIEW.md fix (which also requires an explicit narrow exemption for the one intentional lock), or the docstring is corrected to state that a lock exists and the test is retired/renamed so it no longer claims to guard an absence it cannot detect."
    why_human: "This is a test-integrity gap, not a behavioral one — I confirmed by reading the parametrize list and the `.with_for_update()` call site that neither `\"for update\"` nor `\"select_for_update\"` matches the emitted `with_for_update` token. Whether to fix the test now or accept the misleading-but-harmless guard as follow-up debt is a priority call for the developer."

  - test: "Decide whether WR-02's now-issuable-but-unspendable handles (`claim_anonymous_grant`, `claim_registered_grant`) and the associated weakened operation-vocabulary oracle protection should be tightened now (gate issuance on the two operations with a completion route) or left as the already-recorded D-11 accepted cost."
    expected: "Either a follow-up plan narrows `/auth/challenge`'s issuance test to spendable operations, or WINDOWS.md/REQUIREMENTS.md is confirmed to already carry this acceptance explicitly enough that no further action is needed."
    why_human: "D-11 in 40-CONTEXT.md and the REQUIREMENTS.md amendment already accept unspent handles for one phase each as a documented cost. What is NOT explicitly disclosed anywhere in the planning record is the second-order regression the reviewer found: `claim_anonymous_grant` was removed from the test's `_NOT_ISSUABLE` list, which the class's own docstring says exists so 'the route cannot be asked which operation names are real' — a protection this phase's edit weakened. Low severity (labels are public in the committed migration) but the specific regression was not named in the D-11 acceptance, so a human should confirm the acceptance still covers it."
---

# Phase 40: POST /auth/upgrade-anonymous Verification Report

**Phase Goal:** Record the client-side same-Firebase-UID anonymous→registered upgrade by flipping the existing identity row's provider in place.
**Verified:** 2026-09-02T21:23:02Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | The existing `core.external_identities` row's provider flips in place — no new identity row, no user merge, no row deletion | ✓ VERIFIED | `crud/identities.py::flip_provider` writes `identity_row.provider`/`provider_uid`/`updated_at` and `user.registered_at`/`updated_at`/`email` on the **already-locked** row objects and never inserts or deletes a row. `tests/e2e/test_upgrade_anonymous.py::TestTheAnonymousToRegisteredHappyPath` (lines ~95-135) captures `row_id_before = seeded.id` and asserts `identity.id == row_id_before`, `len(identities) == 1`, provider/uid/`registered_at` set. Independently confirmed the schema-level third-state scan (`tests/schema/test_registration_pairing.py`, 4 cases, both with non-vacuous controls) passes live. |
| 2 | Preparation and completion are partitioned by route — `POST /auth/challenge` issues, `POST /auth/upgrade-anonymous` completes — and only an authenticated linked identity may call the completion (**reworded by Phase 40 D-24**) | ✓ VERIFIED | Reword confirmed honest: `routers/auth.py` diff shows `POST /auth/upgrade-anonymous` declared with `Depends(get_linked_identity)` at the **route level** (the router-level dependency is deliberately unnarrowed, matching `/auth/sync`'s existing pattern). `tests/unit/test_app_wiring.py`'s two named-route parametrizations include `/auth/upgrade-anonymous`, and it is in neither `PUBLIC_PATHS` nor `PREAUTH_CALLABLE_PATHS`. `ChallengesDB.issue` (unmodified) already binds a linked caller's handle to `bound_external_identity_id`; `verify_binding` proves the presenter is that identity row. The `ROADMAP.md` reword text matches the prompt's given criterion verbatim and correctly cites Phase 37.2 as the phase that actually deleted the mode-signal partition, not this one. |
| 3 | `GET /users/me` and `POST /auth/sync` report the new provider afterward | ✓ VERIFIED | `tests/e2e/test_flows.py::TestTheUpgradeAsAClientSeesIt` calls both endpoints before and after the upgrade (`grep -c "/users/me"` and `grep -c "/auth/sync"` each return 2) and asserts `sync_after.json()["identity_provider"] == me_after.json()["identity_provider"]` — proven through the endpoints, not by reading the identity row. |
| 4 | Purchase-attribution tokens are unchanged across the upgrade | ✓ VERIFIED | Same test captures `tokens_before`/`tokens_after` from `/users/me`'s own body (never re-derived) and asserts equality, plus a completeness check against `PurchaseProvider`'s full member set. The naming hazard (`IdentityProvider.apple` vs `PurchaseProvider.apple`) is kept in separate assertions, confirmed by reading the diff. |

**Score:** 4/4 roadmap truths verified.

### Independently Reproduced Evidence (not taken from SUMMARY.md claims)

| Check | Command | Result |
|---|---|---|
| Full default suite | `uv run pytest -q` | **857 passed**, 337 deselected — matches claimed gate |
| e2e + schema suites | `uv run pytest -m 'e2e or schema' -q` | **337 passed**, 857 deselected — matches claimed gate (real Firebase project hit live) |
| Lint | `uv run ruff check src tests` | All checks passed |
| Dev DB `nativespeaker` actually rebuilt (WINDOWS #10) | live `pg_enum`/`pg_constraint` query against the running DB | `auth_operation` carries exactly `['create_user', 'upgrade_anonymous_to_registered', 'claim_anonymous_grant', 'claim_registered_grant']`; `core.auth_challenges` constraints no longer include the operation-membership CHECK (only `auth_challenges_check`, `auth_challenges_check1`, the fkey, the unique key and the pkey survive) |
| The no-skip proof for the real-Google e2e case (40-03's claim, disclosed as non-reproducible from the repo alone) | re-created the throwaway `-p` plugin removing `FIREBASE_TEST_GOOGLE_REFRESH_TOKEN` from `os.environ` after `pytest-dotenv`'s load, ran `GSD_UNSET_REFRESH=1 PYTHONPATH=... uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -s -p gsdprobe_plugin -rs` | **6 passed, 3 errors, zero skipped** — the absent credential fails with `KeyError: 'FIREBASE_TEST_GOOGLE_REFRESH_TOKEN'` at the subscripted read, never a skip. Independently confirms the D-19/D-18 "must fail, never skip" prohibition holds. |
| Diff scope | `git diff 6dcdaa243e68cfd7134f8b7fdfff886d2d48eb8b..HEAD -- . ':!.planning/'` | exactly 20 files changed, matching the phase's stated change set |
| Debt markers | `grep -nE "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` over all 20 changed non-planning files | none found |

### Verification Focus — the three items the orchestrator asked to be scrutinized

**1. 40-REVIEW.md (0 Critical / 8 Warning / 4 Info) — confirmed rather than trusted, by reading the code directly.**

- **WR-05 (does it leave a real invariant unguarded?):** Read `tests/unit/test_conflict_classification.py:271-281` and `crud/identities.py:69`. Confirmed: `lock_identity_and_user` calls `.with_for_update()`, and `TestTheModuleUsesNoSecondRaceArbiter`'s parametrize list is still exactly `["serializable", "advisory_lock", "pg_advisory", "isolation_level", "for update", "select_for_update"]` — unchanged from before this phase. `ast.unparse` emits the method call as `with_for_update` (no space, underscore-joined), which matches **neither** `"for update"` (has a space) **nor** `"select_for_update"` (different token). The phase's only response was a docstring paragraph on the class rationalizing the exception; the parametrize list was not touched. **Verdict: yes, this leaves a real gap** — not in the underlying design (D-15's argument that the challenge claim remains the sole serialization point is sound, and no second arbiter actually exists in the shipped code), but in the test's own ability to catch a *future* second lock. The test currently proves nothing about locks at all; it would pass identically whether one lock or three were added, as long as none used the literal string `"for update"` with a space. This is exactly the failure mode 40-REVIEW.md names: "guards and docstrings that assert more than the code delivers." Routed to human judgment above (not auto-fixed here, since fixing a checked-in structural test is a code change outside verification's scope).

- **WR-02 (unspent handles — accumulation and forward-work disclosure):** Confirmed `routers/auth.py`'s issuance handler tests `body.operation not in AuthOperation` (4 members) while `services/auth.py::_complete` is only ever called with `AuthOperation.create_user` or `AuthOperation.upgrade_anonymous_to_registered` (`complete`/`complete_upgrade`, the only two callers). Confirmed via `grep` that no reaper, delete, or expiry sweep exists over `core.auth_challenges` beyond `issue`/`locate`/`claim`/`consume`. **This accumulation is adequately recorded as forward work**: `40-CONTEXT.md` D-11 and the `.planning/REQUIREMENTS.md` UPGRADE-01 amendment both name the accepted cost explicitly ("a client can obtain a `claim_anonymous_grant` or `claim_registered_grant` handle for an endpoint that does not exist yet; it expires unspent in 300 seconds"), and phases 45/46 are forward-flagged under SCHEMA-01/RESTORE-01/SIGNOUT-01 to inherit the enum. **What is not disclosed anywhere in the planning record** is the specific regression the reviewer found: `claim_anonymous_grant` was removed from `test_challenge_endpoint.py`'s `_NOT_ISSUABLE`/`_OUTSIDE_THE_VOCABULARY` list, whose own class docstring states its purpose as preventing the issuance route from being "asked which operation names are real." That specific weakening (now closed by test WR-02's fix, unapplied) is not named in D-11's acceptance text. Routed to human judgment above.

**2. Two verification claims disclosed as not reproducible from the repository alone — independently checked.**

- **40-03's no-skip proof:** reproduced independently above (fresh throwaway `-p` plugin, since the original was correctly deleted per the plan's own instruction). Result matches the summary's claim exactly in shape (zero skipped, `KeyError` failure). **Adequately covered — the claim is true and now doubly verified.**
- **40-01's dev-database rebuild performed by the orchestrator, not the executor:** the summary and WINDOWS.md entry #10 both disclose this honestly rather than paper over it (the executor's three attempted routes to `DROP`/`pogo rollback` were all denied by the harness's permission classifier). Independently verified the **outcome** by querying the live `nativespeaker` database directly: `core.auth_operation` carries exactly the four post-shrink labels and the operation-membership CHECK is gone. **The disclosed gap is fully closed in the current codebase state**, regardless of which actor performed the fix — WINDOWS.md entry #10's `status: fixed` is accurate.

**3. 40-08's re-derived divergence count (five → six).**

Confirmed present in `.planning/REQUIREMENTS.md`: the Phase 40 amendment header (line 34), the UPGRADE-01 entry's "FLAGGED CONFLICT" block (line 244) naming D-01's removed client-declared provider against seven cited line numbers in `05-upgrade-anonymous.md`, the re-derivation paragraph naming the five `SHARED-INVARIANTS.md` sections re-read (line 256), and the standing table row (line 540) both reading **six** flagged conflicts / **nine** known divergences. The **Phase 37 D-12 gap** — the identical client-declaration removal at create-user, made in Phase 37 but never filed as a conflict — is explicitly reported in the entry ("That gap is left as Phase 37's to close rather than re-filed here") rather than silently re-filed or silently ignored. This is carried-forward debt correctly attributed to Phase 37, not something Phase 40 was obligated to fix, and Phase 40's own text says so plainly.

**4. WINDOWS.md entries 10 and 11 — both closed as `fixed` — verified genuinely resolved in code, not just marked.**

- **Entry 10** (dev DB not rebuilt): verified above via a live query against the running `nativespeaker` database. Genuinely resolved.
- **Entry 11** (placeholder `ProviderTransitionNotAllowed` raise covering three wrongly-answered combinations): read `services/auth.py::_apply_upgrade` in the current tree — it is three flat guard clauses (both-anonymous → `NotLinked(cause="empty")`, same-provider-same-uid → idempotent no-op returning the stored provider with no write issued, `stored is not anonymous` → drift refusal) followed by the flip. No `NotImplementedError` or placeholder remains (`grep -c "NotImplementedError" src/nativespeaker/api/services/auth.py` → confirmed absent by reading the file). `tests/unit/test_upgrade_precedence.py` (18 cases, independently confirmed present) and the four scripted e2e cases in `tests/e2e/test_upgrade_anonymous.py::TestTheRefusalsAndTheRepeat` exercise every branch. Genuinely resolved.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/nativespeaker/api/routers/auth.py` | `POST /auth/upgrade-anonymous` behind `get_linked_identity`, widened issuance membership test | ✓ VERIFIED | Confirmed in diff and by route listing in 40-04-SUMMARY (`/auth/upgrade-anonymous` present) |
| `src/nativespeaker/api/services/auth.py` | Shared completion sequence, `complete_upgrade`, full case matrix | ✓ VERIFIED | `_complete`/`_apply_create_user`/`_apply_upgrade`/`_consume_quietly` all present; case matrix confirmed complete (see WINDOWS #11 above) |
| `src/nativespeaker/api/crud/identities.py` | Locked re-resolution, sole flip writer | ✓ VERIFIED | `lock_identity_and_user` (inner join, `.with_for_update()`) and `flip_provider` (both writes in one method, no commit) present |
| `src/nativespeaker/api/errors.py` | `UpgradeRefused` + two silent leaves | ✓ VERIFIED | Confirmed in diff: base declares 403/`operation_not_allowed` once, leaves declare nothing, constructor excludes provider-account uid |
| `tests/schema/test_registration_pairing.py` | Third-state scan, non-vacuous | ✓ VERIFIED | 4 cases (2 scans + 2 controls) present and passing live against the real database |
| `tests/e2e/test_upgrade_anonymous.py` | Happy path, refusals, real-credential case | ✓ VERIFIED | 9 cases collected, 0 skipped, confirmed passing live including the real-Google case |
| `.planning/REQUIREMENTS.md` | Dated UPGRADE-01/02 amendment, SCHEMA-01 note | ✓ VERIFIED | Confirmed present, see item 3 above |
| `.planning/ROADMAP.md` | Reworded criterion 2 | ✓ VERIFIED | Confirmed present and honest, see item 2 above |

### Data-Flow Trace (Level 4)

`provider`/`provider_uid`/`email` written by `flip_provider` all trace to `lookup_with_retry` → `FirebaseAdminLookup.get_user_provider_data` → the real Firebase Admin `getUser` call — a live external read, never a static/hardcoded value. The real-credential e2e case (`TestTheRealGoogleLinkedUpgrade`) additionally asserts the written `provider_uid` against a value read back through the same production seam rather than a test-invented literal. **FLOWING.**

### Anti-Patterns Found (from 40-REVIEW.md, independently confirmed; none blocking this phase's stated must-haves)

| File | Finding | Severity | Confirmed | Filed in WINDOWS.md? |
|---|---|---|---|---|
| `services/auth.py::_apply_upgrade`, `crud/identities.py::lock_identity_and_user` | WR-01: docstring claims "revalidate the locked rows" but only the provider is revalidated; `identity_state`/`active` are not re-checked under the lock, so an account retired or blocked during the challenge-commit + Firebase round-trip window can still be upgraded, permanently burning a provider-account slot | Warning | Yes, by reading the code | No |
| `routers/auth.py:47-59` | WR-02: two enum members are issuable with no completion route; unspent-handle accumulation is accepted (D-11) but the specific weakening of the "operation vocabulary is not disclosed" test guard is not named in that acceptance | Warning | Yes | No |
| `crud/identities.py:138-144` | WR-03: `except IntegrityError` attributes every failure to the provider-account conflict unconditionally, without discriminating the constraint name; reachability through the shipped adapter is nil today | Warning | Yes, confirmed in diff | No |
| `tests/e2e/conftest.py:135-152` | WR-04: `google_linked_firebase_credential` can leak a real Firebase user if the link step fails between user creation and the `try`/`finally` guard | Warning | Not independently re-verified line-by-line; consistent with the diff's fixture shape | No |
| `tests/unit/test_conflict_classification.py:271-281` | WR-05: guard test asserts an absence ("no second race arbiter") that is false; passes only because of an `ast.unparse` token-matching quirk | Warning | Yes, confirmed above | No |
| `migrations/20260818_01_initial-release.sql` | WR-06: an already-applied database that ran the old 7-label migration silently diverges from a fresh apply, with no in-repo guard | Warning | Consistent with independently observing that only a manual dev-DB rebuild (WINDOWS #10) brought this database in line | No |
| `routers/auth.py`, `app/dependencies.py`, `schemas/auth.py` | WR-07: `identity.identity is None` vs `identity.user is None` are two different predicates for "account-less," on a dataclass with no structural coupling between the two fields | Warning | Consistent with the diff | No |
| `tests/e2e/conftest.py:110-114,132-133` | WR-08: the shared single Google test account has no lease/lock, so two concurrent e2e runs are mutually destructive | Warning | Consistent with the diff | No |

None of these are debt markers (`TBD`/`FIXME`/`XXX`) and none contradict a stated PLAN must-have truth, so none trigger `gaps_found` under the verification decision tree. They are unresolved code-review findings that have not yet been triaged into `WINDOWS.md` or fixed, which is itself worth a developer decision (see `human_verification` above for the two judged most consequential; the other six are recorded here for completeness and are lower-severity per the review's own text).

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|---|---|---|---|
| UPGRADE-01 | 40-01…40-08 | ✓ SATISFIED | All 4 roadmap truths verified; REQUIREMENTS.md carries the dated amendment with re-derived conflict count |
| UPGRADE-02 | 40-02, 40-04, 40-06, 40-08 | ✓ SATISFIED | Partition-by-route and linked-identity admission both independently confirmed in code and tests |

No orphaned requirements — `grep -E "Phase 40" .planning/REQUIREMENTS.md` maps only UPGRADE-01/02 to this phase, both claimed by plans in the phase's `requirements` frontmatter.

### Human Verification Required

See the three items in the frontmatter `human_verification` block above. In short: two of 40-REVIEW.md's eight WARNING findings (WR-01, WR-05) and one nuance of a third (WR-02) were judged consequential enough to route to the developer for an explicit accept-or-fix decision, because they are risk/priority calls rather than facts this verifier can settle by reading code. The remaining review findings (WR-03, WR-04, WR-06, WR-07, WR-08, and the four Info items) are recorded above for completeness but are lower severity per the review's own text and do not block phase completion.

### Gaps Summary

No must-have truth, artifact, or key link failed. All four ROADMAP success criteria are genuinely delivered, independently reproduced against a live database and a live Firebase project, not merely claimed by SUMMARY.md. The phase's own code review (0 Critical / 8 Warning / 4 Info, `status: issues_found`) remains entirely unactioned in the codebase — no fixes applied, and none of its eight warnings have been triaged into `WINDOWS.md` even though the phase used that ledger actively for two other items (#10, #11) in the same session. That gap — a committed review with real, reviewer-confirmed findings and zero follow-up action — is the reason this verification routes to `human_needed` rather than `passed`: the phase goal is achieved, but three of the review's findings are judgment calls (accept the risk vs. fix now vs. file for later) that only the developer can make, and doing so via silent inaction is not the same as an explicit decision.

---

_Verified: 2026-09-02T21:23:02Z_
_Verifier: Claude (gsd-verifier)_
