---
phase: "46"
slug: "post-auth-sign-out-all"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-08"
---

# Phase 46 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client -> Envoy Gateway -> the handler | An untrusted caller crosses here with a Firebase ID token; the gateway authenticates by JWT and rate-limits by IP and user. | Firebase ID token (bearer credential) |
| the handler -> Firebase Admin | The deployment's own credential crosses here to a Google endpoint; the subject is caller-influenced through the verified token. | Provider uid, Application Default Credentials |
| the outcome -> the log pipeline | Provider text and identifiers cross here; only a closed set of fields is admissible. | `identity_row_id`, `stage`, `detail` (bounded); never subject, uid or token |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-46-01 | Repudiation | `revoke_with_retry` exhaustion / a swallowed raise | high | mitigate | `_revocation_exhausted` raises `RevocationUnconfirmed` (`auth/firebase.py:181-192`); `test_firebase_retry.py` pins the class, not `Unavailable` or `RetryError`; every e2e refusal asserts not 204 | closed |
| T-46-02 | Spoofing | issuer to Admin app selection | high | mitigate | One named app per issuer in `self._apps`, `app=app` passed on every call, no `[DEFAULT]` app (`auth/firebase.py:32-86`); unconfigured issuer raises before any call; `test_firebase_adapter.py` records the app object | closed |
| T-46-03 | Information disclosure | the INFO and WARNING records (D-07) | medium | mitigate | `logger.info("sign_out_all_confirmed", identity_row_id=...)` only (`routers/auth.py:208`); `test_sign_out_all.py` asserts exact fields and that no record carries the subject or uid | closed |
| T-46-04 | Information disclosure | the 503 and 401 bodies | medium | mitigate | One shared one-field body `{"code": ...}`; provider text goes to the WARNING record through `stage` and bounded `detail` (`errors.py:385-414`); e2e compares the two 503 bodies as raw bytes | closed |
| T-46-05 | Elevation of privilege | the barrier on this route | high | mitigate | `Depends(get_linked_identity)` on the handler, no `get_db` (`routers/auth.py:203-204`); `test_app_wiring.py` pins the path in both narrowed-route lists and the no-session case; e2e compares barrier rejections against `/auth/sync` bytes with zero Firebase calls | closed |
| T-46-06 | Denial of service | one Firebase revocation write per attempt | medium | accept | Recorded under SIGNOUT-01 in REQUIREMENTS.md as an uncounted divergence on the Phase 40 D-22 precedent; bound is the v2.1 gateway contract | closed |
| T-46-07 | Denial of service | a malformed subject burning three attempts | low | mitigate | `ValueError` arm costs exactly one attempt; `test_firebase_retry.py` attempt-count table (46-03 task 2) | closed |
| T-46-08 | Repudiation | the phase record | medium | mitigate | D-06 is a dated, line-referenced entry under SIGNOUT-01; both spec files byte-identical by sha256 (re-checked in this audit) | closed |
| T-46-09 | Tampering | the recorded suite counts | medium | mitigate | Counts run in 46-05 and reproduced by this audit: unit 1281, e2e 348, schema 229, ruff clean | closed |
| T-46-10 | Information disclosure | the production-only A1 exposure (`USER_NOT_FOUND` mapping never probed live) | low | transfer | Raised to the developer under SIGNOUT-01 with what settles it: one real-credential call against a deleted uid | closed |
| T-46-11 | Tampering | the auth-package ratchet | low | mitigate | `CURRENT = (8, 24, 64)` written from a measured failing run in `test_auth_package_shape.py` | closed |
| T-46-SC | Tampering | npm/pip/cargo installs | low | accept | No commit since tag `phase-45` touches `pyproject.toml` or `uv.lock` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-46-01 | T-46-06 | Caller must hold a valid Firebase ID token for a linked, active account, so it is one subject looping on itself; the write is idempotent by the brief's semantics at `11-sign-out-all.md:52`; closes with the v2.1 gateway contract | Phase 46 plan 46-05 (REQUIREMENTS.md, SIGNOUT-01) | 2026-09-08 |
| R-46-02 | T-46-SC | The phase installs no package and changes no lock file | Phase 46 plans 46-01 to 46-05 | 2026-09-08 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-08 | 12 | 12 | 0 | execute-phase secure-phase step (L1 grep-depth; auditor skipped per short-circuit rule) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-08
