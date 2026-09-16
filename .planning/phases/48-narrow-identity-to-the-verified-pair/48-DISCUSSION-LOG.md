# Phase 48: Narrow Identity to the verified pair - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-16 (started 2026-09-13)
**Phase:** 48-narrow-identity-to-the-verified-pair
**Areas discussed:** Linked vs unlinked check, IdentitiesDB.resolve, Shape tests, Landing, Todos

---

## Linked vs unlinked check

| Option | Description | Selected |
|--------|-------------|----------|
| isinstance on the type | The four sites test `isinstance(identity, LinkedIdentity)` | |
| Narrow before the store | Handler and AuthService pass the store plain values | |
| A method on the classes | `AuthIdentity.linked()` returns `None` or self | |

**User's choice:** None of the three. The user asked what the point of `AuthIdentity` is once
it holds only `issuer` and `subject`, and found it would be a copy of `VerifiedClaims`.
**Notes:** Decided instead: `AuthIdentity` is deleted; two dependencies, `get_claims` returning
`VerifiedClaims` (a singular rename was proposed and withdrawn: `iss` and `sub` are two claims) and `get_identity` returning `LinkedIdentity`; the
challenge route calls `resolve` itself. The user rejected `get_user` as the name because the
dependency returns both rows, and rejected `identity: LinkedIdentity` as a parameter name
because of `identity.identity`; the parameter is `linked`.

---

## IdentitiesDB.resolve

| Option | Description | Selected |
|--------|-------------|----------|
| `LinkedIdentity \| None`, drop `allow_preauth` | `resolve` returns the rows or `None` and raises the three rejections | ✓ |
| Keep the signature | `resolve(allow_preauth) -> AuthIdentity` as today | |

**User's choice:** Drop the flag ("why do I even need this flag?"). `None` stays because the
challenge route needs "no row" as an answer, not a rejection.

---

## Shape tests

**User's choice:** Delete `TestTheIdentityShape` and the two `is None` cases; the type checker
enforces the shape. (Settled by the type decisions; not asked as its own question.)

---

## Landing

**User's choice:** Not discussed; commit granularity left to the planner.

---

## Todos

| Option | Description | Selected |
|--------|-------------|----------|
| Fold neither | Both matched on the word "phase" only | ✓ |
| Fold message-ordering | | |
| Fold secret-manager | | |

---

## Claude's Discretion

- Commit granularity and wave order.
- Docstrings on the two dependencies.
- How the accessor test asserts the two signatures after the rename.

## Deferred Ideas

- Reading `issuer` and `subject` off `linked.identity` instead of `claims` where both are
  present.
