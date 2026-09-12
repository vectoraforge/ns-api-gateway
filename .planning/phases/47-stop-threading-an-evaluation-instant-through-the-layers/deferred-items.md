# Deferred items — Phase 47

## Pre-existing e2e failure, out of scope for plan 47-01

`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`

The case expects the log event name `proof_rejected`; the code emits
`purchase_proof_rejected`. Measured on HEAD (1a3273d) with every plan 47-01 edit
reverted: the case fails the same way. It is not caused by this plan and this
plan does not fix it. Discovered 2026-09-12.

## A one-minute open term, found by plan 47-08 — **CLOSED 2026-09-12 in `5ad4fbd`**

**Resolved at the root, not worked around.** The orchestrator fixed it in commit `5ad4fbd`,
`fix(47-05): the open-term control reads the clock when it runs`. The control now computes
`ends_at = datetime.now(UTC) + timedelta(minutes=1)` at call time and asserts against that
value, instead of dating the term from the module-import `NOW`. The property and the
assertion shape are unchanged, and it is the same call-time read every other plan in this
phase adopted.

Re-measured by plan 47-08 at HEAD `5ad4fbd`: `.venv/bin/pytest -q -m ''` reports **1 failed,
2572 passed** — one more passing case than before the fix, and the failure that remains is
the unrelated pre-existing restore case below. `.venv/bin/pytest tests/unit -q` reports
**1921 passed, exit 0**.

**One side effect the fix carried in, recorded below rather than hidden:** the new line
overruns the line-length limit, so `ruff` is no longer clean. See the next section.

The original diagnosis follows, kept as written.

### The defect as it was found

`tests/unit/test_subscription_attribution.py::TestAnEntitledNotificationWithNoOpenTermIsRefusedBeforeAnyWrite::test_a_term_still_open_when_the_ingestion_reads_is_written_control`

Line 964 sets `expires_at=NOW + timedelta(minutes=1)`. `NOW` is
`datetime.now(UTC)` read at module import, line 33. The case asserts the
notification's term is still open when `SubscriptionsService.ingest` reads its
own clock. The open window is therefore **one minute from import**, not from the
moment the case runs.

pytest imports every test module during collection. A run longer than one minute
between that import and this case closes the term, so `ingest` raises
`InternalError` at `services/subscriptions.py:109` and the case fails.

**Measured, not reasoned about.** The case passes alone in 0.03 s. Under
`.venv/bin/pytest -q -m ''` (2573 collected, 131 s) it fails. A throwaway pytest
plugin that sleeps 65 s in `pytest_collection_finish` — after every import, before
any case runs — reproduces the failure on that one case with the same raise site.
The bare unit run took 57.74 s in this session and passed, which is under the
window by about two seconds.

Plan 47-05 introduced this when it moved this module's terms onto the live clock
(its deviation 3). Its sibling terms are ten to thirty days out; this one is one
minute. The production guard is correct — only the test's window is too small.

Not fixed here: plan 47-08 writes no source and its own action forbids repair.
The fix is a wider window, or an open term derived at call time rather than at
import. Discovered 2026-09-12. **Fixed the same day in `5ad4fbd`, by the second
of those two routes.**

## `ruff` is no longer clean — E501 introduced by the fix commit `5ad4fbd`

`tests/unit/test_subscription_attribution.py:962` is **137 characters** against the
`line-length = 120` set in `pyproject.toml:79`:

```
        ends_at = datetime.now(UTC) + timedelta(minutes=1)  # The term must be open when ingest reads, not when this module was imported.
```

`ruff check src tests` exits **1** and prints exactly one error, `E501 Line too long
(137 > 120)`. Both invocation forms agree — `.venv/bin/ruff` and `uv run ruff`.

**This is a regression, and the before-and-after was measured rather than assumed.** Plan
47-08 ran `ruff check src tests` at `9d307df`, before the fix landed, and it printed
`All checks passed!` and exited 0 in both forms. The only source commit between the two
readings is `5ad4fbd`, and the only file it touches is this one.

The fix for the fix is cosmetic: move the explanatory comment to its own line above the
statement, which is what the surrounding file already does. Not repaired by plan 47-08,
which writes no source. This breaks the plan's own `must_haves` truth *"ruff is clean over
src and tests"*. Discovered 2026-09-12.
