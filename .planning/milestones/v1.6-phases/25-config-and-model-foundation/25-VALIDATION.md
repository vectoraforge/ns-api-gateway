---
phase: 25
slug: config-and-model-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -c "from nativespeaker.api.models import *; from nativespeaker.api.config import *; from nativespeaker.api.schema import *"`
- **After every plan wave:** Run `python -c "from nativespeaker.api.models import *; from nativespeaker.api.config import *; from nativespeaker.api.schema import *; from nativespeaker.api.services.subscriptions import *; from nativespeaker.api.services.chats import *"`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 25-01-01 | 01 | 1 | QUOTA-01 | unit | `python -m pytest tests/unit/test_config.py -x -k quota` | Wave 0 | ⬜ pending |
| 25-01-02 | 01 | 1 | QUOTA-02 | unit | `python -m pytest tests/unit/test_config.py -x -k main_config` | Existing | ⬜ pending |
| 25-01-03 | 01 | 1 | QUOTA-05 | smoke | `python -c "from nativespeaker.api.models import *"` | N/A | ⬜ pending |
| 25-02-01 | 02 | 1 | ENUM-01 | smoke | `python -c "from nativespeaker.api.models import *"` | N/A | ⬜ pending |
| 25-02-02 | 02 | 1 | ENUM-03 | smoke | `python -c "from nativespeaker.api.models import User"` | N/A | ⬜ pending |
| 25-02-03 | 02 | 1 | ENUM-04 | smoke | `python -c "from nativespeaker.api.models import SubscriptionEvent"` | N/A | ⬜ pending |
| 25-02-04 | 02 | 1 | ENUM-05 | smoke | `python -c "from nativespeaker.api.schema import UserProfileResponse"` | N/A | ⬜ pending |
| 25-02-05 | 02 | 1 | SCHEMA-02 | smoke | `python -c "from nativespeaker.api.models import Message; assert Message.__tablename__ == 'messages'"` | N/A | ⬜ pending |
| 25-02-06 | 02 | 1 | ENUM-02 | smoke | `python -c "from nativespeaker.api.models import *"` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_config.py` — add `test_quota_config_*` stubs for QUOTA-01 (import smoke covers Phase 25; comprehensive tests deferred to Phase 28 per D-12)

*Existing infrastructure covers most phase requirements via import smoke tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Enum class names match PG convention | ENUM-01 | Naming convention review | Verify class names in `models.py` match `SubscriptionPlan`, `AnalysisType` patterns |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
