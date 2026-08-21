# Phase 34: PostgreSQL 17 Inventory Capture

**Captured:** 2026-08-20
**Plan:** 34-03 task 1
**Purpose:** the single source of every expected constant in `tests/schema/test_inventory.py`.
Task 3 copies from this file, never from `34-RESEARCH.md` -- RESEARCH.md's Code Example 4 was
captured on PostgreSQL 16.2 and is retained here only as the reconciliation baseline.

**Closes:** RESEARCH.md assumption A1 and open question OQ-1 (orchestrator DIRECTIVE-4).

---

## Capture Environment

| Fact | Value |
|------|-------|
| `SHOW server_version` | `17.11 (Debian 17.11-1.pgdg13+2)` |
| Database | the `DB_NAME` database from `.env`, with `migrations/20260818_01_initial-release.sql` applied by plan 34-02 |
| Default `search_path` of the reading session | `"$user", public` |
| Queries used | `34-RESEARCH.md` Code Example 3 (`ENUMS`, `TABLES`, `INDEXES`, `USER_TRIGGERS`, `VIEWS`, `MATVIEWS`, `GONE`), unmodified |

The observed `server_version` begins with `17`, so this capture is on the version the spec targets.
Plan 34-01 observed the same string.

---

## 1. Enum Types -- 11 in `core`, labels in `enumsortorder`

Labels are listed in `enumsortorder`, which is the order `00-schema.md` section 3 declares and the
order task 3 asserts. They are **not** an unordered set.

#### `core.access_grant_source` -- 4 labels

 1. `subscription`
 2. `anonymous_device_grant`
 3. `registered_account_grant`
 4. `manual`

#### `core.access_grant_status` -- 3 labels

 1. `active`
 2. `revoked`
 3. `expired`

#### `core.auth_event_result` -- 44 labels

 1. `succeeded`
 2. `challenge_expired`
 3. `challenge_consumed`
 4. `challenge_identity_mismatch`
 5. `challenge_operation_mismatch`
 6. `challenge_not_found`
 7. `invalid_external_jwt`
 8. `preauth_identity_not_allowed`
 9. `identity_already_linked`
10. `provider_not_linked`
11. `provider_transition_not_allowed`
12. `provider_account_already_linked`
13. `blocked_user`
14. `historical_identity`
15. `invalid_restore_proof`
16. `proof_malformed`
17. `store_transaction_already_linked`
18. `restore_subscription_unlinked`
19. `restore_subscription_not_entitled`
20. `restore_purchase_uuid_unknown`
21. `restore_purchase_uuid_mismatch`
22. `restore_subscription_grant_owner_mismatch`
23. `restore_branch_inconsistent`
24. `restore_store_state_unverified`
25. `restore_source_user_inactive`
26. `restore_destination_anonymous`
27. `restore_destination_already_entitled`
28. `anti_abuse_already_claimed`
29. `native_claim_already_claimed`
30. `native_claim_unavailable`
31. `native_claim_write_failed`
32. `devicecheck_read_budget_exhausted`
33. `devicecheck_write_budget_exhausted`
34. `device_recall_read_budget_exhausted`
35. `device_recall_write_budget_exhausted`
36. `firebase_user_unresolved`
37. `idp_account_not_eligible`
38. `firebase_lookup_unavailable`
39. `verification_temporarily_unavailable`
40. `idp_account_already_claimed`
41. `registered_grant_destination_incompatible`
42. `policy_rejected`
43. `revocation_unconfirmed`
44. `internal_error`

#### `core.auth_operation` -- 7 labels

 1. `create_user`
 2. `upgrade_anonymous_to_registered`
 3. `claim_anonymous_grant`
 4. `claim_registered_grant`
 5. `restore_subscription`
 6. `sign_out_all`
 7. `sync`

#### `core.chat_role` -- 2 labels

 1. `human`
 2. `ai`

#### `core.gate_consumption_kind` -- 2 labels

 1. `web_anonymous_gate`
 2. `registered_account_grant`

#### `core.identity_provider` -- 3 labels

 1. `anonymous`
 2. `google`
 3. `apple`

#### `core.identity_state` -- 2 labels

 1. `active`
 2. `historical`

#### `core.native_claim_provider` -- 2 labels

 1. `ios_devicecheck`
 2. `android_play_integrity`

#### `core.subscription_provider` -- 2 labels

 1. `apple`
 2. `google_play`

#### `core.subscription_status` -- 5 labels

 1. `active`
 2. `grace_period`
 3. `billing_retry`
 4. `expired`
 5. `revoked`


---

## 2. Tables

**`core` -- 15**

- `access_grants`
- `access_grants_anti_abuse`
- `access_tiers`
- `auth_challenges`
- `chats`
- `external_identities`
- `manual_grant_issuances`
- `messages`
- `provider_account_gate_consumptions`
- `provider_accounts`
- `store_purchase_tokens`
- `store_purchases`
- `subscriptions`
- `user_monthly_usage`
- `users`

**`audit` -- 2**

- `auth_events`
- `subscription_events`

---

## 3. Indexes -- 54 total (46 in `core`, 8 in `audit`)

Predicate column shows `pg_get_expr(indpred, indrelid)` read under the **default** `search_path`
(`"$user", public`) -- see section 4 for why that qualifier matters.

### `core` (46)

| Index | Unique | Predicate |
|-------|--------|-----------|
| `access_grants_anti_abuse_pkey` | yes | (none) |
| `access_grants_anti_abuse_registered_account_grant_id_key` | yes | (none) |
| `access_grants_id_source_key` | yes | (none) |
| `access_grants_pkey` | yes | (none) |
| `access_tiers_pkey` | yes | (none) |
| `auth_challenges_challenge_id_key` | yes | (none) |
| `auth_challenges_pkey` | yes | (none) |
| `chats_pkey` | yes | (none) |
| `external_identities_issuer_subject_key` | yes | (none) |
| `external_identities_pkey` | yes | (none) |
| `external_identities_user_id_key` | yes | (none) |
| `ix_access_grants_anti_abuse_idp_account_hash` | no | `(idp_account_hash IS NOT NULL)` |
| `ix_access_grants_one_active_per_user` | yes | `(status = 'active'::core.access_grant_status)` |
| `ix_access_grants_one_free_grant_per_user_source` | yes | `(source = ANY (ARRAY['anonymous_device_grant'::core.access_grant_source, 'registered_account_grant'::core.access_grant_source]))` |
| `ix_access_grants_one_per_subscription` | yes | `((source = 'subscription'::core.access_grant_source) AND (subscription_id IS NOT NULL) AND (status = 'active'::core.access_grant_status))` |
| `ix_access_grants_subscription` | no | `(subscription_id IS NOT NULL)` |
| `ix_access_grants_user_active` | no | (none) |
| `ix_auth_challenges_expires_at` | no | (none) |
| `ix_chats_user_id` | no | (none) |
| `ix_external_identities_provider` | no | (none) |
| `ix_external_identities_provider_account` | yes | `(provider_uid IS NOT NULL)` |
| `ix_external_identities_user_active` | no | (none) |
| `ix_external_identities_user_id` | no | (none) |
| `ix_gate_consumptions_grant_id` | no | (none) |
| `ix_messages_chat_id` | no | (none) |
| `ix_store_purchase_tokens_user_id` | no | (none) |
| `ix_store_purchases_provider_identity_value` | no | (none) |
| `ix_store_purchases_purchase_user_id` | no | (none) |
| `ix_subscriptions_provider_external_id` | yes | (none) |
| `ix_subscriptions_user_id` | no | (none) |
| `ix_users_registered_at` | no | (none) |
| `manual_grant_issuances_grant_id_key` | yes | (none) |
| `manual_grant_issuances_pkey` | yes | (none) |
| `messages_pkey` | yes | (none) |
| `provider_account_gate_consumptions_pkey` | yes | (none) |
| `provider_accounts_pkey` | yes | (none) |
| `provider_accounts_provider_provider_uid_key` | yes | (none) |
| `store_purchase_tokens_provider_identity_value_key` | yes | (none) |
| `store_purchase_tokens_user_id_provider_key` | yes | (none) |
| `store_purchases_pkey` | yes | (none) |
| `store_purchases_provider_external_id_key` | yes | (none) |
| `subscriptions_id_user_id_key` | yes | (none) |
| `subscriptions_pkey` | yes | (none) |
| `subscriptions_product_entitled_subscription_id_key` | yes | (none) |
| `user_monthly_usage_pkey` | yes | (none) |
| `users_pkey` | yes | (none) |

### `audit` (8)

| Index | Unique | Predicate |
|-------|--------|-----------|
| `auth_events_pkey` | yes | (none) |
| `ix_auth_events_actor_issuer_subject_hash` | no | (none) |
| `ix_auth_events_challenge_row_id` | no | (none) |
| `ix_auth_events_operation_created_at` | no | (none) |
| `ix_auth_events_result_created_at` | no | (none) |
| `ix_subscription_events_subscription_id` | no | (none) |
| `subscription_events_notification_uuid_key` | yes | (none) |
| `subscription_events_pkey` | yes | (none) |

---

## 4. Index Predicates Under Both `search_path` Settings (P-5)

RESEARCH.md pitfall P-5 is **confirmed on PostgreSQL 17.11**: `pg_get_expr` renders enum casts
schema-qualified or bare depending on whether `core` is on the reader's `search_path`. The same
index therefore has two correct-looking predicate strings, and an unpinned assertion passes on one
machine and fails on another.

| Index | `search_path` = default (`"$user", public`) | `search_path` = `core, public` |
|-------|---------------------------------------------------|--------------------------------|
| `ix_access_grants_anti_abuse_idp_account_hash` | `(idp_account_hash IS NOT NULL)` | `(idp_account_hash IS NOT NULL)` |
| `ix_access_grants_one_active_per_user` | `(status = 'active'::core.access_grant_status)` | `(status = 'active'::access_grant_status)` |
| `ix_access_grants_one_free_grant_per_user_source` | `(source = ANY (ARRAY['anonymous_device_grant'::core.access_grant_source, 'registered_account_grant'::core.access_grant_source]))` | `(source = ANY (ARRAY['anonymous_device_grant'::access_grant_source, 'registered_account_grant'::access_grant_source]))` |
| `ix_access_grants_one_per_subscription` | `((source = 'subscription'::core.access_grant_source) AND (subscription_id IS NOT NULL) AND (status = 'active'::core.access_grant_status))` | `((source = 'subscription'::access_grant_source) AND (subscription_id IS NOT NULL) AND (status = 'active'::access_grant_status))` |
| `ix_access_grants_subscription` | `(subscription_id IS NOT NULL)` | `(subscription_id IS NOT NULL)` |
| `ix_external_identities_provider_account` | `(provider_uid IS NOT NULL)` | `(provider_uid IS NOT NULL)` |
| `ix_subscriptions_provider_external_id` | `None` (no predicate) | `None` (no predicate) |

**Task 3 pins the default `search_path`** -- the left-hand column, with `core.`-qualified enum
casts. Rationale: it is the `search_path` an ordinary `asyncpg.connect()` already has, so the test
pins what it would otherwise get by accident, and the expected strings stay literal rather than
being normalized after the fact. The pin is one statement executed at the top of the predicate test.

Note `ix_subscriptions_provider_external_id`: it is a **unique index with no predicate**, so its
expected value is `None` under both settings. Asserting the absence of a predicate is as
load-bearing as asserting its text -- a partial predicate added there later would silently narrow
uniqueness.

---

## 5. Triggers, Views, Materialized Views

| Metric | Query filter | Observed |
|--------|--------------|----------|
| User triggers on `core` + `audit` | `AND NOT t.tgisinternal` | **0** |
| **All** trigger rows on `core` + `audit` | no `tgisinternal` filter | **104** |
| Views in `core` + `audit` | `pg_views` | 0 |
| Materialized views in `core` + `audit` | `pg_matviews` | 0 |

Both trigger numbers are recorded deliberately. D-09 forbids triggers and D-18 asserts there are
zero of them, but a **correct** schema has 104 rows in `pg_trigger` for these two schemas
because PostgreSQL implements every foreign key as a pair of internal trigger rows. An unfiltered
`count(*) == 0` assertion therefore fails on a correct schema -- which is exactly what RESEARCH.md
P-7 warns about. The `NOT tgisinternal` filter is not an optimization; it is what makes the
assertion mean "no user-defined trigger" instead of "no foreign keys".

---

## 6. SCHEMA-07 Negative Results

From Code Example 3's `GONE` query, plus three additions task 3 asserts alongside them:

| Check | Result |
|-------|--------|
| `to_regtype('core.subscription_plan') IS NULL` | True |
| `to_regclass('core.usage_monthly') IS NULL` | True |
| `to_regclass('core.subscription_events') IS NULL` | True |
| no `(core, users, jwt_sub)` row in `information_schema.columns` | True |
| no `(core, users, subscription_plan)` row in `information_schema.columns` | True |
| `to_regclass('audit.subscription_events') IS NOT NULL` | True |

The last row is the guard against a false positive: `core.subscription_events` is absent because the
table **moved to `audit`**, not because it was deleted. A test asserting only the `core` absence
would pass on a schema that lost the table entirely.

`core.users` has exactly 7 columns, matching the section 2 target shape, in
`ordinal_position`:

1. `id`
2. `email`
3. `display_name`
4. `registered_at`
5. `active`
6. `created_at`
7. `updated_at`

---

## 7. Reconciliation Against RESEARCH.md Code Example 4 (PostgreSQL 16.2)

RESEARCH.md assumption A1 held that PostgreSQL 17 would behave identically to the 16.2 instance its
capture came from, because the migration uses no version-gated feature. **The assumption is
confirmed.** All six constant groups match exactly.

| # | Constant group | RESEARCH.md (PG 16.2) | This capture (PG 17.11) | Verdict |
|---|----------------|-----------------------|-----------------------------------|---------|
| 1 | `EXPECTED_ENUM_LABEL_COUNTS` | 11 types, counts as listed | 11 types, identical names and identical counts | **matched** -- no difference |
| 2 | `EXPECTED_CORE_TABLES` | 15 names | 15 names, symmetric difference empty | **matched** -- no difference |
| 3 | `EXPECTED_AUDIT_TABLES` | 2 names | 2 names, symmetric difference empty | **matched** -- no difference |
| 4 | `EXPECTED_CORE_INDEXES` | 46 names | 46 names, symmetric difference empty | **matched** -- no difference |
| 5 | `EXPECTED_AUDIT_INDEXES` | 8 names | 8 names, symmetric difference empty | **matched** -- no difference |
| 6 | `EXPECTED_INDEX_PREDICATES` | 7 entries (6 strings + 1 `None`) | 7 entries, all 7 byte-identical under the default `search_path` | **matched** -- no difference |

Additional cross-checks beyond the six groups, all matched:

- `core.auth_event_result`'s 44 labels are identical **and in identical `enumsortorder`** to
  RESEARCH.md's listing -- compared as an ordered sequence, not as a set.
- User trigger count 0 and internal trigger count 104 both match RESEARCH.md P-7's
  PostgreSQL 16.2 observation exactly.
- View count 0 and matview count 0 match.
- All four `GONE` negatives match.

**Differences found: none.** No constant in task 3's test file differs from what RESEARCH.md
recorded. A1 is closed as confirmed rather than as corrected; OQ-1 is answered "no divergence".

The values in this file are nonetheless the authority for task 3, because they were read from the
target version. RESEARCH.md remains an accurate record of the PostgreSQL 16.2 observation and was
not edited.
