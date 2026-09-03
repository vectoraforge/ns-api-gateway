# Phase 42: POST /auth/claim-registered-grant - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-03
**Phase:** 42-post-auth-claim-registered-grant
**Areas discussed:** The device gate (bit1), Cross-account uniqueness, Firebase confirmation, Refusal & repeat contract

---

## The device gate (bit1)

| Option | Description | Selected |
|--------|-------------|----------|
| Burn bit1 too | Read bit1; set → 403 device_grant_exhausted; write bit1 before the transaction. One registered grant per iPhone. | ✓ |
| No device check | The Google/Apple account alone anchors it. N accounts on one phone = N×50 credits. | |

| Option | Description | Selected |
|--------|-------------|----------|
| Skip the check on conversion | Conversion issues no new allowance; the allowance already cost bit0. No Apple call. | ✓ |
| Check bit1 on every claim | One path, brief-faithful; a converting user on a device with bit1 set is refused. | |

| Option | Description | Selected |
|--------|-------------|----------|
| One token, same as Phase 41 | One DeviceCheck token, always required; 422 if absent; unused on conversion. | ✓ |
| Two tokens, as the brief asks | Separate query and update tokens; splits the two routes' wire shapes. | |

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse Phase 41's code and shape | 403 device_grant_exhausted, same copy, no device state in the body. | ✓ |
| A distinct code for this route | Lets a client tell which bit was hit; one more code; tells a prober which bit. | |

**User's choice:** all four recommended options.
**Notes:** none.

---

## Cross-account uniqueness

**Trail.** The first question was rejected twice: once for "ELI5", once because the explanation
contradicted itself ("you said this needs a second Firebase id, then you check the account id?").
The answer distinguished the Firebase uid (`subject`) from the Google/Apple id (`provider_uid`).
The user then asked: "Why not just make `provider_uid` unique?" It already is —
`ix_external_identities_provider_account`. Claude's recommendation to build `provider_accounts`
was withdrawn as wrong: the hole it closed does not exist.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep the list, real account id | Write provider_accounts + gate_consumptions; add account_already_claimed. | withdrawn |
| Keep the list, scrambled id | Query the existing idp_account_hash index; breaks on key rotation. | |
| Keep no list | Per-user index + free_grant_consumed_at + the existing unique index on external_identities. | ✓ |

The remaining question was the anti-abuse row's hash, which the CHECK requires for a registered grant.
The user asked, in turn: why was the keyring dropped; how is `access_grants_anti_abuse` used;
explain it architecturally, not by implementation; how can it hold a receipt for an Apple bit that
has no id; does the claim compare the hash; is the table only record keeping; was
`provider_account_gate_consumptions` introduced to do the anti-abuse table's job; do I need to
hash `provider_uid` at all; can I delete all three tables and lose nothing.

| Option | Description | Selected |
|--------|-------------|----------|
| Name the device | Record native_claim_provider = ios_devicecheck; needs a CHECK edit. | |
| Name the account | Record the HMAC with key version 1; one new secret. | |
| Record nothing | Row with grant_id, source, created_at only; needs a CHECK edit. | |
| Delete the three tables | User's own option. The receipt duplicates facts held elsewhere; the controls are the indexes and Apple's bits. | ✓ |

**User's choice:** "Do it" — delete `core.access_grants_anti_abuse`, `core.provider_accounts`,
`core.provider_account_gate_consumptions`. No HMAC. `provider_uid` stays raw.
**Notes:** The user asked for ASD-STE100 and for architecture rather than implementation detail.

---

## Firebase confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| Stored row only | provider must be google/apple on the stored row; no Firebase call. | ✓ |
| Live Firebase read on every claim | getUser through the retry-wrapped lookup, compared with the stored binding. | |

**User's choice:** Stored row only.
**Notes:** none.

---

## Refusal & repeat contract

| Option | Description | Selected |
|--------|-------------|----------|
| No field | 403 operation_not_allowed with no fields, as Phase 41. | ✓ |
| Add held_grant_ends_at | The brief's field; new information (Entitlement has no ends_at). | |

| Option | Description | Selected |
|--------|-------------|----------|
| 403 operation_not_allowed | Mirror of ClaimantNotAnonymous; no new code. | ✓ |
| 403 verification_required | The brief's code; one code for one case. | |

| Option | Description | Selected |
|--------|-------------|----------|
| Move unchanged | monthly_period and monthly_used copied exactly on conversion. | ✓ |
| Reset to 0 | A one-time incentive of up to 10 credits; one special case. | |

**User's choice:** all three recommended options.
**Notes:** none.

---

## Todos

| Option | Description | Selected |
|--------|-------------|----------|
| Neither | Both matched on generic keywords; both declined in Phase 41. | ✓ |
| message-ordering (0.6) | chats; unrelated. | |
| secret-manager (0.2) | config; declined nine phases running. | |

## Claude's Discretion

How `AuthService` grows the completion; the crud writer shape; the request model name; the
`ClaimRefused` leaf name; whether the schema deletion is its own plan wave; how the migration
edit is verified; test placement and depth.

## Deferred Ideas

The web branch's account record table; the Android and web branches; `held_grant_ends_at`;
`verification_required`; a real-device Apple round trip; auth-surface rate limiting; the
enum-versus-type label test.
