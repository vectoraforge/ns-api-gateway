-- v2.0 authentication and entitlements schema
-- depends:

-- migrate: apply

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;

-- Every enum type is created before any table that uses it.
CREATE TYPE core.chat_role AS ENUM ('human', 'ai');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');

CREATE TYPE core.subscription_provider AS ENUM ('apple', 'google_play');

CREATE TYPE core.identity_provider AS ENUM ('anonymous', 'google', 'apple');
CREATE TYPE core.identity_state AS ENUM ('active', 'historical');

CREATE TYPE core.auth_operation AS ENUM (
    'create_user',
    'upgrade_anonymous_to_registered',
    'claim_anonymous_grant',
    'claim_registered_grant'
);

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

-- email is nullable on purpose: it is copied only from a verified provider record, and stays NULL otherwise.
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

CREATE TABLE core.chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id),
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_chats_user_id ON core.chats (user_id);

CREATE TABLE core.messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES core.chats (id) ON DELETE CASCADE,
    role core.chat_role NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_messages_chat_id ON core.messages (chat_id);

-- The only table storing a recoverable external subject in plaintext; it exists as a uniqueness reservation.
CREATE TABLE core.external_identities (
    id UUID PRIMARY KEY,
    -- Identity rows are never deleted, only retired, and a deployment role should also be denied DELETE here.
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    provider core.identity_provider NOT NULL,
    -- The stable Google/Apple provider-account UID, plaintext, NULL exactly for anonymous.
    provider_uid TEXT,
    identity_state core.identity_state NOT NULL DEFAULT 'active',
    -- Pins an anonymous identity's native claim platform once, immutably.
    native_claim_platform core.native_claim_provider,
    -- Set once when the account consumes its one lifetime free grant, and never cleared.
    free_grant_consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    historical_at TIMESTAMPTZ,
    -- provider_uid is NULL exactly for anonymous; no sentinel value is ever invented for one.
    CHECK (
        (provider = 'anonymous' AND provider_uid IS NULL)
        OR
        (provider IN ('google', 'apple')
            AND provider_uid IS NOT NULL
            AND provider_uid <> '')
    ),
    -- Caps a user at one identity row.
    UNIQUE (user_id),
    -- The auth-time lookup key, and the arbiter between concurrent create-user completions.
    UNIQUE (issuer, subject)
);

-- Partial, and carrying no state predicate, so retirement never frees a provider account for reuse.
CREATE UNIQUE INDEX ix_external_identities_provider_account
    ON core.external_identities (issuer, provider, provider_uid)
    WHERE provider_uid IS NOT NULL;

CREATE INDEX ix_external_identities_user_id ON core.external_identities (user_id);
CREATE INDEX ix_external_identities_provider ON core.external_identities (provider);
CREATE INDEX ix_external_identities_user_active ON core.external_identities (user_id, identity_state);

-- The rule that no registered tier grants fewer credits than the anonymous tier is not expressible here.
CREATE TABLE core.access_tiers (
    id TEXT PRIMARY KEY,
    monthly_credits INTEGER NOT NULL CHECK (monthly_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Reference data, one tier per grant source; registered (50) >= anonymous (10) keeps a claim's carry-over safe.
INSERT INTO core.access_tiers (id, monthly_credits) VALUES
    ('anonymous', 10),
    ('registered', 50),
    ('paid', 1000);

CREATE TABLE core.subscriptions (
    id UUID PRIMARY KEY,
    -- Nullable: an unclaimed store subscription is ingested unowned, and restore is what first links it.
    user_id UUID REFERENCES core.users (id),
    provider core.subscription_provider NOT NULL,
    external_id TEXT NOT NULL,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    status core.subscription_status NOT NULL,
    -- Written by nothing: cross-account restore transfer is never performed, so this stays NULL.
    last_cross_account_transfer_month DATE,
    -- Lifetime restore binding: NULL until the first successful restore, then never changed.
    restore_bound_user_id UUID REFERENCES core.users (id),
    -- The entitled set is fixed here; changing it is a future migration, never a runtime toggle.
    product_entitled_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN status IN ('active', 'grace_period') THEN id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    -- Exists solely as a composite FK target; it adds no uniqueness beyond the primary key.
    UNIQUE (id, user_id),
    UNIQUE (product_entitled_subscription_id)
);

CREATE INDEX ix_subscriptions_user_id ON core.subscriptions (user_id);

-- Globally unique on the lifecycle key, with no predicate.
CREATE UNIQUE INDEX ix_subscriptions_provider_external_id
    ON core.subscriptions (provider, external_id);

-- Deliberately PK-less: the two UNIQUE constraints carry the rules, over an opaque non-secret value.
CREATE TABLE core.store_purchase_tokens (
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    provider core.subscription_provider NOT NULL,
    identity_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    UNIQUE (provider, identity_value)
);

CREATE INDEX ix_store_purchase_tokens_user_id ON core.store_purchase_tokens (user_id);

-- One row per accepted store subscription, not per lifecycle event; inserted once and never updated.
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
    -- MATCH SIMPLE: a NULL resolved_token_value skips the check, so an unattributed purchase still records.
    FOREIGN KEY (provider, resolved_token_value)
        REFERENCES core.store_purchase_tokens (provider, identity_value)
);

CREATE INDEX ix_store_purchases_purchase_user_id
    ON core.store_purchases (purchase_user_id);

CREATE INDEX ix_store_purchases_provider_identity_value
    ON core.store_purchases (provider, identity_value);

-- Append-only: the subscription event log, in the audit schema and keyed on tier ids rather than plan names.
CREATE TABLE audit.subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES core.subscriptions (id),
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier_id TEXT REFERENCES core.access_tiers (id),
    new_tier_id TEXT REFERENCES core.access_tiers (id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_subscription_events_subscription_id ON audit.subscription_events (subscription_id);

CREATE TABLE core.access_grants (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    source core.access_grant_source NOT NULL,
    subscription_id UUID,
    status core.access_grant_status NOT NULL DEFAULT 'active',
    starts_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Open-ended grants are legal, so ends_at is nullable and a finite end is never required.
    ends_at TIMESTAMPTZ,
    -- The "at least one anti-abuse row per free-source grant" lower bound, via the deferrable FK below.
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
    CHECK (
        (source = 'subscription' AND subscription_id IS NOT NULL)
        OR
        (source <> 'subscription' AND subscription_id IS NULL)
    ),
    -- A composite FK target for the anti-abuse table only.
    UNIQUE (id, source),
    -- Deferred so ingestion and restore can write both rows in one transaction, in either order.
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

-- Superseded term rows stay in history while at most one active grant per subscription exists.
CREATE UNIQUE INDEX ix_access_grants_one_per_subscription
    ON core.access_grants (subscription_id)
    WHERE source = 'subscription' AND subscription_id IS NOT NULL AND status = 'active';

-- Non-deferrable and per-statement; a correct caller makes it unreachable by expiring before activating.
CREATE UNIQUE INDEX ix_access_grants_one_active_per_user
    ON core.access_grants (user_id)
    WHERE status = 'active';

CREATE TABLE core.access_grants_anti_abuse (
    -- The primary key is the "at most one anti-abuse row per grant" upper bound.
    grant_id UUID PRIMARY KEY,
    grant_source core.access_grant_source NOT NULL,
    native_claim_provider core.native_claim_provider,
    -- A non-authoritative lookup alias only: several key versions may map to one canonical account.
    idp_account_hash BYTEA,
    idp_account_hash_key_version SMALLINT,
    registered_account_grant_id UUID GENERATED ALWAYS AS (
        CASE WHEN grant_source = 'registered_account_grant' THEN grant_id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    -- With the composite FK below, this forbids an anti-abuse row for a subscription or manual grant.
    CHECK (grant_source IN ('anonymous_device_grant', 'registered_account_grant')),
    -- The native anonymous arm is shape-only: it constrains NULL population and enumerates no providers.
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

-- Never unique: several key versions may map to one canonical provider account.
CREATE INDEX ix_access_grants_anti_abuse_idp_account_hash
    ON core.access_grants_anti_abuse (idp_account_hash)
    WHERE idp_account_hash IS NOT NULL;

-- Circular: these point back at the anti-abuse table, so they cannot be declared inline above.
ALTER TABLE core.access_grants
    ADD FOREIGN KEY (anti_abuse_required_grant_id)
        REFERENCES core.access_grants_anti_abuse (grant_id)
        DEFERRABLE INITIALLY DEFERRED,
    ADD FOREIGN KEY (active_registered_account_grant_id)
        REFERENCES core.access_grants_anti_abuse (registered_account_grant_id)
        DEFERRABLE INITIALLY DEFERRED;

-- No status predicate on purpose: expiry or revocation never reopens the lifetime free-grant slot.
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

-- Authoritative free-grant gate uniqueness, and it survives erasure so an erased account cannot reclaim.
CREATE TABLE core.provider_accounts (
    id UUID PRIMARY KEY,
    provider core.identity_provider NOT NULL CHECK (provider IN ('google', 'apple')),
    provider_uid TEXT NOT NULL CHECK (provider_uid <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, provider_uid)
);

-- Per-key abuse brakes only; the per-account rule lives on external_identities.free_grant_consumed_at.
CREATE TABLE core.provider_account_gate_consumptions (
    provider_account_id UUID NOT NULL REFERENCES core.provider_accounts (id),
    consumption_kind core.gate_consumption_kind NOT NULL,
    grant_id UUID NOT NULL REFERENCES core.access_grants (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_account_id, consumption_kind)
);

CREATE INDEX ix_gate_consumptions_grant_id
    ON core.provider_account_gate_consumptions (grant_id);

-- monthly_period is free text in YYYY-MM with no format CHECK, and the allowance is derived, never stored.
CREATE TABLE core.user_monthly_usage (
    grant_id UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE,
    monthly_period TEXT NOT NULL,
    monthly_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (monthly_used >= 0)
);

CREATE TABLE core.auth_challenges (
    -- An internal correlation identifier, never returned to a client.
    id UUID PRIMARY KEY,
    -- The single opaque random value that both locates the row and serves as the nonce.
    challenge_id TEXT NOT NULL UNIQUE,
    operation core.auth_operation NOT NULL,
    bound_external_identity_id UUID REFERENCES core.external_identities (id),
    -- Plaintext: a deployment-known provider string shared by every user of that provider.
    preauth_issuer TEXT,
    -- The verified subject in plaintext, cleared when the row is consumed.
    preauth_subject TEXT,
    -- The TTL is applied by the application; there is no database default and no per-operation override.
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    -- Lifecycle: issued, then claimed once claimed_at is set, then consumed; consuming requires a claim.
    CHECK (consumed_at IS NULL OR claimed_at IS NOT NULL),
    -- Exactly one of the bound identity or the preauth pair, with the subject clearable only once consumed.
    CHECK (
        (bound_external_identity_id IS NOT NULL
            AND preauth_issuer IS NULL
            AND preauth_subject IS NULL)
        OR
        (bound_external_identity_id IS NULL
            AND preauth_issuer IS NOT NULL
            AND (preauth_subject IS NOT NULL OR consumed_at IS NOT NULL))
    )
);

CREATE INDEX ix_auth_challenges_expires_at ON core.auth_challenges (expires_at);

-- migrate: rollback

DROP SCHEMA IF EXISTS audit CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
