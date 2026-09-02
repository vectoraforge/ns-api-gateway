# Phase 40: POST /auth/upgrade-anonymous - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-02
**Phase:** 40-post-auth-upgrade-anonymous
**Areas discussed:** Target-provider declaration, Where prepare lives, The three refusals, Proving
the flip works, Where the endpoint's logic lives, Proving the criteria about other endpoints, What a
no-op repeat answers, What gets written down about the divergences

---

## Target-provider declaration

### Does the client declare the target provider at all?

| Option | Description | Selected |
|--------|-------------|----------|
| No declaration | Server derives the provider solely from the Firebase Admin providerData read; Phase 37 D-12's precedent | ✓ |
| Declared at completion only | Body carries `provider`, checked against the classification, nothing persisted | |
| Re-add the persisted column | Declared and normalized at prepare, stored as immutable variant — the brief verbatim | |

**Notes:** Removes brief steps 3 and 4, keeps `operation_variant` deleted, and keeps
`supported-provider-mismatch` out of `NotLinked`'s causes.

### How does a client tell a retryable refusal from a terminal one?

| Option | Description | Selected |
|--------|-------------|----------|
| It can't, and that's fine | Client compares its own SDK state against `/auth/sync` and bounds its own retries | ✓ |
| Split into two error codes | Unambiguous signal; new client-visible code, and turns the endpoint into an oracle | |
| 409 vs 403 split | Reuses `identity_already_linked`; overloads one code with two unrelated meanings | |

### Share or duplicate the wire models?

| Option | Description | Selected |
|--------|-------------|----------|
| Share both, rename the request | `CreateUserRequest` gets a neutral name; `CompletionResponse` reused as-is | ✓ |
| Share the response, new request model | Keeps create-user's contract frozen; two identical one-field classes | |
| You decide | Planner's call, bound to the two wire shapes | |

### Keep the brief's rule that the challenge is consumed on any post-lookup rejection?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep it | One rule: once the provider was called, the handle is spent. Matches shipped create-user | ✓ |
| Leave it claimed but unconsumed on `provider_not_linked` | Saves a round-trip; breaks the one-way lifecycle | |
| You decide | | |

### What enforces the `registered_at` ↔ provider pairing across two tables?

| Option | Description | Selected |
|--------|-------------|----------|
| Sole-writer crud method plus a schema test | Structural rather than asserted; test scans for third-state rows | ✓ |
| Runtime assertion raising an `InternalError` | Catches a future bypassing writer; costs a query per success | |
| Just the crud method | Simplest; nothing fails if a later phase writes the column directly | |

### Copy the verified email on the flip?

| Option | Description | Selected |
|--------|-------------|----------|
| Copy only when stored is NULL | The brief's rule; one added guard over the existing verified-email helper | ✓ |
| Copy unconditionally when verified | Never stale; makes the stored profile a mirror of live Firebase state | |
| Don't copy | Minimal mutation surface; upgraded accounts report `email: null` forever | |

**Notes:** This endpoint is the only path in the milestone that ever fills `core.users.email` for an
upgraded account.

### Accept the unbounded Firebase Admin load from a looping client?

| Option | Description | Selected |
|--------|-------------|----------|
| Accept and flag it | As Phase 37 D-01 did; closes when the Envoy contract lands in v2.1 | ✓ |
| Skip the lookup when already registered | Removes the load; a diverged binding would report success forever | |
| Narrow limiter for this route | Reopens Phase 35 D-05 and Phase 37 D-01 | |

**Notes:** The user challenged the premise first — "Why do I need Firebase calls on every endpoint?
That doesn't sound right. What brief?" The framing was corrected: only two endpoints in the whole
application call Firebase Admin, and only on completion. The question was re-asked after that.

---

## Where prepare lives

### Where does upgrade's prepare live?

| Option | Description | Selected |
|--------|-------------|----------|
| Widen `POST /auth/challenge` | Phase 37.2's route-based partition; the challenge store needs no change | ✓ |
| A prepare mode on the endpoint | The brief verbatim; would leave two prepare conventions in the codebase | |
| You decide | | |

### What rejects a caller with no account asking for an upgrade challenge?

| Option | Description | Selected |
|--------|-------------|----------|
| One derived condition in the challenge handler | Anything but create-user with no linked identity is refused | ✓ |
| Move the rule into `ChallengesDB.issue` | Closer to the binding; makes the store learn that sign-up is special | |
| Let it issue, reject at completion | Wrong binding written, and any token holder can mint upgrade rows | |

**Notes:** An earlier framing offered a per-operation admission table and was rejected by the user —
"Does it mean I will have to keep duplicated lists of routes?" The table keyed on operation, not
path, but the objection stood and the answer was rewritten as a single derived condition.

### Does the handler need an issuable-operation list?

| Option | Description | Selected |
|--------|-------------|----------|
| Shrink the enum, list the two that work | Cleanest end state; every yes is truthful | |
| Shrink the enum, accept all four | The enum *is* the list; two operations hand out unspendable handles for one phase each | ✓ |
| Leave the enum, list the two that work | Phase stays narrow; dead values and the redundant CHECK survive | |

**Notes:** The user asked why `sync` and the other non-issuable operations were in `AuthOperation` at
all. Investigation showed they existed only for `audit.auth_events`, deleted by Phase 37.1, leaving
`core.auth_operation` with exactly one consumer. The user then raised the deciding concern — "I'm
worried that I will have to keep 2 lists (actually 3 with the database enum) in sync" — and the
recommendation was changed from a two-entry list to accepting all four.

### Should FastAPI route metadata derive the issuable set?

| Option | Description | Selected |
|--------|-------------|----------|
| Derive from route metadata | `openapi_extra`, or a marker decorator read back through `route.endpoint` | |
| Keep the check in the handler | | ✓ |

**Notes:** Raised by the user. Both mechanisms were verified working against live FastAPI. The
pattern is ordinary — Django's `csrf_exempt`, Starlette's `requires` — but it configures one
endpoint from metadata on others, so a forgotten marker fails silently, and it needs permanent
machinery (startup build, app-state stash, dependency, forgotten-marker test). Shrinking the enum
removed the need entirely. The user asked directly whether the approach was normal by industry
standards and whether to prefer it; the answer was that it is normal but not worth it at four
operations.

---

## The three refusals

### How should the three refusals be expressed in code?

| Option | Description | Selected |
|--------|-------------|----------|
| Three separate classes | Class name becomes the log event name, so three distinct internal results for free | ✓ |
| One new class with a field | Two new things instead of three; both serious cases log under one name | |
| Reuse the existing class for all three | Nothing new; one name would cover two unrelated situations | |

**Notes:** The first attempt at this question was rejected outright — "I have no idea what you're
talking about. At least make an introduction before asking." It was re-asked after a plain-English
explanation of what the three refusals are and why the client sees the same answer for all three.

### What should the two serious refusal log lines carry?

| Option | Description | Selected |
|--------|-------------|----------|
| Our row id plus stored and live provider names | Find the row and know the kind of disagreement without a query | ✓ |
| Our row id and user id only | Minimum; patterns invisible without querying the database | |
| Add the provider account id too | Most complete; copies the user's real Google/Apple identifier into logs | |

### What level should the not-yet-linked refusal log at?

| Option | Description | Selected |
|--------|-------------|----------|
| Drop it to info | Keeps the two serious cases visible among warnings | |
| Log nothing | Quietest; loses the ability to distinguish it from any other 403 | |
| Leave all three at warning | Consistent with every other refusal in the codebase | ✓ |

### Look for a conflicting row before writing, or just write and catch?

| Option | Description | Selected |
|--------|-------------|----------|
| Only catch the database's refusal | One path, always right; the database is the only race-free answer | ✓ |
| Look first, and catch as well | More direct at the common case; two paths saying the same thing | |
| You decide | | |

**Notes:** The user's first response was a concern rather than a choice — "Does it mean I will have
to parse the DB error, extract the affected constraint, compare it with a stored string which I will
have to maintain and keep in sync with the DB?" Investigation of the repo answered it: production
code catches the typed error and names nothing, and where a test needs a constraint name it asks the
database for the live name by column set. No parsing and no stored strings anywhere.

Also corrected during this area: an earlier claim that Phase 37 shipped a savepoint around the
business write. It did not — a test actively forbids it — and the shipped rollback-then-consume
design is what this phase follows.

---

## Proving the flip works

### How much real Firebase contact should this phase's tests have?

| Option | Description | Selected |
|--------|-------------|----------|
| One real test on the refusal path | Real anonymous user, real empty answer, real refusal; Phase 37's split | |
| Everything against the fake | Fast, no credentials; nothing ever calls Firebase for real | |
| Add a real Google-linked account too | Covers the successful flip for real | ✓ |

**Notes:** The user asked what "stand-in" meant; the term was replaced with "fake" and the existing
`scripted_firebase_adapter` fixture shown. After the choice, the cost estimate was corrected: no
per-run OAuth flow is needed, because the Admin SDK can mint a custom token for the UID which
Firebase exchanges for an ID token. `create_custom_token` was verified present in the installed
firebase-admin 7.3.0. The Firebase account is also read-only for the test, since the flip mutates
rows in this database rather than in Firebase.

### With the real account covering the success path, what does the fake still cover?

| Option | Description | Selected |
|--------|-------------|----------|
| Everything the real account can't | Refusals, drift conflict, taken-account conflict, idempotent repeat | ✓ |
| Add a real anonymous account for the refusal too | Slightly more real coverage; a second piece of hand-made test data | |
| You decide | | |

### Does this phase test that the row lock blocks a concurrent upgrade?

| Option | Description | Selected |
|--------|-------------|----------|
| Take the lock, don't test the blocking | The claim already serializes; both writers would write identical values | ✓ |
| Prove it blocks, in the schema suite | Proves the lock works; slow and flaky for a collision that writes the same values twice | |
| Don't take the lock at all | Simplest; departs from the specification and needs re-deriving later | |

---

## Where the endpoint's logic lives

| Option | Description | Selected |
|--------|-------------|----------|
| Add upgrade to the existing service | Shared sequence stays in one place; create-user's shipped code is edited | ✓ |
| Extract the shared part, two thin services | Neither endpoint inside the other; largest change to shipped code | |
| A separate service, nothing shared | Smallest blast radius; the challenge sequence exists twice | |

---

## Proving the criteria about other endpoints

| Option | Description | Selected |
|--------|-------------|----------|
| One flow test covering all three | Upgrade, then call both read endpoints and compare tokens either side | ✓ |
| Assert on the rows, not the endpoints | Cheaper; proves the database is right, not what the criteria say | |
| Don't test them | True by construction; a stated criterion nothing checks | |

---

## What a no-op repeat answers

| Option | Description | Selected |
|--------|-------------|----------|
| Identical to a real flip | Client only needs to know the backend now reports the registered provider | ✓ |
| Add a flag saying nothing changed | Useful for diagnostics; a contract field clients may start branching on | |
| Different status code for a no-op | Distinguishable without a field; two statuses for one outcome | |

---

## What gets written down about the divergences

| Option | Description | Selected |
|--------|-------------|----------|
| Amend the two upgrade requirements | The three decisions new to this phase, plus a note that the brief's rate-limit and audit obligations are already dead | ✓ |
| Note the enum shrink under the schema requirement | Explains a migration diff showing a shape that never ran anywhere | ✓ |
| Reword the roadmap criterion about modes | "Prepare and completion modes" describes the design Phase 37.2 replaced | ✓ |
| Edit the phase brief itself | Would make it agree with the code; breaks the verbatim pattern for every other brief | |

---

## Claude's Discretion

- The names of the two new exception classes and their placement in `errors.py`, bound by the
  requirement that they snake-case to the brief's internal result names.
- The new neutral name for `CreateUserRequest`, and whether the rename lands in its own commit.
- The flip crud method's name and signature, and how the locked rows reach it.
- Whether lock-and-revalidate is one joined statement or two ordered ones.
- How `AuthService` accommodates a second completion internally.
- Test placement and depth, and whether the enum shrink lands in its own commit.

## Deferred Ideas

- A single test asserting each Python enum's values equal its database type's labels.
- Cleaning up create-user's nested exception block to match the no-nesting rule.
- Operator tooling for a drifted identity row.
- Revisiting Phase 37's registered-flow coverage once a real Google-linked account exists.
- A second permanently anonymous Firebase account for the refusal path.
- `PROJECT.md` says Python 3.12; the environment runs 3.14.7.
- Restoring rate limiting to the auth surface (v2.1, with the Envoy contract).
- Secret Manager integration, now also touching the service-account signing question.

### Reviewed Todos (not folded)

- `admission-holds-a-db-connection` — LLM admission and the quota charge.
- `breaker-check-moved-to-admission` — LLM provider resilience.
- `message-ordering-is-unspecified` — chats.
- `secret-manager-integration` — config; declined for the eighth consecutive phase.
