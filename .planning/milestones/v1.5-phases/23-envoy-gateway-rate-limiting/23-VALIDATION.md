---
phase: 23
slug: envoy-gateway-rate-limiting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0 + pytest-asyncio >=1.3 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/unit/ -x -q` |
| **Full suite command** | `pytest tests/unit/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/ -x -q`
- **After every plan wave:** Run `pytest tests/unit/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green + `helm template k8s/ --values k8s/values.yaml` renders without errors
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-XX-01 | XX | X | ENVOY-01 | manual-only | N/A (requires live Envoy Gateway) | N/A | ⬜ pending |
| 23-XX-02 | XX | X | ENVOY-02 | manual-only | N/A (requires live Envoy Gateway) | N/A | ⬜ pending |
| 23-XX-03 | XX | X | ENVOY-03 | manual-only | N/A (requires live Envoy Gateway) | N/A | ⬜ pending |
| 23-XX-04 | XX | X | ENVOY-04 | manual-only | N/A (infrastructure config) | N/A | ⬜ pending |
| 23-XX-05 | XX | X | ENVOY-05 | unit | `pytest tests/unit/test_users.py -x` | ✅ (extend) | ⬜ pending |
| 23-XX-06 | XX | X | -- | unit | `pytest tests/unit/test_error_contract.py -x` | ✅ (extend) | ⬜ pending |
| 23-XX-07 | XX | X | -- | unit | `pytest tests/unit/test_usage.py -x` | ❌ W0 | ⬜ pending |
| 23-XX-08 | XX | X | -- | unit | `pytest tests/unit/test_services.py -x` | ✅ (extend) | ⬜ pending |
| 23-XX-09 | XX | X | -- | unit | `pytest tests/unit/test_subscriptions.py -x` | ✅ (extend) | ⬜ pending |
| 23-XX-10 | XX | X | -- | unit | `helm template k8s/ --values k8s/values.yaml` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_usage.py` — covers quota check-and-increment, lazy row creation, usage reset
- [ ] Helm template validation via `helm template` command (no test file needed, use CLI)

*Existing infrastructure covers remaining phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| JWT plan claim extracted to x-user-plan header | ENVOY-01 | Requires live Envoy Gateway cluster | Deploy chart, send JWT with `plan` claim, verify `x-user-plan` header forwarded to backend |
| Per-user rate limits by plan tier at edge | ENVOY-02 | Requires live Envoy Gateway cluster | Deploy chart, send >N requests per minute per tier, verify 429 at threshold |
| Webhook bypasses JWT authentication | ENVOY-03 | Requires live Envoy Gateway cluster | Deploy chart, send POST to `/webhooks/apple` without JWT, verify 200 |
| Rate limiting uses local (not Redis) | ENVOY-04 | Infrastructure config verification | Inspect BackendTrafficPolicy YAML for `local:` block, confirm no Redis references |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
