---
phase: 40-post-auth-upgrade-anonymous
plan: 07
subsystem: testing
tags: [e2e, schema, firebase, asyncpg, postgres, invariant, purchase-attribution]

# Dependency graph
requires:
  - phase: 40-03
    provides: "`google_linked_firebase_credential` — the per-run exchange-and-link session whose real providerData carries exactly one `google.com` entry"
  - phase: 40-04
    provides: "`POST /auth/upgrade-anonymous` end to end, and `flip_provider` as the sole writer of both halves of the pairing"
  - phase: 40-05
    provides: "the complete case matrix and the conflict-arm fix, so the endpoint answers correctly before it is proven against a real credential"
provides:
  - "`TestTheRealGoogleLinkedUpgrade` — the flip driven by a genuinely Google-linked Firebase account through the production Admin SDK, with the written `provider_uid` asserted against Google's own answer"
  - "`TestTheUpgradeAsAClientSeesIt` — ROADMAP criteria 3 and 4 proven through `/users/me` and `/auth/sync` rather than by reading the identity row both endpoints read"
  - "`tests/schema/test_registration_pairing.py` — the two third-state scans over real rows, each with a control that makes it count a deliberately offending row"
affects: [40-08, 41-claim-anonymous-grant, 42-claim-registered-grant]

# Actuals (#2632) — same estimateTokens scale (chars/4) as the plan's estimate.
actuals:
  tokens: 6485
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A count-zero scan ships with a control: insert the offending row, assert the same query counts it, roll back to a savepoint, assert zero returns — so a silently wrong query cannot pass vacuously"
    - "An expected value is read back through the same production seam the subject used, so the assertion is against the third party's answer rather than the test's own guess"
    - "A value that must not move is captured from the endpoint before the change and compared after, never re-derived — a re-derivation would still match a regenerated value"

key-files:
  created:
    - tests/schema/test_registration_pairing.py
  modified:
    - tests/e2e/test_upgrade_anonymous.py
    - tests/e2e/test_flows.py

key-decisions:
  - "The real case's expected `provider_uid` is read through `app.state.firebase_adapter.get_user_provider_data(issuer, local_id)` — the production seam the endpoint itself uses — so the Google subject is never written into the repository and the assertion is against Google's answer"
  - "The real case takes no `stub_verifier`: the linked session is a genuine Firebase ID token for the configured project, so the production verification path accepts it, and substituting a verifier would remove half of what the case proves"
  - "The flow case asserts `/auth/sync`'s provider against `/users/me`'s value rather than against a second literal, so the two endpoints are proven to agree rather than proven separately equal to a constant"
  - "The schema file writes its own `_rolled_back` savepoint helper rather than reusing `test_constraints.py`'s `_rejects`: the offending row is accepted, so there is no exception to catch and the insertion must be undone explicitly"

patterns-established:
  - "The scan-plus-control shape for any cross-table invariant no CHECK can express: two count-zero queries and two controls, in the schema suite's own scratch database"

requirements-completed: [UPGRADE-01, UPGRADE-02]

coverage:
  - id: D1
    description: "A real Firebase user carrying a genuine Google credential completes the upgrade through the real Admin SDK with nothing substituted, and the provider_uid written is the one Google actually reported"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRealGoogleLinkedUpgrade::test_a_genuinely_google_linked_user_completes_through_the_real_admin_sdk"
        status: pass
      - kind: command
        ref: "grep -cE \"pytest\\.skip|skipif|mark\\.skip\" tests/e2e/test_upgrade_anonymous.py -> 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "That case fails, never skips, when its credential is absent — it carries no marker and no presence guard, and the production lookup class is asserted"
    requirement: "UPGRADE-01"
    verification:
      - kind: command
        ref: "uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -rs -> 9 passed, zero skipped, no skip reasons reported"
        status: pass
      - kind: e2e
        ref: "tests/e2e/test_upgrade_anonymous.py#TestTheRealGoogleLinkedUpgrade — `assert isinstance(adapter, FirebaseAdminLookup)`"
        status: pass
    human_judgment: false
  - id: D3
    description: "After an upgrade, GET /users/me and POST /auth/sync both report the new provider, proven through the endpoints a client calls"
    requirement: "UPGRADE-01"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_flows.py#TestTheUpgradeAsAClientSeesIt::test_both_reads_report_the_new_provider_and_no_purchase_token_moves"
        status: pass
    human_judgment: false
  - id: D4
    description: "The purchase-attribution tokens are identical either side of the upgrade — same set of store providers, same identity value per provider"
    requirement: "UPGRADE-02"
    verification:
      - kind: e2e
        ref: "tests/e2e/test_flows.py#TestTheUpgradeAsAClientSeesIt — `tokens_after == tokens_before`, both captured from `/users/me`"
        status: pass
    human_judgment: false
  - id: D5
    description: "No row exists in the third state, and the observation is proven non-vacuous by a control per scan"
    requirement: "UPGRADE-01"
    verification:
      - kind: integration
        ref: "tests/schema/test_registration_pairing.py#TestTheRegistrationPairing (4 cases: two scans, two controls)"
        status: pass
      - kind: command
        ref: "uv run pytest -m schema -q -> 121 passed (117 before this plan)"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-09-02
status: complete
---

# Phase 40 Plan 07: The Real Credential, the Two Read Endpoints, and the Third State Summary

**The three claims the endpoint cannot make about itself, each proven in the suite that can actually make it: a live Google-linked account drives the flip through the unsubstituted Admin SDK, both read endpoints report the result to a client, and the half-upgraded row state is observed absent by scans that are proven able to see it.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-09-02
- **Tasks:** 3
- **Files:** 1 created, 2 modified

## Accomplishments

- The upgrade now has a case with **nothing substituted**: a real Firebase user carrying a genuine Google credential, verified by the production JWT verifier, read by the production `FirebaseAdminLookup`, flipped by the real endpoint against the real database. It carries no skip marker, no presence guard and no fallback.
- The written `provider_uid` is asserted against **Google's own answer**, read back through the same seam the endpoint used. No Google identifier is embedded in the repository, and a test that invented its own expected value could not have caught a provider-uid regression.
- `tests/e2e/test_flows.py` gained the D-20 flow: the upgrade is performed, then `/users/me` and `/auth/sync` are called again and asserted to report the new provider **and to agree with each other**. Criterion 3 names two endpoints, so it is proven by calling them.
- The purchase-attribution tokens are **measured** unchanged, not argued unchanged: read off `/users/me` before the flip, read off it again after, compared by equality.
- `tests/schema/test_registration_pairing.py` is new: two count-zero scans over the users/identity pairing, each shipping a control that inserts a deliberately offending row, asserts the same query counts it, rolls it back to a savepoint and asserts zero returns.

## Task Commits

1. **Task 1: The real Google-linked account completes the upgrade, nothing substituted** — `509c966`
2. **Task 2: The cross-endpoint flow — the new provider is reported, the purchase tokens are not touched** — `1bf1118`
3. **Task 3: The third-state scan over real rows** — `2e012bf`

## Task 1: the assertion the case exists for

The plan's acceptance criterion asks for the assertion line to be quoted. The expected value is read first, through the production seam:

```python
        # Read through the same seam the endpoint uses, so the uid asserted below is Google's, not the test's.
        reported = await adapter.get_user_provider_data(issuer, local_id)
```

and the row read back after the flip is compared against it:

```python
        assert identities[0].provider_uid == reported.provider_uid
```

`reported` is a `VerifiedProviderIdentity` produced by `FirebaseAdminLookup.get_user_provider_data` against the live project — the same call `_complete` makes. Nothing in the test invents, derives or hard-codes the Google subject.

### Which cases request the fake, and which does not

`grep -c "scripted_firebase_adapter" tests/e2e/test_upgrade_anonymous.py` returns **15**. Every one of those is in the earlier classes — `TestTheAnonymousToRegisteredHappyPath` and `TestTheRefusalsAndTheRepeat`, which are the four cases D-19 assigns to the fake plus the tracer. Filtered to the lines at or after `TestTheRealGoogleLinkedUpgrade` (line 270 onwards) the grep returns exactly one line, and it is a comment:

```
281:        # scripted_firebase_adapter is deliberately not requested, and this is what makes that visible.
```

The real case's signature is `(self, google_linked_client, _db_transaction, _app_lifespan, _app_config, google_linked_firebase_credential)` — the fake appears nowhere in it. The `assert isinstance(adapter, FirebaseAdminLookup)` line one statement later is what turns that absence into an assertion: if anyone later adds `scripted_firebase_adapter` to this signature, the case fails rather than silently proving nothing.

### The no-skip measurement

`uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -rs` reported **9 passed, 0 skipped** with no `SKIPPED` section at all. `grep -cE "pytest\.skip|skipif|mark\.skip" tests/e2e/test_upgrade_anonymous.py` returns `0`. Plan 40-03 already measured the absent-credential branch: with `FIREBASE_TEST_GOOGLE_REFRESH_TOKEN` removed from `os.environ` after `pytest-dotenv` loads, the run errors with `KeyError` and skips nothing. This plan adds no guard that would change that.

## Task 2: the two capture lines

The criterion asks for both capture lines to be quoted. Before the flip:

```python
        # Captured from the endpoint, never re-derived: a regenerated token would still match a re-derivation.
        tokens_before = me_before.json()["purchase_tokens"]
```

and after it:

```python
        tokens_after = me_after.json()["purchase_tokens"]
```

compared by `assert tokens_after == tokens_before`. Both come off `/users/me`'s body — a `dict[PurchaseProvider, str]`, so the equality covers the set of store providers and the identity value per provider in one comparison. A separate `assert set(tokens_after) == {provider.value for provider in PurchaseProvider}` states the completeness explicitly, because an endpoint that returned an empty dict either side would satisfy the equality alone.

### The naming hazard, kept apart

The test reads both enums and never derives one from the other:

- `IdentityProvider.google` is scripted into the fake and asserted in the two providers' bodies (`"anonymous"` before, `"google"` after).
- `PurchaseProvider` is used only for the token-key set.

They appear in different assertions on different values, and neither is computed from the other. The one comment on the token-set assertion names which enum is in play, since `apple` is a member of both.

### The two endpoints, both called

`grep -c "/users/me" tests/e2e/test_flows.py` returns `2` and `grep -c "/auth/sync" tests/e2e/test_flows.py` returns `2` — one call each side of the flip. The post-upgrade agreement is asserted as agreement, not as two literals:

```python
        assert sync_after.json()["identity_provider"] == me_after.json()["identity_provider"]
```

## Task 3: the two controls

The criterion asks for both control assertions to be quoted. First direction — a user carrying a registration timestamp whose identity row is anonymous:

```python
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=datetime.now(UTC))
            await _insert_identity(conn, user_id=user_id, provider="anonymous")
            assert await conn.fetchval(_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY) == 1
        assert await conn.fetchval(_REGISTERED_USER_ON_AN_ANONYMOUS_IDENTITY) == 0
```

Second direction — an identity row carrying a registered provider whose user has no timestamp:

```python
        async with _rolled_back(conn):
            user_id = await _insert_user(conn, registered_at=None)
            await _insert_identity(conn, user_id=user_id, provider="google")
            assert await conn.fetchval(_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER) == 1
        assert await conn.fetchval(_REGISTERED_IDENTITY_ON_AN_UNREGISTERED_USER) == 0
```

Both offending rows insert successfully — which is the point. The database accepts the third state, so the pairing rests entirely on `flip_provider` writing both halves, and these scans are what keep that honest. Without the controls the file would keep passing if either query were silently wrong.

The file imports nothing from the e2e package: `grep -n "import"` shows five lines, all of them `contextlib`, `uuid`, `datetime`, `asyncpg` and `pytest`. It uses the schema suite's own `conn` fixture — a connection to a freshly migrated scratch database inside a transaction that always rolls back — and its own `_rolled_back` savepoint helper, written rather than borrowed because `test_constraints.py::_rejects` expects an exception and there is none here.

## Files Created/Modified

- `tests/e2e/test_upgrade_anonymous.py` — the module-scoped `google_linked_client` fixture (the linked ID token, no `stub_verifier`) and `TestTheRealGoogleLinkedUpgrade` with one case. 49 insertions, 0 deletions.
- `tests/e2e/test_flows.py` — the module docstring restated for a file that now holds two flows, six imports, `UPGRADE_SUBJECT`, the `upgrade_flow_client` fixture and `TestTheUpgradeAsAClientSeesIt` with one case. 68 insertions, 1 deletion (the old one-flow module docstring line).
- `tests/schema/test_registration_pairing.py` — new. The schema marker, two module-level scan queries, two module-level insert literals, the `_rolled_back` helper, two insert helpers and `TestTheRegistrationPairing` with four cases. 85 insertions.

## Decisions Made

- **The real case reads its expected uid rather than storing it.** T-40-07-03 forbids embedding the test Google account's identifiers in the repository, and a literal would also be wrong the first time the account is rebuilt. Reading it back through `get_user_provider_data` costs one extra Admin call in one test and makes the assertion be about Google's answer.
- **The real case does not take `stub_verifier`, and the existing `anonymous_client` precedent is why.** The linked session is a genuine Firebase ID token for the configured project, so the production verifier accepts it as-is. Swapping the verifier would have made this case prove only the flip, not the whole path a real client takes.
- **The flow case uses the scripted fake, exactly as D-20 says.** It needs no hand-made Firebase account, and its subject is the two read endpoints rather than the provider read. Driving it through the real credential would have coupled ROADMAP criteria 3 and 4 to the availability of the Google refresh token for no gain.
- **`_rolled_back` is a new helper rather than a reuse.** `test_constraints.py::_rejects` wraps `pytest.raises`; here the statement succeeds, so there is nothing to catch. Same savepoint discipline, opposite expectation, four lines.
- **The scans compare `i.provider <> 'anonymous'` rather than enumerating `('google','apple')`.** The pairing is defined by the negation — a registered provider is any non-anonymous one — so an enum gaining a third registered member is covered without editing this file.

## Deviations from Plan

**None on the code.** All three `files_modified` were changed and nothing else was. No source file under `src/` was touched.

One mechanical note, not a change of substance:

- **[Rule 3 - Blocking] `.env` had to be copied into the worktree.** It is gitignored, so the parallel worktree was created without it, and neither the e2e suite nor the schema suite can reach Google, Firebase or PostgreSQL without it. Copied from the main checkout as the dispatch directed. It was never staged and never committed — `git status --short` is empty at every commit, and `.gitignore` lists it.

## Issues Encountered

None. The endpoint answered the real credential correctly on the first run, which is the outcome plans 40-04 and 40-05 earned: the case matrix and the conflict-arm fix had already been driven against a real PostgreSQL, so the only thing left for this case to discover would have been a Google `providerData` shape mismatch, and there was none.

The one operational risk the dispatch flagged — a stale Firebase link left by an interrupted prior run — did not materialise; `_release_google_account`'s preamble ran on a free account.

## Verification Results

| Gate | Result |
|---|---|
| `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py -q -rs` | **9 passed, 0 skipped**, no skip reasons (8 before this plan) |
| `uv run pytest -m e2e tests/e2e/test_flows.py -q -rs` | **2 passed, 0 skipped** — both flows collected (1 before) |
| `uv run pytest -m e2e -q` | **216 passed** (214 before) |
| `uv run pytest -m schema tests/schema/test_registration_pairing.py -q` | **4 passed** (≥ 4 required) |
| `uv run pytest -m schema -q` | **121 passed**, 1073 deselected (117 before) |
| `uv run pytest -q` | **857 passed**, 337 deselected |
| `uv run ruff check src tests` | All checks passed! |
| `uv run pytest tests/unit/test_docstring_bar.py -q` | 9 passed — all three files measure zero |
| `grep -cE "pytest\.skip\|skipif\|mark\.skip" tests/e2e/test_upgrade_anonymous.py` | `0` |
| `grep -c "scripted_firebase_adapter" tests/e2e/test_upgrade_anonymous.py` | `15`, all before the real case; one comment line after it |
| `grep -c "/users/me"` and `grep -c "/auth/sync"` in `tests/e2e/test_flows.py` | `2` and `2` |
| `grep -n "import" tests/schema/test_registration_pairing.py` | 5 lines, none from the e2e package |
| `git status --porcelain src/` | empty — no production source file touched |
| `git diff --diff-filter=D` over every commit | no deletions |

### The Firebase user this run created is gone

The module's `_google_user_deleted_after_teardown` finalizer asserts `UserNotFoundError` after the credential fixture tears down, and every e2e run above completed with no teardown error. Independently confirmed after pytest exited, by a throwaway read-only script (run outside the repository and deleted afterwards) that looked the account up by its Google provider identifier:

```
holders: 0, not_found: 1
```

No Firebase user holds the test Google account, so the next run's link will succeed without needing the recovery preamble. The refresh token was never printed and appears in no committed file.

## Known Stubs

None. No hardcoded empty collection, no placeholder text, no unwired data source, no skipped test, and every `<verify>` in the plan was run and is quoted above.

## Threat Flags

None new. The register's five entries are addressed as written:

- **T-40-07-01 (a case that quietly skips).** Measured, not asserted: zero skip markers by grep, zero skipped and no skip reasons by `-rs`, and the production-adapter assertion that turns a substituted seam into a failure.
- **T-40-07-02 (the half-upgraded row state).** Both scans observe zero and both controls prove the scans can count a deliberately offending row.
- **T-40-07-03 (the test account's identifiers).** The expected `provider_uid` is read from the live Admin response; `grep` over the three changed files finds no Google subject literal, and the refresh token was never printed.
- **T-40-07-04 (purchase attribution).** Captured before and compared after, off the endpoint's own body; the two same-valued provider enums are used in separate assertions and neither is derived from the other.
- **T-40-07-SC (package installs).** Unreachable — nothing installed, `pyproject.toml` untouched.

## User Setup Required

None.

## Next Phase Readiness

- **40-08** can record in `REQUIREMENTS.md` that criteria 3 and 4 are proven through the endpoints rather than by row reads, and that the D-12 pairing is now scanned with non-vacuous controls.
- **41 and 42** inherit the scan-plus-control shape for any further cross-table invariant, and inherit a real-credential case that will fail loudly if the Google `providerData` shape ever moves.
- **D-18's body remains stale** and should not be used as the record of what shipped; the mechanism is in `40-03-SUMMARY.md`, and this plan consumed it unchanged.

---
*Phase: 40-post-auth-upgrade-anonymous*
*Completed: 2026-09-02*

## Self-Check: PASSED

- `.planning/phases/40-post-auth-upgrade-anonymous/40-07-SUMMARY.md` — FOUND
- `tests/e2e/test_upgrade_anonymous.py`, `tests/e2e/test_flows.py`, `tests/schema/test_registration_pairing.py` — all FOUND
- Commits `509c966`, `1bf1118`, `2e012bf`, `4de83c7` — all FOUND in `git log`
- `.env` present in the worktree, gitignored, unknown to git (`git ls-files --error-unmatch .env` fails), and absent from every commit
- No production source file touched; working tree clean
