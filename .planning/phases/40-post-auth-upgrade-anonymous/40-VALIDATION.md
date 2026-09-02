---
phase: 40
slug: post-auth-upgrade-anonymous
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-02
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `40-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio ≥1.3, `asyncio_mode = "auto"` |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest` (unit suite — `addopts` deselects `e2e` and `schema`) |
| **Full suite command** | `uv run pytest -m 'e2e or schema' && uv run pytest` |
| **Estimated runtime** | ~unit suite fast (no external deps); `e2e`/`schema` need live PostgreSQL, `e2e` also needs Firebase credentials |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest`
- **After every plan wave:** Run `uv run pytest -m schema` after any migration or `tables/` change; `uv run pytest -m e2e` after any router/service change
- **Before `/gsd:verify-work`:** `uv run pytest -m 'e2e or schema'` and `uv run pytest` both green, plus `ruff check`
- **Max feedback latency:** unit suite per commit

---

## Per-Task Verification Map

Task IDs are assigned by the planner; `/gsd:validate-phase` fills this table against the
requirement→test map in `40-RESEARCH.md` § Validation Architecture.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | UPGRADE-01 | T-40-01 / — | {expected secure behavior or "N/A"} | e2e | `uv run pytest -m e2e tests/e2e/test_upgrade_anonymous.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/e2e/test_upgrade_anonymous.py` — the endpoint's own e2e file (D-18 real case + D-19 fake cases)
- [ ] `tests/unit/test_upgrade_precedence.py` — rejection-precedence and consumption-disposition cases
- [ ] `tests/schema/test_registration_pairing.py` — D-12's third-state scan (asyncpg, outside the e2e rollback)
- [ ] **Answer § P-01 before the test wave** — route (a), (b) or (c); the choice changes what gets written
- [ ] Reserve and document the D-18 account UID env var in `.env.example` (D-18 obligation 1)
- [ ] Edits to existing test files: `tests/schema/test_inventory.py` (enum literal),
      `tests/schema/test_constraints.py` (three cases, P-02), `tests/unit/test_challenge_endpoint.py`
      (`_NOT_ISSUABLE` + `store.issued`, P-02), `tests/unit/test_rejection_vocabulary.py`
      (`EVENT_NAMES` + `CONSTRUCTOR_ARGUMENTS`), `tests/unit/test_app_wiring.py` (name the new path),
      `tests/unit/test_conflict_classification.py` (Pitfall 1's judgement call)
- [ ] Framework install: **none** — pytest, pytest-asyncio, asyncpg and httpx are all installed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Google-linked account completes through the real Admin SDK | UPGRADE-01 | Blocked on § P-01 — no custom-token signer is available on this machine (`authorized_user` ADC, org policy forbids minting a key). Automated only if route (a) or (b) is taken. | Under route (c): skip marker mirrors `anonymous_firebase_credential`; verify by hand against a real linked account before release |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < unit-suite runtime
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
