---
phase: "49"
slug: "delete-the-single-implementation-auth-protocols"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-18"
---

# Phase 49 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Google Pub/Sub push → the RTDN handler | An untrusted signed token crosses here and `JWTVerifier` checks it | signed JWT |
| Google Play Developer API → the restore service | An external subscription answer crosses here | subscription state |
| Firebase Admin SDK → the auth service | An externally-owned identity record crosses here as `VerifiedProviderIdentity` | verified uid, email |
| Apple DeviceCheck → the claim path | An externally-held bit pair crosses here and gates a free grant | device bits |
| client → `POST /auth/challenge` | An untrusted caller asks for a single-use capability here | challenge handle (secret) |
| client → the four completion routes | An untrusted caller presents a handle it claims to own here | challenge handle (secret) |
| request session → `core.auth_challenges` | Every challenge read and write crosses here | challenge rows |
| concurrent requests → one challenge row | Two callers can race the same single-use handle here | claim state |

---

## Threat Register

Evidence re-checked at HEAD c6eb771 on 2026-09-18, after the review-fix commits that moved `VerifiedProviderIdentity` to `schemas/auth.py` (0ee572f) and `verify_binding` out of the crud class (1150793).

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-49-01 | Spoofing | `PubSubPushTokens.__init__` | high | mitigate | Annotation-only edit; `test_google_play_notifications.py`, `test_jwt_security.py`, `test_jwks_offload.py` green in the full suite | closed |
| T-49-02 | Tampering | `services/restore.py` `play` parameter | medium | mitigate | Annotation-only edit; `test_restore_proof.py` green | closed |
| T-49-03 | Repudiation | the retired WR-24 guard | low | accept | Accepted risk R-49-01 | closed |
| T-49-04 | Tampering | `VerifiedProviderIdentity` after the move | high | mitigate | `TestTheValueTypeIsImmutable` (4 cases) asserts frozen, slotted, no instance dict, email default against the type now in `schemas/auth.py` | closed |
| T-49-05 | Elevation of Privilege | the `auth/` package's SDK isolation | high | mitigate | `TestNoProviderDependency` walks five auth modules in a subprocess; control asserts `jwt_verifier` in the set | closed |
| T-49-06 | Spoofing | `lookup_with_retry`, `read_bits_with_retry` | medium | mitigate | Annotation-only edit; `test_firebase_retry.py`, `test_devicecheck_adapter.py` green | closed |
| T-49-07 | Repudiation | the retired WR-23 guard | low | accept | Accepted risk R-49-02 | closed |
| T-49-08 | Elevation of Privilege | `AuthService._complete` rejection order | high | mitigate | Four precedence suites green, 136 cases, no assertion edited | closed |
| T-49-09 | Elevation of Privilege | the binding check | high | mitigate | `grep -c verify_binding tests/unit/conftest.py` = 0; `services/auth.py:148` calls the real `verify_binding` | closed |
| T-49-10 | Tampering | single-use consume | high | mitigate | `tests/e2e/test_challenge_store.py` (32) and three schema race suites (55) green against live PostgreSQL | closed |
| T-49-11 | Information Disclosure | the handle in `issue_challenge` | medium | mitigate | `routers/auth.py:59` logs only the operation string; `Cache-Control: no-store` at :75 and :131 | closed |
| T-49-12 | Spoofing | `get_auth_service` provider wiring | medium | mitigate | `dependencies.py:122-123` annotate `FirebaseAdminLookup` and `AppleDeviceCheck`; ty at 295 diagnostics, below the 306 baseline | closed |
| T-49-13 | Elevation of Privilege | `_claim_statement` | high | mitigate | Present at `crud/challenges.py:45`; 8-contender e2e race and schema race suites green | closed |
| T-49-14 | Tampering | `consume` | high | mitigate | The pre-auth-clearing UPDATE unchanged; e2e claimed-to-consumed cases green | closed |
| T-49-15 | Elevation of Privilege | `verify_binding` | high | mitigate | Now a module function at `crud/challenges.py:27` (WR-03); 10 references in `test_challenge_ids.py`, precedence suites green | closed |
| T-49-16 | Tampering | one crud object shared by two sessions | medium | mitigate | `grep -c 'def store' tests/e2e/test_challenge_store.py` = 0; each session builds its own object | closed |
| T-49-17 | Information Disclosure | the handle | medium | mitigate | `crud/challenges.py` imports neither `structlog` nor `logging`; `TestTheStoreHoldsNoLogger` green | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-49-01 | T-49-03 | ROADMAP criterion 3 retires the WR-24 annotation guard; a class cannot fail to carry its own members, so the control had nothing left to catch. Recorded in 49-01-SUMMARY.md | phase owner (plan-time disposition) | 2026-09-18 |
| R-49-02 | T-49-07 | ROADMAP criterion 3 retires the WR-23 annotation guard for the same reason. Recorded in 49-02-SUMMARY.md | phase owner (plan-time disposition) | 2026-09-18 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-18 | 17 | 17 | 0 | verify-work verify:post, L1 grep-depth (Claude) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-18
