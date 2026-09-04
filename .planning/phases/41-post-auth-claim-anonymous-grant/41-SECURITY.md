---
phase: "41"
slug: "post-auth-claim-anonymous-grant"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-04"
---

# Phase 41 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client → `POST /auth/claim-anonymous-grant` | Bearer token, challenge handle and one DeviceCheck token; all untrusted until the JWT barrier, the challenge store and Apple have spoken | Bearer JWT, challenge id, device token (secret capability) |
| application → Apple DeviceCheck | The sole authority for "this device's slot is spent"; each call authenticated by a fresh ES256 service JWT | Device token, two bits, ES256 bearer |
| application → PostgreSQL | The three-row activation under the two-tier lock order, inside one transaction | Grant, usage and identity rows |
| filesystem → application | The ES256 private key, read once at boot from a path outside this repository | PEM private key |
| application → LLM provider | The outbound call the breaker, the queue and the semaphore bound (plan 41-02) | Prompt content, no request body |
| planning record → future reader | Divergences and dead obligations recorded so a later phase does not rebuild what was deleted (plan 41-05) | Decisions and counts, no secrets |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-41-01 | Spoofing | client-asserted device state | high | mitigate | `schemas/auth.py::GrantClaimRequest` carries `challenge_id` and one `device_token` only; the backend reads the bits itself via `read_bits_with_retry` on every claim (`services/auth.py:189`). Two-token bodies answer 422 (`test_claim_precedence.py::TestTheDeviceReadAndTheDeviceWriteNameOneDevice`) | closed |
| T-41-02 | Elevation of Privilege | replaying a device token to claim twice | high | mitigate | Apple's bit0 is written before activation (`services/auth.py:194`); `ix_access_grants_one_free_grant_per_user_source` and `ix_access_grants_one_active_per_user` (`migrations/20260818_01_initial-release.sql:256,261`) refuse the second insert. Live race: `tests/schema/test_claim_race.py::TestTwoSimultaneousFirstClaimsAllocateOnce` | closed |
| T-41-03 | Information disclosure | raw device token in a log, row or error | high | mitigate | `auth/devicecheck.py` imports no logger (grep: only the docstring names one); `ProofRejected`/`DeviceGrantExhausted` inherit `ProviderLookupError`'s keyword-only `stage`/`cause` from a closed set (`errors.py:348-361`); `test_rejection_vocabulary.py::test_no_arm_can_carry_anything_into_its_log_line` | closed |
| T-41-04 | Information disclosure | account-state enumeration via 403 bodies | high | mitigate | `ClaimRefused` declares status 403 and code `operation_not_allowed` once (`errors.py:436-441`); leaves add only a name. `test_rejection_vocabulary.py::test_no_arm_declares_a_status_or_a_code_of_its_own` | closed |
| T-41-05 | Tampering / Elevation | failing open on an ambiguous Apple response | high | mitigate | Five ordered parse arms in `_parse_bit_state`; an unrecognised body raises `RetryableDeviceCheckError` and an exhausted budget becomes `Unavailable` (`devicecheck.py:98-110,146-151`). `test_devicecheck_adapter.py::TestTheParseArms` incl. `test_arm_five_an_unrecognised_body_fails_closed_rather_than_defaulting` | closed |
| T-41-06 | Tampering | destroying Phase 42's bit1 state | high | mitigate | The write carries the queried bit1 (`services/auth.py:194`: `bit1=state.bit1`); `test_devicecheck_adapter.py::TestTheBit1CarryForward` | closed |
| T-41-07 | Denial of Service | a network call under a held lock | medium | mitigate | Both Apple calls precede `activate_anonymous_device_grant` (`services/auth.py:189-196`); the crud writer cannot import an HTTP client. `tests/unit/test_claim_ordering.py::TestBothVendorCallsPrecedeTheActivation`, `TestTheCrudWriterCannotReachTheVendor`; `test_claim_precedence.py::TestNoVendorCallHappensUnderALockOrInsideTheTransaction` | closed |
| T-41-08 | Denial of Service | unbounded Apple calls from one eligible token holder | medium | accept | Recorded as D-20 in `STATE.md:216` and under ANONGRANT-01 in `REQUIREMENTS.md`; see AR-41-01 | closed |
| T-41-09 | Denial of Service | crash between the confirmed bit write and the commit | low | accept | Recorded in `41-CONTEXT.md` D-06 (lines 81-83): accepted and uncompensated, remediation is an operator `manual` grant; see AR-41-02 | closed |
| T-41-10 | Information disclosure | the ES256 private key | high | mitigate | Key path only in `.env.example:81` (`DEVICECHECK_PRIVATE_KEY_PATH`, outside the repo); `.env` is gitignored; `config/config.yaml` has no devicecheck section; `git grep` finds no PEM material. An absent key yields `None` (`devicecheck.py:54-59`) and `_service_jwt` raises `Unavailable` having sent nothing (`:62-65`); `test_devicecheck_adapter.py::TestAnAbsentCredentialFailsClosed` | closed |
| T-41-11 | Denial of Service | a request in flight against an open breaker | high | mitigate | `before_call` runs inside every attempt (`resilience.py:147`); `test_resilience_retry.py::test_a_breaker_opening_mid_flight_ends_the_request_on_its_next_attempt` | closed |
| T-41-12 | Denial of Service | provider permits held across a database round trip | high | mitigate | `admission` takes only the breaker check and the in-flight slot (`resilience.py:134-136`); the `concurrency` permit wraps the retry loop (`:162-175`); the quota charge runs inside admission, before the permit (`services/chats.py:92-93`) | closed |
| T-41-13 | Denial of Service | pool exhaustion at three concurrent chat posts | high | mitigate | `config/config.yaml:19` `db.pool_size: 12` with the relation noted at `:16`; `test_config.py::test_the_tracked_pool_size_loads_beside_the_environment_credentials` | closed |
| T-41-14 | Repudiation / integrity | a breaker refusal recorded as a provider failure | medium | mitigate | Pass-through arm ordered first (`resilience.py:150`); `test_resilience_retry.py::TestGateAndBreakerErrorsAreNeverWrapped` | closed |
| T-41-15 | Tampering | double or phantom billing | medium | mitigate | `quota_service.charge` sits inside `admission()` and outside `ask_llm`'s retry loop (`services/chats.py:92-93`); 22 cases in `tests/unit/test_quota_seam.py` pass | closed |
| T-41-16 | Information disclosure | account-state enumeration through 403 bodies | high | mitigate | Same base as T-41-04; `tests/e2e/test_claim_anonymous_grant.py::TestTheFourRefusals` compares each body to one constant by equality | closed |
| T-41-17 | Information disclosure | device-state disclosure | medium | mitigate | `DeviceGrantExhausted` carries only `stage`/`cause` log fields, never a response field (`errors.py:348-361,427-430`); e2e `test_a_device_whose_bit0_is_already_set_is_exhausted_and_is_never_written_to` | closed |
| T-41-18 | Elevation of Privilege | a registered caller taking the anonymous grant | high | mitigate | Provider checked positively at the top (`services/auth.py:169-170`) and re-checked under the locks (`crud/grants.py:141-144`); e2e `test_a_registered_caller_is_refused_and_waits_for_phase_42` | closed |
| T-41-19 | Spoofing | burning another caller's live handle | high | mitigate | Pre-claim rejections neither claim nor consume (`services/auth.py:120-131`); `test_claim_precedence.py::TestTheRejectionsBeforeTheClaimSpendNothing` (three cases) | closed |
| T-41-20 | Elevation of Privilege | a spent lifetime slot reopened by revocation | high | mitigate | `_prior_free_grant_statement` has no status predicate (`crud/grants.py:62-66`); e2e `test_a_revoked_free_grant_is_refused_because_the_read_carries_no_status_predicate` | closed |
| T-41-21 | Tampering | a second writer of the free grant source added later | medium | mitigate | `tests/unit/test_grant_sources.py::TestTheAnonymousDeviceGrantHasExactlyOneWriter` walks `src/` with controls in `TestTheWalkFires`; `FREE_GRANT_SOURCES` named once | closed |
| T-41-22 | Elevation of Privilege | two simultaneous first claims both allocating | high | mitigate | The unique indexes arbitrate; `tests/schema/test_claim_race.py` drives two real completions on two connections to a barrier and asserts one grant, one usage row, one marker | closed |
| T-41-23 | Denial of Service | a genuine race surfacing as a 500 | high | mitigate | The flush's `IntegrityError` is read as `lost_race` only on SQLSTATE 23505 (`crud/grants.py:174-181`, narrowed by 42-07, closing WR-01); the loser answers 200 (`test_the_loser_answers_two_hundred_with_the_winners_entitlement`, `test_the_losers_violation_arrived_at_the_flush_and_not_at_the_commit`) | closed |
| T-41-24 | Tampering | a deadlock introduced by a third lock tier | medium | mitigate | The planned control exists: `tests/schema/test_grant_locks.py::TestTheActivationAddsNoThirdLockTier` captures the writer's real SQL and asserts exactly two explicit tiers, neither identity nor user. Residual (41-REVIEW WR-05, confirmed still present): the fixture reaches only the refused branch (`:313-317`), so the write branch's implicit locks (FK `KEY SHARE` on `core.users` from the grant INSERT, row lock from the identity UPDATE) are unmeasured. `/auth/upgrade-anonymous` locks identity and user `FOR UPDATE` in one statement (`crud/identities.py:61-74`), so a same-account concurrent upgrade and claim can deadlock in a narrow window; Postgres kills one with a 500. Severity stays medium: one account, one request, self-healing on retry | open — below high threshold (non-blocking) |
| T-41-25 | Elevation of Privilege | a spent lifetime slot reopened by narrowing the source set | medium | mitigate | `test_grant_locks.py::TestTheFreeGrantSourceSetMatchesTheIndex::test_the_named_set_equals_the_live_index_predicate` reads the live catalogue predicate | closed |
| T-41-26 | Repudiation | an unrecorded divergence from the binding specification | high | mitigate | `REQUIREMENTS.md` ANONGRANT section carries four dated flagged conflicts (D-01, D-03, D-08, D-09), one precedence resolution (D-13) and the consequences, each under its requirement | closed |
| T-41-27 | Repudiation | a dead obligation read as unmet work | medium | mitigate | The dead-obligation inventory under ANONGRANT-01 names each item with the phase and decision that removed it | closed |
| T-41-28 | Tampering | a specification edited to agree with the code | high | mitigate | `06-claim-anonymous-grant.md` (mtime 2026-08-18) and `SHARED-INVARIANTS.md` (mtime 2026-09-01) both predate the phase's execution window (2026-09-02 22:16 to 23:34); neither appears in any plan's `files_modified` | closed |
| T-41-29 | Repudiation | an accepted risk mistaken for an oversight | medium | mitigate | `STATE.md:216` records the Apple exposure as accepted with precedent (Phase 40 D-22), mitigation and closing condition (v2.1 gateway contract) | closed |
| T-41-30 | Information disclosure | a credential or token written into a planning file | high | mitigate | grep of `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md` for PEM headers, API keys and JWT-shaped strings: no match | closed |
| T-41-SC | Tampering | npm/pip/cargo installs | high | mitigate | No new package: `httpx >=0.28` moved from the dev group into `[project].dependencies` (`pyproject.toml:26`, still at `:35`); plans 02-05 touched no manifest | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-41-01 | T-41-08 | Every eligible claim makes an unbounded pair of Apple DeviceCheck round trips. No backend rate limiting exists (Phase 35 D-05) and the Envoy contract is v2.1 (Phase 35 D-08). Mitigating: one account looping on itself, the preflight refuses an ineligible account before Apple is reached, and each turn costs a fresh challenge. Closes with the v2.1 gateway contract. Recorded as D-20 (`STATE.md:216`) | Phase 41 D-20 | 2026-09-03 |
| AR-41-02 | T-41-09 | A crash after a confirmed bit write and before commit burns the device slot with no grant. Uncompensated by design: `SHARED-INVARIANTS.md` forbids a background healer, so no pending-state machine or reconciler exists. Remediation is an operator `manual` grant. Recorded in `41-CONTEXT.md` D-06 | Phase 41 D-06 | 2026-09-02 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-04 | 31 | 30 | 1 (medium, non-blocking) | secure-phase orchestrator, ASVS L1 grep-depth against the tree at 6b14231; auditor not spawned (short-circuit: no blocking threats, plan-time register, L1) |

Follow-up carried forward, not blocking: extend `TestTheActivationAddsNoThirdLockTier` with a fixture that reaches the flush (`activated`), and either record the write branch's implicit locks as acceptable or reorder the flush so the identity UPDATE precedes the grant INSERT.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-04
