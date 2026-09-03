---
title: The admission gate holds a DB connection across the quota charge
area: resilience
created: 2026-08-31
source: Phase 37.5 code review (CR-01), 37.5-REVIEW.md
completed: 2026-09-02
completed_in: 41
status: done
---

# The admission gate holds a DB connection across the quota charge

`ChatService.create_chat` and `send_message` both do:

```python
async with self.llm_service.admission() as admitted:
    await self.quota_service.charge(...)      # a DB write, inside the gate
    ai_message = await self.ask_llm(..., admitted)
```

Phase 37.5 moved the charge inside `admission()` so an unreached provider is not
billed. That part is correct and holds. But the gate hold widened from "around the
provider call" to "around the whole body", and the body now checks out a database
connection.

**Why it matters:** `db.pool_size` is 5 with `max_overflow: 0`, and
`resilience.pool_size` is 5 (`config/config.yaml:7`, `config.py:25,34`). A caller
already holding a connection that then passes admission and requests a second one
can contend. Below the deadlock threshold it degrades differently but still badly:
a stalled charge holds an LLM semaphore slot, so a slow database becomes
indistinguishable from a saturated LLM and surfaces as a 503 storm.

**Scope when picked up:**
- Move the charge outside the `admission()` context, or make it use a connection
  acquired before admission, so no gate hold spans a pool checkout.
- Keep the billing property that Phase 37.5 established: `tests/unit/test_quota_seam.py`
  has 20 cases asserting an open circuit and a full queue each leave
  `usage.monthly_used == 0`, and that a retried request spends exactly one unit
  against three provider calls. Those must stay green.
- Consider whether `resilience.pool_size` and `db.pool_size` should be related
  rather than independently 5.
