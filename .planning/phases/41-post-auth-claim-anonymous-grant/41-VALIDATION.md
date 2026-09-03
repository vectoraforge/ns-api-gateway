---
phase: 41
slug: post-auth-claim-anonymous-grant
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-02
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `41-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 with pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -q` (unit only — `addopts = "-v --tb=short -m 'not e2e and not schema'"` deselects the rest) |
| **Full suite command** | `uv run pytest -q && uv run pytest -m 'e2e or schema' -q && uv run ruff check src tests` |
| **Estimated runtime** | ~2 s for the unit suite (no infrastructure); `e2e`/`schema` need live PostgreSQL 17, `e2e` also needs a Firebase Admin credential |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q`
- **After every plan wave:** Run `uv run pytest -q && uv run pytest -m 'e2e or schema' -q`
- **Before `/gsd:verify-work`:** Full suite green plus `uv run ruff check src tests` clean
- **Max feedback latency:** unit-suite runtime (~2 s)

---

## Per-Task Verification Map

Task IDs are assigned by the planner; `/gsd:validate-phase` fills this table against the
requirement→test map in `41-RESEARCH.md` § Validation Architecture, reproduced here as the
seed rows.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | ANONGRANT-01 | — | `anonymous_device_grant` is written from exactly one site in `src/` | unit | `uv run pytest tests/unit/test_grant_sources.py -q` | ❌ W0 | ⬜ pending |
| {N}-01-02 | 01 | 1 | ANONGRANT-01 | — | Successful claim returns 200 + `SyncResponse` + `Cache-Control: no-store` | e2e | `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` | ❌ W0 | ⬜ pending |
| {N}-01-03 | 01 | 1 | ANONGRANT-01 | — | Route registered, narrowed to linked identities, in neither exemption set | unit | `uv run pytest tests/unit/test_app_wiring.py -q` | ✅ extend | ⬜ pending |
| {N}-01-04 | 01 | 1 | ANONGRANT-02 | — | Grant rows lock ascending by id, then usage rows; no other lock tier first | schema | `uv run pytest tests/schema/test_grant_locks.py -m schema -q` | ✅ extend | ⬜ pending |
| {N}-01-05 | 01 | 1 | ANONGRANT-02 | — | No network call while a lock is held or a transaction is open | unit | `uv run pytest tests/unit/test_claim_ordering.py -q` | ❌ W0 | ⬜ pending |
| {N}-01-06 | 01 | 1 | ANONGRANT-03 | — | Two concurrent claims → one grant, one usage row, one anti-abuse row, marker set once, both challenges consumed, loser 200 | schema | `uv run pytest tests/schema/test_claim_race.py -m schema -q` | ❌ W0 (D-12) | ⬜ pending |
| {N}-01-07 | 01 | 1 | ANONGRANT-03 | — | Repeat claim on an active free grant answers 200 without reaching Apple | e2e | `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` | ❌ W0 | ⬜ pending |
| {N}-01-08 | 01 | 1 | ANONGRANT-03 | — | Consumed-but-inactive free grant, and an active grant of another source, both answer 403 | e2e | `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` | ❌ W0 | ⬜ pending |
| {N}-01-09 | 01 | 1 | D-06 | Replay / spoofed bits | Apple adapter: JWT header/claims, both body shapes, bit1 carried forward, four parse arms | unit | `uv run pytest tests/unit/test_devicecheck_adapter.py -q` | ❌ W0 | ⬜ pending |
| {N}-01-10 | 01 | 1 | D-06 | — | Every post-claim outcome consumes the challenge; pre-claim rejections do not | unit | `uv run pytest tests/unit/test_claim_precedence.py -q` | ❌ W0 | ⬜ pending |
| {N}-01-11 | 01 | 1 | D-11 | Account enumeration via 403 bodies | Both new codes are 403; `ErrorCode` and the tree agree in both directions | unit | `uv run pytest tests/unit/test_error_registry.py tests/unit/test_rejection_vocabulary.py -q` | ✅ no edit | ⬜ pending |
| {N}-01-12 | 01 | 1 | D-14 | Fail-open on exhausted budget | Request in flight when the breaker opens fails on its next attempt with 503 + `Retry-After` | unit | `uv run pytest tests/unit/test_resilience_retry.py -q` | ✅ extend | ⬜ pending |
| {N}-01-13 | 01 | 1 | D-15 | — | The charge commits and releases its connection before a provider permit is taken; the twenty billing cases stay green | unit | `uv run pytest tests/unit/test_quota_seam.py -q` | ✅ reword + extend | ⬜ pending |
| {N}-01-14 | 01 | 1 | D-16 | — | `db.pool_size` resolves to 12 | unit | `uv run pytest tests/unit/test_config.py -q` | ✅ extend | ⬜ pending |
| {N}-01-15 | 01 | 1 | C-4/C-5 | — | Docstring and comment bar stays 0 on every root | unit | `uv run pytest tests/unit/test_docstring_bar.py -q` | ✅ no edit | ⬜ pending |
| {N}-01-16 | 01 | 1 | — | — | `auth/` package shape literal updated | unit | `uv run pytest tests/unit/test_auth_package_shape.py -q` | ✅ **must edit `CURRENT`** | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_devicecheck_adapter.py` — the adapter's signing and all four parse arms (D-04, D-06)
- [ ] `tests/e2e/test_claim_anonymous_grant.py` + a `scripted_devicecheck_adapter` fixture in `tests/e2e/conftest.py` — covers ANONGRANT-01/03 (D-04)
- [ ] `tests/schema/test_claim_race.py` — covers ANONGRANT-03 (D-12)
- [ ] `tests/unit/test_claim_precedence.py` — rejection precedence and consume-on-every-post-claim-outcome (D-06)
- [ ] `tests/unit/test_grant_sources.py` — the single-writer assertion for ANONGRANT-01
- [ ] `tests/unit/test_claim_ordering.py` — the no-network-under-lock structural assertion for ANONGRANT-02
- [ ] `tests/unit/test_auth_package_shape.py::CURRENT` — **edit**, not create (Pitfall 4)
- [ ] Framework install: **none** — pytest, pytest-asyncio, asyncpg, httpx, PyJWT[crypto] and tenacity are all installed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A real Apple DeviceCheck round trip (real device token, real key ID / team ID / ES256 key) | ANONGRANT-01 | No Apple DeviceCheck credentials and no iOS app producing real device tokens exist on this machine. Recorded as a fact by D-04, not a gap this phase can close. | Deferred until an iOS app exists. Automated coverage is the scripted fake (e2e) plus unit tests against the documented wire shapes; the first real 400 is the check on the assumed field names. |
| Real anonymous Firebase sign-in for the e2e fixture | ANONGRANT-01/03 | Environment-dependent Firebase Admin credential. Existing e2e cases already `pytest.skip` with a named reason. | Set `GOOGLE_APPLICATION_CREDENTIALS` (ADC) in `.env`, then `uv run pytest tests/e2e/test_claim_anonymous_grant.py -m e2e -q` and confirm no skips. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < unit-suite runtime
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
