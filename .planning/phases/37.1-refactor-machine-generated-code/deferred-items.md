# Deferred items — phase 37.1

Out-of-scope discoveries logged rather than fixed, per the executor's scope boundary.

## From plan 02

**1. `src/nativespeaker/api/errors.py` — the 405 comment is inaccurate, and was already.**

The A1 note above `METHOD_NOT_ALLOWED` says "a 405 is only reachable by a caller the barrier
already admitted". That was false *before* this plan too: the middleware's `_match_full` returned
`None` on a `Match.PARTIAL` (path matches, method does not) and passed the request straight
through unauthenticated, leaving the router to answer 405. It is equally false now, for the
symmetrical reason — a method mismatch matches no route, so no route's auth dependency runs.

`tests/e2e/test_admission.py::TestAdmissionPhasePrecedesAuth` asserts the real behaviour in both
directions (`test_a_wrong_method_returns_405_not_401` and
`test_the_405_holds_even_with_a_valid_credential`), so the code is right and only the comment is
wrong. Not caused by this plan and not touched by it; the anti-oracle claim the sentence is making
("there is no anti-oracle cost") happens to survive its own bad reasoning, because a 405 discloses
only that the path exists, which a 401 on the same path discloses too.

**2. `tests/e2e/test_startup_assertion.py` no longer names what it tests.**

Plan 02 deleted the two startup-assertion cases; what survives is the unauthenticated-access
matrix (401 on `/`, 200 on `/health/ready`, 404 on the four doc routes, 404 on a trailing slash).
The class was renamed to `TestUnauthenticatedAccess`, but the **file** was not renamed, because
plan 02's own acceptance criteria reference `tests/e2e/test_startup_assertion.py` by path. A later
plan should rename it to something like `tests/e2e/test_unauthenticated_access.py`.
