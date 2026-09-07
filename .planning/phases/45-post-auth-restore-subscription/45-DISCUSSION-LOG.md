# Phase 45: POST /auth/restore-subscription - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-07
**Phase:** 45-post-auth-restore-subscription
**Areas discussed:** The body and the surface gate, Apple's live check, The write path, Rejections and the response

---

## Todos

| Option | Description | Selected |
|--------|-------------|----------|
| Neither | Both declined in every prior phase | ✓ |
| secret-manager-integration | Relevant only if an Apple API key were added | |
| message-ordering-is-unspecified | Chats; keyword match only | |

**User's choice:** Neither.

---

## The body and the surface gate

| Option | Description | Selected |
|--------|-------------|----------|
| provider + restore_proof | Two fields; the provider picks the verifier, a wrong declaration cannot verify | ✓ |
| restore_proof only, server sniffs the shape | A Play token has no defined shape; a fall-through rule | |
| Two named fields, exactly one set | Same information over two optional fields | |

**User's choice:** provider + restore_proof.

| Option | Description | Selected |
|--------|-------------|----------|
| By the proof | Unknown store → 403 operation_not_allowed; failed proof → proof_rejected; nothing else checked | ✓ |
| Also use the stored platform mark | `native_claim_platform` when set; NULL for most; refuses a platform switch | |
| Ask the app to say which platform it is | A header anyone can send | |

**User's choice:** By the proof. The first phrasing of this question was refused with "Speak plain
English"; it was re-asked without layer names.

| Option | Description | Selected |
|--------|-------------|----------|
| No, refuse it | The brief's rule: a lifetime tie on a device-bound account is a risk | |
| Yes, allow it | Any signed-in account may restore | ✓ (after discussion) |

**User's choice:** Allow anonymous restore, with transfers capped at one move per month, tied to
the subscription the proof names.
**Notes:** The user asked why anonymous cannot restore, rejected an answer that said "forever",
and established through questions that: the tie is forever only if built that way; the brief
deleted the transfer cap; receipt theft is a risk of restore in any form; a cap bounds sharing
rather than removing it. The decision followed from those answers.

---

## Apple's live check

| Option | Description | Selected |
|--------|-------------|----------|
| Trust proof + local row | No Apple key, no live call; refunds reach the row by webhook; blind spot accepted | ✓ |
| Call Apple live | App Store Server API key, one call per adoption, closes the blind spot | |

**User's choice:** Trust proof + local row.

| Option | Description | Selected |
|--------|-------------|----------|
| The signed transaction | StoreKit 2 JWS, verified with the existing verifier | ✓ |
| The app receipt | StoreKit 1; needs the API key; deprecated path | |

**User's choice:** The signed transaction.
**Notes:** Google's one Play call serving both proof and live state was stated as Claude's
discretion and not questioned.

---

## The write path

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse the webhook's writer | Term model, expire-then-insert, own counter, repeat writes nothing | ✓ |
| Follow the brief | Open-ended grant, reactivate in place; a second grant shape | |

**User's choice:** Reuse the webhook's writer.

| Option | Description | Selected |
|--------|-------------|----------|
| Conditional update | Grant locks in the existing order, then an UPDATE whose WHERE restates the pre-lock read | ✓ |
| Lock the subscription row first | The brief's order; a new lock tier ahead of the grants | |

**User's choice:** Conditional update.

| Option | Description | Selected |
|--------|-------------|----------|
| Only a move between accounts | Adoption and same-account do not count; UTC calendar month | ✓ |
| Every restore that changes the owner | The first adoption counts too | |

**User's choice:** Only a move between accounts.

---

## Rejections and the response

| Option | Description | Selected |
|--------|-------------|----------|
| Two new codes | restore_not_found, restore_transfer_rejected; reuse proof_rejected and verification_temporarily_unavailable | ✓ |
| No new codes | Everything after the proof is operation_not_allowed | |
| All six from the brief | Four would have no trigger | |

**User's choice:** Two new codes.

| Option | Description | Selected |
|--------|-------------|----------|
| The sync body | SyncResponse after commit, no-store, as the claim routes do | ✓ |
| A restore-specific body | A new shape naming the branch | |

**User's choice:** The sync body.

---

## Claude's Discretion

- The restore service's home and name; the Apple status rule for a bare transaction; how the
  Play class is called without webhook fields; the two-user grant lock statement; the HTTP
  statuses and leaf names of the two new codes; the request model's name; the Apple verifier's
  accessor; test shape; plan wave order. Listed in CONTEXT.md.
- D-09 (an owner, once set, is kept by ingestion) was derived by Claude from the transfer decision
  and stated to the user at wrap-up, not asked.

## Deferred Ideas

- Apple live status from the App Store Server API; the renewal-info JWS as a second Apple proof
  field; dropping `restore_bound_user_id`; gateway rate limits on the auth surface; `/auth` paths
  in the gateway HTTPRoutes; the Android and web claim branches; Phase 44.1; the enum-label test.
