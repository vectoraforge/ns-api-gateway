---
phase: 46-post-auth-sign-out-all
fixed_at: 2026-09-08T00:00:00Z
review_path: .planning/phases/46-post-auth-sign-out-all/46-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 46: Code Review Fix Report

**Fixed at:** 2026-09-08
**Source review:** `.planning/phases/46-post-auth-sign-out-all/46-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (WR-01..WR-05; the review found no Critical)
- Fixed: 5
- Skipped: 0
- Out of scope, not attempted: 8 Info findings (IN-01..IN-08), except IN-03, folded into WR-05

Every finding was re-checked against the live code before it was edited. All five held.

## Verification

Run from the repo root after the last commit. The tools are not on `PATH`; they come from
`.venv/bin`. Verification ran in the main checkout, not in an isolated worktree (see Notes).

| Gate | Baseline (review) | After fixes |
|---|---|---|
| `ruff check src tests` | passes | **All checks passed!** |
| `ruff format --check src tests` | 134 reformat / 11 clean | **134 reformat / 11 clean** (unchanged) |
| `pytest tests/unit -q` | 1281 passed | **1283 passed** (+2 new cases from WR-05) |
| `ty check src` | 53 diagnostics, 3 new this phase | **50 diagnostics**, 0 in phase-46 code |

`ruff format --check` fails on 134 files at the baseline and still fails on the same 134. The
project does not use `ruff format` as a gate: its style is a long-line, hand-wrapped one that the
formatter would rewrite wholesale. My edits changed neither the count nor which files are in it.

The three phase-46 `ty` diagnostics (`routers/auth.py:206:38`, `206:64`, `208:63`) are gone:
53 − 3 = 50. The 50 that remain are pre-existing, and none is in the `sign_out_all` block. WR-05's
annotations introduced no new diagnostics.

`tests/e2e/test_sign_out_all.py` reports `15 deselected` in this environment: the e2e suite is
gated behind infrastructure that is not present here. That gating is pre-existing and is not
something these fixes changed.

## Fixed Issues

### WR-01: The malformed-subject arm writes the Firebase subject into the log

**Files modified:** `src/nativespeaker/api/auth/firebase.py`
**Commit:** `cdf1511`

Confirmed the premise empirically before editing, rather than trusting the review's quote:

```
>>> _auth_utils.validate_uid('')
ValueError: Invalid uid: "". The uid must be a non-empty string with no more than 128 characters.
```

The SDK message embeds the uid verbatim, so `detail=str(error)` put the caller's Firebase `sub`
into a WARNING record, against D-07. Dropped the provider text from the arm and switched to
`from None`. No test asserted on the `detail` field, so nothing depended on it.

### WR-02: The handler takes the issuer and subject from the stored row, not from the verified token

**Files modified:** `src/nativespeaker/api/routers/auth.py`
**Commit:** `8f958de`
**Status: fixed — the provenance change deserves a human read**

The handler now sends `identity.issuer` / `identity.subject`, the request-verified pair, to the
provider. This is the root cause the finding names: what is sent to Firebase is now the credential
the request presented, not a database row that merely happens to match.

**One departure from the review's fix text, argued rather than assumed.** The review said the log
line's `identity.identity.id` "stays as is". Taken literally that leaves the third diagnostic
(`208:63`) standing, which contradicts the instruction that all three must go. Both cannot hold, so
I checked which is right.

`Identity` is built in exactly two places (`crud/identities.py:41,53`): either `user` and `identity`
are both set, or both are `None`. So "linked implies a row" is a true structural invariant, and
`get_linked_identity` admits only linked callers. The declared type is simply wider than the
guarantee. I narrowed with a bare `assert`, which is this codebase's own existing device for that
exact situation (`app/error_handlers.py:35,51,62`), not a `ty: ignore` suppression:

```python
    row = identity.identity
    # `resolve` sets the row and the user together, and `get_linked_identity` admits only a linked caller.
    assert row is not None
```

That removes `208:63` at its cause. Verified: 50 diagnostics, none in this handler.

### WR-03: `TestTheSignOutRouteOpensNoSession` asserts nothing

**Files modified:** `tests/unit/test_app_wiring.py`
**Commit:** `d6cd042`

Reproduced the review's claim before editing:

```
/auth/sign-out-all  get_db direct: False  flattened: False
/auth/sync          get_db direct: False  flattened: True
```

`/auth/sync` opens a session through `get_sync_service` and passed the old `_declared` assertion
unchanged, so the test could not fail for the reason its docstring gave. Switched to `_flattened`.
The test now has teeth — the same assertion applied to `/auth/sync` fails — and still passes for
`/auth/sign-out-all`, exactly as the review predicted.

### WR-04: The OpenAPI description overstates what the revocation achieves

**Files modified:** `src/nativespeaker/api/routers/auth.py`
**Commit:** `fffa38f`

Confirmed against the SDK's own docstring, which states that "existing ID tokens may remain active
until their natural expiration (one hour)" and that `check_revoked=True` is what detects revocation.
`grep -rn check_revoked src/` returns nothing, so this deployment cannot detect it. The published
description now states what the call does and names the one-hour window, instead of implying that
current sessions die immediately.

### WR-05: The `FirebaseAdminAdapter` Protocol declares methods no implementation satisfies

**Files modified:** `src/nativespeaker/api/auth/adapters.py`,
`src/nativespeaker/api/auth/firebase.py`, `src/nativespeaker/api/app/dependencies.py`,
`tests/unit/test_adapter_interfaces.py`, `tests/unit/test_firebase_adapter.py`
**Commit:** `9a7f5ec`

Made both Protocol methods `async def`, then annotated `get_firebase_adapter` and both
`*_with_retry` wrappers with the Protocol, so the seam is now actually checked rather than being
documentation.

I proved the finding empirically instead of assuming it, with a temporary probe file that was
removed afterwards. Against a Protocol declared the old synchronous way, `ty` rejects the real
adapter:

```
Expected `OldSyncSeam`, found `FirebaseAdminLookup`
```

Against the corrected async Protocol the same assignment is accepted and adds no diagnostic. That
is the finding's claim — "no object in the codebase conforms to this Protocol" — confirmed and then
resolved.

Test changes:
- `test_adapter_interfaces.py`: added `test_every_method_is_declared_async`, which asserts
  `inspect.iscoroutinefunction` on both methods. This is what locks the fix in; the two return
  tests still read the annotation, whose docstrings now say it is what the coroutine resolves to.
- `test_firebase_adapter.py`: `TestTheDeliberateNonImplementations` claimed the concrete class
  "does not satisfy `FirebaseAdminAdapter`". My change made that false, so I corrected it. The
  assertion is unchanged and still meaningful: conformance is structural, so it is never a reason
  to inherit the Protocol.

**IN-03 folded in, as instructed.** `app/dependencies.py:117` said the class implements "the
Protocol's one reachable method". Because I annotated the same block, I rewrote the whole comment
rather than only its word count: the function is no longer "deliberately unannotated", so that
docstring changed too.

## Out of Scope — Info findings not attempted

Per instruction, `fix_scope` was Critical + Warning. These were read but not fixed:

- **IN-01** duplicate retry wrappers and SDK bodies — a refactor, deferred.
- **IN-02** `Lookup` vocabulary names a write path — rename deferred; if taken, rename all three together.
- **IN-03** stale comment in `app/dependencies.py` — **done**, folded into WR-05 as instructed.
- **IN-04** no test asserts the route makes no providerData read.
- **IN-05** tautological assertion at `test_firebase_adapter.py:270`.
- **IN-06** the "every value" assertion filters on `isinstance(value, str)`.
- **IN-07** `subject_rejected` answers 503 for a permanent condition — no fix required under D-05.
- **IN-08** one unrate-limited provider write per request — deferred to the v2.1 gateway contract.

## Notes for the next reviewer

**One defect this phase did not introduce, left standing.** WR-01's twin at `firebase.py:117-119`
(`_read`) has the identical `detail=str(error)` leak, and unlike the revoke arm it *is* reachable
from `/auth/create-user`. The review classified it as pre-existing and scoped it out, so I did not
touch it — the fix rule was to scope each change to its finding. It is a real, reachable D-07
violation and is worth its own entry rather than being lost as a footnote here.

**The `Identity` optionality gap is the source of most remaining `ty` noise.** Several of the 50
remaining diagnostics (`routers/auth.py:125,128,149,152,178,181,193,194`, `routers/chats.py:23`)
are the same shape as the one WR-02 hit: `user` and `identity` are declared optional but are
guaranteed present after `get_linked_identity`. A `LinkedIdentity` type with non-optional fields
would remove the whole class at once. That is a codebase-wide change, well beyond this phase, so I
used the codebase's existing `assert` idiom locally instead of starting it here.

**Isolation.** The agent contract asks for an isolated git worktree, and `workflow.use_worktrees`
is `true`. I worked in the main checkout instead, because the task instruction states this
directory is a submodule (`.git` is a file) and forbids creating or switching branches — and the
worktree path requires creating a temporary branch. No branch was created, nothing was pushed, and
the working tree is clean. Consequence for reproducibility: the gate numbers above come from the
main checkout, so they are reproducible directly from this tree.

---

_Fixed: 2026-09-08_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
