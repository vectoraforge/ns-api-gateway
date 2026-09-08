# Phase 46: POST /auth/sign-out-all - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-08
**Phase:** 46-post-auth-sign-out-all
**Areas discussed:** The revocation call and its retry budget, What the client gets back, Closing the forward flags in REQUIREMENTS.md

---

## Todos (cross-reference step)

| Option | Description | Selected |
|--------|-------------|----------|
| Fold neither | message-ordering is a chats todo matched on "phase"; secret-manager adds no secret here | ✓ (final) |
| Fold message-ordering | Message ordering unspecified on read and LLM history | selected, then withdrawn |
| Fold secret-manager-integration | Retrieve all secrets via google.cloud.secretmanager | selected, then withdrawn |

**User's choice:** Both folded at first; reversed with "I changed my mind. Do not fold the 2 todos into this phase."
**Notes:** Claude noted that secret-manager's "why now" (HMAC key material) is stale since the audit writer was deleted.

---

## The revocation call and its retry budget

| Option | Description | Selected |
|--------|-------------|----------|
| Second method on FirebaseAdminLookup | revoke_refresh_tokens beside get_user_provider_data; Protocol grows by one method; one app.state object, one fake | ✓ |
| A new class beside it | Own Protocol, own app.state entry, own fake; keeps "Lookup" honest | |

**User's choice:** Second method on FirebaseAdminLookup.

| Option | Description | Selected |
|--------|-------------|----------|
| Three, the same as getUser | Reuse the tenacity policy and constant; ~48s worst case | ✓ |
| Two | Separate constant; ~32s worst case | |
| One, no in-request retry | Client is the retry path; ~16s worst case | |

**User's choice:** Three.
**Notes:** Moved to next area after two questions; the retryable/definitive split and the handler shape went to Claude's discretion.

---

## What the client gets back

| Option | Description | Selected |
|--------|-------------|----------|
| 204 No Content | No body; no database read on success | ✓ |
| 200 with an empty JSON object | Uniform parse with other auth routes | |
| 200 with the sync body | Same shape as claim and restore; costs a read | |

**User's choice:** 204 No Content.

| Option | Description | Selected |
|--------|-------------|----------|
| Own leaf class, existing code | RevocationUnconfirmed at 503 verification_temporarily_unavailable; own log event name | ✓ |
| Reuse Unavailable with a stage | Same code; event "unavailable" with stage=token_revocation | |
| Generic 503 service_unavailable | The LLM-outage code | |

**User's choice:** Own leaf class, existing code.

| Option | Description | Selected |
|--------|-------------|----------|
| 401 auth_required via UserNotFound | Same as create-user; flagged conflict against the brief | ✓ |
| 503 unconfirmed | No conflict; client retries for up to an hour | |

**User's choice:** 401 via UserNotFound.

| Option | Description | Selected |
|--------|-------------|----------|
| One INFO line with the identity row id | sign_out_all_confirmed with identity_row_id; the one-way door is findable | ✓ |
| No extra line, as 38 D-02 | Middleware request line is the record | |

**User's choice:** One INFO line with the identity row id.

---

## Closing the forward flags in REQUIREMENTS.md

| Option | Description | Selected |
|--------|-------------|----------|
| No label, close the flag | Not challenge-bearing, no audit row, no reader; migration not edited | ✓ |
| Re-add 'sign_out_all' to core.auth_operation | Edit the single migration for a value nothing reads | |

**User's choice:** No label, close the flag.

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 45 model, in full | Dated entries, two flags closed, one flagged conflict, dead-obligations inventory, uncounted divergence, counts re-derived, criterion 3 rewritten | ✓ |
| Minimal | Mark met, close flags in one line each, rewrite criterion 3 | |

**User's choice:** Phase 45 model, in full.

---

## Closing

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context | Write CONTEXT.md | (second round) ✓ |
| Explore more gray areas | Test shape, anonymous one-way door wording | (first round) ✓ |

**User's choice:** "Explore more gray areas" first; after the todo reversal, "Write the context now".

## Claude's Discretion

- Class and constant renames; stage strings; INFO event name.
- Retry wrapper shape; the retryable versus definitive split as recorded in D-02.
- Handler declaration order; OpenAPI summary and description.
- Test shape on the 43/44/45 model; whether to add the zero-statement session stand-in.
- Plan wave order.

## Deferred Ideas

- Gateway rate limits on the auth surface (v2.1).
- `/auth` paths in the gateway HTTPRoutes.
- Phase 44.1 restructure.
- Enum-label equality test.
- Both reviewed todos, not folded.
