# Deferred items — Phase 47

## Pre-existing e2e failure, out of scope for plan 47-01

`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`

The case expects the log event name `proof_rejected`; the code emits
`purchase_proof_rejected`. Measured on HEAD (1a3273d) with every plan 47-01 edit
reverted: the case fails the same way. It is not caused by this plan and this
plan does not fix it. Discovered 2026-09-12.

## A one-minute open term, found by plan 47-08 and caused by this phase

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
import. Discovered 2026-09-12.
