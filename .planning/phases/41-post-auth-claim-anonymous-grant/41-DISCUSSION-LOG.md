# Phase 41: POST /auth/claim-anonymous-grant - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-02
**Phase:** 41-post-auth-claim-anonymous-grant
**Areas discussed:** The device gate, Who claims and repeats, The response body, Proving the race, The two folded todos

---

## Todo cross-reference

| Todo | Score | Folded |
|------|-------|--------|
| admission-holds-a-db-connection | 0.6 | ✓ |
| breaker-check-moved-to-admission | 0.6 | ✓ |
| message-ordering-is-unspecified | 0.4 | |
| secret-manager-integration | 0.2 | |

---

## The device gate

### How much of the device gate ships in this phase?

| Option | Description | Selected |
|--------|-------------|----------|
| Database rule only | One free grant per account via the existing unique index and marker; no vendor call; anti-abuse tables become dead schema | |
| One native gate, iOS DeviceCheck | Apple's per-device bit read and written server-to-server; Android and web get no anonymous grant | |
| All three as the brief writes it | DeviceCheck, Play Integrity with Device Recall, Turnstile plus Firebase read and HMAC hash | ✓ (initially) |

**User's choice:** "Other" first — asked whether the gates belong in this phase at all and why the question was being asked; then asked what "capped per account" meant and objected to the phrasing. Then: "Build all three."
**Notes:** The brief scopes all three gates here; the roadmap and ANONGRANT-01…03 never mention a proof. No later phase owns them. "Free grant capped per account" was rejected as jargon and restated as: without a device check, anyone can sign in anonymously again and claim again.

### How is the work cut?

| Option | Description | Selected |
|--------|-------------|----------|
| One phase, one plan per vendor | Shared endpoint and transaction built once, each vendor adapter its own plan wave | |
| Split by platform into 41, 41.1, 41.2 | iOS, then Android, then web, each a working route for one platform | |
| Web first, native later | Cloudflare and Firebase branch first, native gates in 41.1 | |

**User's choice:** "I changed my mind. Build 41 with iOS only, Android and web are deferred to another milestone." (supersedes "Build all three")

### How does the Apple call get tested?

| Option | Description | Selected |
|--------|-------------|----------|
| Fake in the suite, real Apple by hand | Scripted fake drives the endpoint; adapter unit-tested against Apple's documented payloads | ✓ (by consequence) |
| Fake in the suite, plus a required phone check | Same, but acceptance requires a real iPhone build claiming a grant | |

**User's choice:** "There is no iOS app yet, what are you talking about?" — then "Yes" to: scripted fake in the suite, adapter unit tests against Apple's documented shapes, first real round trip when an app exists.
**Notes:** The second option was withdrawn as nonsense once the fact was stated.

### Which comes first after the claim: asking Apple, or checking the database?

| Option | Description | Selected |
|--------|-------------|----------|
| Database first | Cheap query refuses an ineligible account before any Apple round trip; flagged conflict with the brief's order | ✓ |
| Apple first, as the brief writes it | Every attempt costs an Apple query; already-claimed device always answers device_grant_exhausted | |

**User's choice:** Database first (Recommended)

### Where do Apple's DeviceCheck credentials live?

| Option | Description | Selected |
|--------|-------------|----------|
| .env, like the other secrets | Key ID, team ID, private key beside DB_*, JWT_*, OPENAI_API_KEY; PEM base64 or mounted-file path | ✓ |
| config.yaml, tracked in git | Zero provisioning; a private key committed and readable in history forever | |

**User's choice:** .env, like the other secrets (Recommended)

---

## Who claims, and repeats

### Who may claim the grant through the iPhone gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Anonymous and registered accounts | As the brief writes it; registered iPhone user takes the 10-credit grant now, Phase 42's 50 supersedes it | |
| Anonymous accounts only | Registered users wait for Phase 42; one claimant class; flagged conflict | ✓ |

**User's choice:** Anonymous accounts only

### What does a repeat claim get when the account already holds its active anonymous grant?

| Option | Description | Selected |
|--------|-------------|----------|
| 200, same body as a fresh claim | Repeat never reaches Apple, writes nothing; two refusal states remain (consumed-but-inactive, other active grant) | ✓ |
| 403 operation_not_allowed, as the brief writes it | A claim is a state change; the client reconciles through /auth/sync | |

**User's choice:** 200, same body as a fresh claim (Recommended)

---

## The response body

### What does a successful claim return?

| Option | Description | Selected |
|--------|-------------|----------|
| Exactly what /auth/sync returns | SyncResponse reused as is; identity_provider redundant here | ✓ |
| The entitlement block alone | New model wrapping the six-field Entitlement | |
| {identity_provider}, like the other completions | Existing CompletionResponse; client calls sync afterwards | |

**User's choice:** Exactly what /auth/sync returns (Recommended)

### Do the two Apple-side refusals get their own client-visible codes?

| Option | Description | Selected |
|--------|-------------|----------|
| Two new codes: proof_rejected and device_grant_exhausted | Both 403; vocabulary 16 → 18; verification_required not added | ✓ |
| Fold both into operation_not_allowed | No new codes; app cannot distinguish the cases | |

**User's choice:** Two new codes (Recommended)

---

## Proving the race

### How is "two simultaneous claims yield one grant" proven?

| Option | Description | Selected |
|--------|-------------|----------|
| A live two-connection race in tests/schema | Modelled on test_create_race.py; one grant and one usage row afterwards | ✓ |
| Unit level only | Assert the index exists and the crud converts the refusal | |

**User's choice:** A live two-connection race in tests/schema (Recommended)

### What does the loser of the race get back?

| Option | Description | Selected |
|--------|-------------|----------|
| 200, as a repeat would | Database refuses the second insert, rollback, re-read, return the winner's grant | ✓ |
| 403 operation_not_allowed | The refusal becomes the shared 403; client syncs | |

**User's choice:** 200, as a repeat would (Recommended)

---

## The two folded todos

### Is the circuit breaker consulted once at admission, or before every attempt?

| Option | Description | Selected |
|--------|-------------|----------|
| Before every attempt | before_call() at the top of each attempt as well as at admission; dead except becomes reachable | ✓ |
| Once at admission, and say so | Delete the unreachable except, rewrite AGENTS.md § Resilience | |

**User's choice:** Before every attempt (Recommended)

### Where does the quota charge sit relative to the provider permit?

| Option | Description | Selected |
|--------|-------------|----------|
| Charge first, then take the permit | admission() keeps breaker + in-flight slot; semaphore moves into ainvoke() around the retry loop | ✓ |
| Leave the structure, widen the pool | Keep the charge inside admission; raise db.pool_size | |
| Charge before admission | Breaks the "503 spends nothing" property twenty tests assert | |

**User's choice:** Charge first, then take the permit (Recommended)
**Notes:** The user interrupted to ask why one request holds two connections: the request session from get_db holds one from its first query to the end of the handler; the quota charge opens its own short session so the grant lock is released by commit before the provider round trip.

### Raise db.pool_size?

| Option | Description | Selected |
|--------|-------------|----------|
| Raise to 12 | resilience.pool_size × 2 + 2 per STATE.md A-15; independent numbers, relation as a comment | ✓ |
| Derive it from resilience.pool_size | Computed default with a validator | |
| Leave it at 5 | Accept the exhaustion STATE.md records | |

**User's choice:** Raise to 12 (Recommended)

---

## Claude's Discretion

The DeviceCheck seam's module, Protocol placement, HTTP client and signing; the 422-versus-proof_rejected default for absent tokens; how AuthService grows a completion without a Firebase read; the request model; the grant writer and the AccessGrantAntiAbuse model; how identity and user rows are revalidated behind the grant locks; test placement; whether the folded todos are their own plan wave.

## Deferred Ideas

Android branch; web branch (Turnstile, Firebase read, HMAC keyring, provider_accounts, gate consumptions, verification_required); registered claimants on the iOS gate; dev/simulator bypass; real-device Apple check; rate limiting and an Apple call budget; deriving db.pool_size; the enum-mirror test; operator tooling for a burned device slot.
