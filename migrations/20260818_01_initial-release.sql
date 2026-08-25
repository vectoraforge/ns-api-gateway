-- v2.0 authentication and entitlements schema
-- depends:
--
-- Single initial migration. The v2.0 schema is delivered in one apply against an
-- empty database; no incremental migration files are added during v2.0.
-- See .planning/PROJECT.md Key Decisions and .planning/phases/34-schema/34-CONTEXT.md D-01.
--
-- This file supersedes and replaces 20260322_01_initial-release.sql, which is deleted.
-- The filename stem is pogo's tracked migration id, so the rename presents this file as a
-- new, unapplied id: a database holding the old id fails loudly instead of silently
-- skipping a stale schema (34-CONTEXT.md D-02).
--
-- Source of truth: specs/auth-refactor-phases/00-schema.md.
-- Statement order follows its section 1 exactly; section 9's fourteen rulings override any
-- contrary prose elsewhere in that document. Section 1's prohibition list is absolute:
-- no triggers, stored procedures, rules, views, materialized views, extensions,
-- partitioning, NULLS NOT DISTINCT, invented format CHECKs, scheduled-job scaffolding,
-- and no ON UPDATE / ON DELETE clause beyond the ones section 8 enumerates.
-- updated_at columns are maintained by application writes, never by a trigger.
--
-- Sections 3-7 of the spec are written as a delta against the deleted baseline migration.
-- Seven objects the spec's section 10 inventory requires are therefore never created by
-- those sections and are written here by hand: schemas core and audit, enums
-- core.chat_role and core.subscription_status, and tables core.users, core.chats,
-- core.messages with index ix_chats_user_id. core.users below is the section 2 TARGET
-- shape (00-schema.md:84-94), NOT the baseline shape: it has no jwt_sub and no
-- subscription_plan, and email is nullable.

-- migrate: apply

-- =====================================================================
-- PREAMBLE (unnumbered) - SCHEMAS
-- Deliberately outside the five numbered sections below: both statements
-- precede every one of them and belong to none. This is not a sixth section.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;

-- =====================================================================
-- 1. ENUMS  (00-schema.md section 3, plus the two baseline survivors)
-- All eleven enum types are created before any table that uses them.
-- =====================================================================

-- Baseline survivors. 00-schema.md:181 says these "survive from the baseline unchanged
-- and are not recreated" - true of the spec's six-file sequence, false of this from-empty
-- single file, so they are recreated verbatim from the deleted baseline migration.
CREATE TYPE core.chat_role AS ENUM ('human', 'ai');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');

-- The baseline's core.subscription_provider had only 'apple'; it gains 'google_play'.
-- There is no core.subscription_plan enum in v2.0: plan/tier lives on core.access_tiers,
-- referenced by grants and subscriptions, never on the user row.
CREATE TYPE core.subscription_provider AS ENUM ('apple', 'google_play');

CREATE TYPE core.identity_provider AS ENUM ('anonymous', 'google', 'apple');
CREATE TYPE core.identity_state AS ENUM ('active', 'historical');

CREATE TYPE core.auth_operation AS ENUM (
    'create_user',
    'upgrade_anonymous_to_registered',
    'claim_anonymous_grant',
    'claim_registered_grant',
    'restore_subscription',
    'sign_out_all',
    'sync'
);

-- Ruling 9.1: 'promo' is DELETED from this enum and from every rule that referenced it.
-- Exactly four values. Any document still showing 'promo' is stale.
CREATE TYPE core.access_grant_source AS ENUM (
    'subscription',
    'anonymous_device_grant',
    'registered_account_grant',
    'manual'
);

CREATE TYPE core.access_grant_status AS ENUM (
    'active',
    'revoked',
    'expired'
);

CREATE TYPE core.native_claim_provider AS ENUM ('ios_devicecheck', 'android_play_integrity');

CREATE TYPE core.gate_consumption_kind AS ENUM ('web_anonymous_gate', 'registered_account_grant');

-- =====================================================================
-- 2. IDENTITY AND TIERS  (00-schema.md section 4, plus users/chats/messages)
-- =====================================================================

-- core.users is the section 2 TARGET shape (00-schema.md:84-94), all seven columns of it.
-- Deliberately absent: jwt_sub (and ix_users_jwt_sub) - the external subject is never an
-- ownership or lookup key here; (issuer, subject) lives only on core.external_identities.
-- Also absent: subscription_plan, and the baseline's 'name' column, renamed display_name.
-- email is NULLABLE on purpose (00-schema.md:80): it is copied only from a Firebase Admin
-- record whose emailVerified is TRUE, and stays NULL otherwise. Do not add NOT NULL.
CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    registered_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_users_registered_at ON core.users (registered_at);

-- Baseline survivor, definition unchanged (00-schema.md:82).
CREATE TABLE core.chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id),
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_chats_user_id ON core.chats (user_id);

-- Baseline survivor, definition unchanged (00-schema.md:82), including its ON DELETE
-- CASCADE, which is one of the five cascades section 8 permits.
CREATE TABLE core.messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES core.chats (id) ON DELETE CASCADE,
    role core.chat_role NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_messages_chat_id ON core.messages (chat_id);

-- ---------------------------------------------------------------------
-- DATABASE ROLE REQUIREMENT - ACTION REQUIRED BY WHOEVER PROVISIONS ROLES
--
-- Normal application and cleanup roles MUST have no permission to delete
-- core.external_identities rows:
--
--     REVOKE DELETE ON core.external_identities FROM <application_role>;
--
-- That statement is deliberately NOT in this migration. This repository defines no
-- database role - only a DB_USER placeholder in [tool.pogo] database_config and in
-- docker-compose.yml - and 00-schema.md:622 says to note the requirement in the
-- migration comment rather than invent a role. Add the REVOKE when the deployment
-- defines an application role. The ON DELETE RESTRICT below is the guardrail this
-- file CAN enforce; it stops a user row being deleted out from under an identity row,
-- but it does not stop a privileged role deleting the identity row itself.
-- ---------------------------------------------------------------------
--
-- This is the ONLY table that stores a recoverable external subject. issuer/subject are
-- the verified Firebase ID token's iss/sub in plaintext; core.auth_challenges stores a
-- keyed hash instead. That plaintext is the deliberate, user-disclosed exception of
-- section 8: it exists solely as a uniqueness reservation.
CREATE TABLE core.external_identities (
    id UUID PRIMARY KEY,
    -- ON DELETE RESTRICT is intentional (section 8) - a guardrail against deleting a
    -- user out from under an identity row. Identity rows are never deleted; retirement
    -- (identity_state='historical' + historical_at) and blocking (users.active=FALSE)
    -- are state transitions, never row removal.
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    provider core.identity_provider NOT NULL,
    -- The stable Google/Apple provider-account UID, plaintext, NULL exactly for anonymous.
    provider_uid TEXT,
    identity_state core.identity_state NOT NULL DEFAULT 'active',
    -- Pins an anonymous identity's native claim platform once, immutably.
    native_claim_platform core.native_claim_provider,
    -- Permanent per-account marker that the account consumed its one lifetime free
    -- grant; set once, never cleared.
    free_grant_consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    historical_at TIMESTAMPTZ,
    -- Ruling 9.2: the provider/provider_uid agreement is a CHECK constraint, not a
    -- write-path rule. No sentinel or placeholder provider_uid is ever invented for an
    -- anonymous row.
    CHECK (
        (provider = 'anonymous' AND provider_uid IS NULL)
        OR
        (provider IN ('google', 'apple')
            AND provider_uid IS NOT NULL
            AND provider_uid <> '')
    ),
    -- Caps a user at one identity row.
    UNIQUE (user_id),
    -- Makes an external identity belong to at most one user; the auth-time lookup key
    -- and the race arbiter for concurrent create-user completions.
    UNIQUE (issuer, subject)
);

-- A PARTIAL unique index, deliberately stating the business rule (the reservation covers
-- registered provider accounts only) rather than leaning on NULL-distinctness. It carries
-- no state predicate, so it covers 'historical' tombstones as well as 'active' rows and
-- retirement never frees a provider account for reuse. Never replace it with a table-level
-- UNIQUE, and never use UNIQUE NULLS NOT DISTINCT here.
CREATE UNIQUE INDEX ix_external_identities_provider_account
    ON core.external_identities (issuer, provider, provider_uid)
    WHERE provider_uid IS NOT NULL;

CREATE INDEX ix_external_identities_user_id ON core.external_identities (user_id);
CREATE INDEX ix_external_identities_provider ON core.external_identities (provider);
CREATE INDEX ix_external_identities_user_active ON core.external_identities (user_id, identity_state);

-- Product configuration. The only database-side rule is monthly_credits >= 0; the "no
-- registered tier may grant fewer monthly_credits than the anonymous tier" sizing
-- invariant (07-claim-registered-grant.md:59) is not expressible as a constraint here.
CREATE TABLE core.access_tiers (
    id TEXT PRIMARY KEY,
    monthly_credits INTEGER NOT NULL CHECK (monthly_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seeded as reference data, overriding 00-schema.md:249 ("Phase 00 seeds NO tier rows -
-- tier ids are configuration owned by later phases/deployment"). Recorded here as the
-- required SHARED-INVARIANTS conflict flag rather than resolved silently. Rationale: no
-- phase in the roadmap claimed tier seeding, so the table stayed empty and every grant
-- path (36, 41, 42, 43) had nothing to FK against.
--
-- One row per v2.0 grant source: 'anonymous' backs anonymous_device_grant, 'registered'
-- backs registered_account_grant, 'paid' backs subscription. 'manual' grants pick whichever
-- tier the issuance names.
--
-- registered (50) >= anonymous (10) satisfies the sizing invariant, which is what makes
-- 07-claim-registered-grant.md:59's carry-over of monthly_used across a claim safe: the
-- superseded grant's consumption can never exceed the new grant's allowance.
INSERT INTO core.access_tiers (id, monthly_credits) VALUES
    ('anonymous', 10),
    ('registered', 50),
    ('paid', 1000);

-- =====================================================================
-- 3. SUBSCRIPTIONS AND STORE  (00-schema.md section 5)
-- =====================================================================

CREATE TABLE core.subscriptions (
    id UUID PRIMARY KEY,
    -- NULLABLE: an unclaimed store subscription is ingested unowned, and restore's
    -- adoption is what first links it.
    user_id UUID REFERENCES core.users (id),
    provider core.subscription_provider NOT NULL,
    external_id TEXT NOT NULL,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    status core.subscription_status NOT NULL,
    -- Ships but is written by nothing: cross-account restore transfer is never performed
    -- (ruling 9.10), so this stays NULL forever. Keep the column; build no code that sets it.
    last_cross_account_transfer_month DATE,
    -- Lifetime store-transaction-to-account restore binding: NULL until the first
    -- successful restore, then never changed.
    restore_bound_user_id UUID REFERENCES core.users (id),
    -- Ruling 9.14: the product-entitled set is FIXED at ('active','grace_period') in this
    -- expression. billing_retry, expired and revoked are NOT entitled. Changing the set is
    -- a future migration, never a runtime toggle. The UNIQUE below exists so
    -- core.access_grants can point a deferrable FK at this column.
    product_entitled_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN status IN ('active', 'grace_period') THEN id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    -- Exists solely as a composite FK target for core.access_grants; it adds no
    -- uniqueness beyond the primary key.
    UNIQUE (id, user_id),
    UNIQUE (product_entitled_subscription_id)
);

CREATE INDEX ix_subscriptions_user_id ON core.subscriptions (user_id);

-- Globally unique on the lifecycle key. This replaces the baseline's
-- ix_subscriptions_external_id and ix_subscriptions_user_provider_active, neither of
-- which is recreated (00-schema.md:333). No predicate.
CREATE UNIQUE INDEX ix_subscriptions_provider_external_id
    ON core.subscriptions (provider, external_id);

-- Intentionally has NO primary key; its two UNIQUE constraints carry the rules - one
-- attribution token per user per store for the account's life, and one owner per
-- (provider, identity_value). The value is a random, opaque, server-generated,
-- non-secret UUID that is never rotated and survives the anonymous-to-registered upgrade.
CREATE TABLE core.store_purchase_tokens (
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    provider core.subscription_provider NOT NULL,
    identity_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    UNIQUE (provider, identity_value)
);

CREATE INDEX ix_store_purchase_tokens_user_id ON core.store_purchase_tokens (user_id);

-- Ruling 9.9: one row per accepted (provider, external_id) store subscription, NOT one
-- row per lifecycle event. Immutable historical record - inserted once, never updated,
-- reassigned, or deleted, which is why both composite FKs keep default NO ACTION.
CREATE TABLE core.store_purchases (
    id UUID PRIMARY KEY,
    provider core.subscription_provider NOT NULL,
    identity_value TEXT NOT NULL,
    external_id TEXT NOT NULL,
    store_transaction_id TEXT,
    store_original_transaction_id TEXT,
    purchase_user_id UUID REFERENCES core.users (id),
    resolved_token_value TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (provider, external_id),
    -- Keeps resolved_token_value from drifting away from identity_value.
    CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value),
    FOREIGN KEY (provider, external_id)
        REFERENCES core.subscriptions (provider, external_id),
    -- Relies on MATCH SIMPLE semantics: a NULL resolved_token_value skips the check, which
    -- is how unattributed purchases (no echoed token, unresolvable token, restore-created
    -- rows) are recorded without rejection.
    FOREIGN KEY (provider, resolved_token_value)
        REFERENCES core.store_purchase_tokens (provider, identity_value)
);

CREATE INDEX ix_store_purchases_purchase_user_id
    ON core.store_purchases (purchase_user_id);

CREATE INDEX ix_store_purchases_provider_identity_value
    ON core.store_purchases (provider, identity_value);

-- The baseline core.subscription_events moved into the audit schema, with old_plan/new_plan
-- replaced by old_tier_id/new_tier_id referencing core.access_tiers. Append-only.
CREATE TABLE audit.subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES core.subscriptions (id),
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier_id TEXT REFERENCES core.access_tiers (id),
    new_tier_id TEXT REFERENCES core.access_tiers (id),
    created_at TIMESTAMPTZ NOT NULL
);

-- The index keeps its baseline name but now lives in audit (00-schema.md:339).
CREATE INDEX ix_subscription_events_subscription_id ON audit.subscription_events (subscription_id);

-- =====================================================================
-- 4. GRANTS, ANTI-ABUSE, PROVIDER-ACCOUNT GATES, USAGE  (00-schema.md section 6)
-- =====================================================================

CREATE TABLE core.access_grants (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    source core.access_grant_source NOT NULL,
    subscription_id UUID,
    status core.access_grant_status NOT NULL DEFAULT 'active',
    starts_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Ruling 9.11: open-ended grants are legal, so ends_at is nullable and a finite end
    -- is never required.
    ends_at TIMESTAMPTZ,
    -- The "at least one anti-abuse row for the two free sources" lower bound, enforced by
    -- the deferrable FK added by ALTER TABLE below.
    anti_abuse_required_grant_id UUID GENERATED ALWAYS AS (
        CASE WHEN source IN ('anonymous_device_grant', 'registered_account_grant') THEN id END
    ) STORED,
    active_registered_account_grant_id UUID GENERATED ALWAYS AS (
        CASE WHEN source = 'registered_account_grant' AND status = 'active' THEN id END
    ) STORED,
    active_subscription_grant_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN source = 'subscription' AND status = 'active' THEN subscription_id END
    ) STORED,
    active_subscription_grant_user_id UUID GENERATED ALWAYS AS (
        CASE WHEN source = 'subscription' AND status = 'active' THEN user_id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ends_at IS NULL OR ends_at > starts_at),
    -- source='subscription' requires subscription_id; every other source forbids it.
    -- Free and manual grants are real grant rows, never fake subscriptions.
    CHECK (
        (source = 'subscription' AND subscription_id IS NOT NULL)
        OR
        (source <> 'subscription' AND subscription_id IS NULL)
    ),
    -- A composite FK target for the anti-abuse table only.
    UNIQUE (id, source),
    -- These two deferrable FKs enforce, declaratively, that an active subscription-backed
    -- grant's user_id equals the subscription's user_id and that its subscription is
    -- product-entitled. MATCH SIMPLE semantics exempt non-subscription and terminal rows,
    -- which generate NULLs. Deferred so ingestion/restore can write both rows in one
    -- transaction in either order.
    FOREIGN KEY (active_subscription_grant_subscription_id, active_subscription_grant_user_id)
        REFERENCES core.subscriptions (id, user_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (active_subscription_grant_subscription_id)
        REFERENCES core.subscriptions (product_entitled_subscription_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_access_grants_user_active
    ON core.access_grants (user_id, status, starts_at, ends_at);

CREATE INDEX ix_access_grants_subscription
    ON core.access_grants (subscription_id)
    WHERE subscription_id IS NOT NULL;

-- Allows superseded term rows to remain in history while at most one active grant per
-- subscription exists.
CREATE UNIQUE INDEX ix_access_grants_one_per_subscription
    ON core.access_grants (subscription_id)
    WHERE source = 'subscription' AND subscription_id IS NOT NULL AND status = 'active';

-- A plain, NON-deferrable, per-statement partial unique index. Do not convert it to a
-- deferrable exclusion constraint and do not write an application rejection path for it;
-- correct callers make it unreachable by expiring before activating.
CREATE UNIQUE INDEX ix_access_grants_one_active_per_user
    ON core.access_grants (user_id)
    WHERE status = 'active';

CREATE TABLE core.access_grants_anti_abuse (
    -- The primary key is the "at most one anti-abuse row per grant" upper bound.
    grant_id UUID PRIMARY KEY,
    grant_source core.access_grant_source NOT NULL,
    native_claim_provider core.native_claim_provider,
    -- Ruling 9.5: free-grant uniqueness is on the stable provider UID
    -- (core.provider_accounts + gate consumptions), NOT on this keyed hash. These two
    -- columns survive only as a non-authoritative lookup and audit alias, so multiple key
    -- versions may map to one canonical account.
    idp_account_hash BYTEA,
    idp_account_hash_key_version SMALLINT,
    registered_account_grant_id UUID GENERATED ALWAYS AS (
        CASE WHEN grant_source = 'registered_account_grant' THEN grant_id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    -- With the composite FK below, this forbids an anti-abuse row for a 'subscription' or
    -- 'manual' grant at all.
    CHECK (grant_source IN ('anonymous_device_grant', 'registered_account_grant')),
    -- Ruling 9.6: the native anonymous arm is SHAPE ONLY - it constrains NULL/NOT NULL
    -- population and does NOT enumerate accepted native_claim_provider values. Do not add
    -- a value list to that arm. The three valid shapes are: native anonymous
    -- (native_claim_provider NOT NULL, hash fields NULL), web anonymous
    -- (native_claim_provider NULL, both hash fields NOT NULL), registered (same as web).
    CHECK (
        (grant_source = 'anonymous_device_grant'
            AND (
                (native_claim_provider IS NOT NULL
                    AND idp_account_hash IS NULL
                    AND idp_account_hash_key_version IS NULL)
                OR
                (native_claim_provider IS NULL
                    AND idp_account_hash IS NOT NULL
                    AND idp_account_hash_key_version IS NOT NULL)
            ))
        OR
        (grant_source = 'registered_account_grant'
            AND native_claim_provider IS NULL
            AND idp_account_hash IS NOT NULL
            AND idp_account_hash_key_version IS NOT NULL)
    ),
    UNIQUE (registered_account_grant_id),
    FOREIGN KEY (grant_id, grant_source)
        REFERENCES core.access_grants (id, source)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
);

-- Ruling 9.5: NEVER make this index unique. Multiple key versions may map to one
-- canonical provider account.
CREATE INDEX ix_access_grants_anti_abuse_idp_account_hash
    ON core.access_grants_anti_abuse (idp_account_hash)
    WHERE idp_account_hash IS NOT NULL;

-- The circular pair. These two FKs point back at core.access_grants_anti_abuse, so they
-- must be added by ALTER TABLE after that table exists rather than declared inline.
-- Together with the anti-abuse primary key, the composite (grant_id, grant_source) FK and
-- the per-source CHECK, they make "exactly one anti-abuse row iff free source" fully
-- declarative - no trigger, no application check.
ALTER TABLE core.access_grants
    ADD FOREIGN KEY (anti_abuse_required_grant_id)
        REFERENCES core.access_grants_anti_abuse (grant_id)
        DEFERRABLE INITIALLY DEFERRED,
    ADD FOREIGN KEY (active_registered_account_grant_id)
        REFERENCES core.access_grants_anti_abuse (registered_account_grant_id)
        DEFERRABLE INITIALLY DEFERRED;

-- The lifetime one-free-grant-per-source slot. It has NO status predicate on purpose:
-- expiry, revocation, or a lapsed paid entitlement never reopens the slot. 'subscription'
-- and 'manual' are outside the predicate and unbounded.
CREATE UNIQUE INDEX ix_access_grants_one_free_grant_per_user_source
    ON core.access_grants (user_id, source)
    WHERE source IN ('anonymous_device_grant', 'registered_account_grant');

-- Immutable historical record; its FKs carry no cascade for exactly that reason.
CREATE TABLE core.manual_grant_issuances (
    case_id TEXT PRIMARY KEY CHECK (case_id <> ''),
    grant_id UUID NOT NULL UNIQUE REFERENCES core.access_grants (id),
    user_id UUID NOT NULL REFERENCES core.users (id),
    operator TEXT NOT NULL CHECK (operator <> ''),
    reason TEXT NOT NULL CHECK (reason <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Authoritative free-grant gate uniqueness lives here (with the gate-consumptions primary
-- key below), not on idp_account_hash. Reuses core.identity_provider with a CHECK
-- restricting it to google/apple - anonymous accounts have no provider-account row.
-- Immutable historical record. Survives privacy erasure, so an erased provider account
-- can never claim a free grant again.
CREATE TABLE core.provider_accounts (
    id UUID PRIMARY KEY,
    provider core.identity_provider NOT NULL CHECK (provider IN ('google', 'apple')),
    provider_uid TEXT NOT NULL CHECK (provider_uid <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, provider_uid)
);

-- One row per (provider_account_id, consumption_kind), recording the grant_id it produced
-- so a repeat claim can be matched to its grant. The two consumption kinds are independent
-- rows and are per-key abuse brakes only; the user-level "one free grant per account across
-- both claim endpoints" rule is carried by core.external_identities.free_grant_consumed_at
-- and the lifetime grant index, not by these rows.
CREATE TABLE core.provider_account_gate_consumptions (
    provider_account_id UUID NOT NULL REFERENCES core.provider_accounts (id),
    consumption_kind core.gate_consumption_kind NOT NULL,
    grant_id UUID NOT NULL REFERENCES core.access_grants (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_account_id, consumption_kind)
);

CREATE INDEX ix_gate_consumptions_grant_id
    ON core.provider_account_gate_consumptions (grant_id);

-- Keyed by grant_id, NOT by user, and replaces the dropped core.usage_monthly entirely.
-- monthly_period is free text in YYYY-MM (UTC calendar month) with NO format CHECK
-- (00-schema.md:500) - do not invent one. Allowance is never stored here; it is derived by
-- joining the grant to core.access_tiers.
CREATE TABLE core.user_monthly_usage (
    grant_id UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE,
    monthly_period TEXT NOT NULL,
    monthly_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (monthly_used >= 0)
);

-- =====================================================================
-- 5. CHALLENGES AND THE AUTH AUDIT LOG  (00-schema.md section 7)
-- =====================================================================

CREATE TABLE core.auth_challenges (
    -- An internal correlation identifier, never returned to a client.
    id UUID PRIMARY KEY,
    -- The single opaque random value that both locates the row and serves as the nonce.
    challenge_id TEXT NOT NULL UNIQUE,
    operation core.auth_operation NOT NULL,
    bound_external_identity_id UUID REFERENCES core.external_identities (id),
    -- Ruling 9.3: preauth_issuer stays PLAINTEXT. It is a deployment-known provider string
    -- shared by every user of that provider; do not hash it, encrypt it, or drop it.
    preauth_issuer TEXT,
    -- Ruling 9.4: the challenge subject is a stored keyed hash (HMAC-SHA-256 of the
    -- backend-verified subject), not a signed token carried by the client. There is no
    -- signed-token column and no JWT column. This row records NO HMAC key version -
    -- verification uses the current active key alone, so a challenge outstanding across a
    -- key rotation simply fails. Do NOT add a key-version column here.
    preauth_subject_hash BYTEA,
    -- The 300-second TTL is applied by the application when it writes this; there is no
    -- database default and no per-operation override.
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    claim_attempt_id UUID,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    -- Lifecycle: issued while claimed_at IS NULL; claimed once claimed_at and the
    -- attempt's server-generated claim_attempt_id are set; consumed once consumed_at is set.
    CHECK (
        (claimed_at IS NULL AND claim_attempt_id IS NULL AND consumed_at IS NULL)
        OR
        (claimed_at IS NOT NULL AND claim_attempt_id IS NOT NULL)
    ),
    -- Ruling 9.8: exactly the four challenge-bearing operations, by membership alone.
    -- restore_subscription, sign_out_all and sync are challenge-free - restore has no
    -- challenge row, no claim step and no consumption step - and the database refuses
    -- such a row.
    --
    -- Phase 37 / D-12 + D-13: the per-operation variant arms are GONE with the
    -- operation_variant column. D-12 deletes the client flow declaration, so the account
    -- type is derived from Firebase Admin providerData at COMPLETION, not declared at
    -- prepare; there is nothing left to freeze at insert time and a nullable column would
    -- be a field nothing ever writes. What survives is the membership rule alone.
    --
    -- HANDOFF, NOT PHASE 37's TO SOLVE: upgrade_anonymous_to_registered was pinned here to
    -- operation_variant IN ('google','apple'). Phase 40 (POST /auth/upgrade-anonymous) has
    -- therefore lost its provider binding at the database and must supply its own; this
    -- CHECK is deliberately written so Phase 40's rows still insert.
    CHECK (
        operation IN (
            'create_user',
            'upgrade_anonymous_to_registered',
            'claim_anonymous_grant',
            'claim_registered_grant'
        )
    ),
    -- Requires exactly one of bound_external_identity_id or
    -- (preauth_issuer, preauth_subject_hash), and admits a cleared preauth_subject_hash
    -- only once consumed_at is set.
    CHECK (
        (bound_external_identity_id IS NOT NULL
            AND preauth_issuer IS NULL
            AND preauth_subject_hash IS NULL)
        OR
        (bound_external_identity_id IS NULL
            AND preauth_issuer IS NOT NULL
            AND (preauth_subject_hash IS NOT NULL OR consumed_at IS NOT NULL))
    )
);

CREATE INDEX ix_auth_challenges_expires_at ON core.auth_challenges (expires_at);

-- migrate: rollback

DROP SCHEMA IF EXISTS audit CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
