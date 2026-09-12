# Deferred items — Phase 47

## Pre-existing e2e failure, out of scope for plan 47-01

`tests/e2e/test_restore_subscription.py::TestEveryRejectedProofOfBothStoresAnswersOneBody::test_the_four_arms_answer_bodies_equal_to_each_other_and_write_nothing`

The case expects the log event name `proof_rejected`; the code emits
`purchase_proof_rejected`. Measured on HEAD (1a3273d) with every plan 47-01 edit
reverted: the case fails the same way. It is not caused by this plan and this
plan does not fix it. Discovered 2026-09-12.
