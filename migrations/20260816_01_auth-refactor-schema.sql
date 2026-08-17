-- the auth refactor declarative schema, applied as written
-- depends: 20260322_01_initial-release

-- migrate: apply

-- The pre-refactor objects of the initial release are replaced wholesale: the auth refactor
-- redefines core.users, core.subscriptions and the usage table, and adds the identity, grant,
-- challenge and audit tables. They are dropped here so the declarative schema below applies
-- exactly as the specification writes it.
DROP TABLE IF EXISTS core.subscription_events;
DROP TABLE IF EXISTS core.usage_monthly;
DROP TABLE IF EXISTS core.subscriptions;
DROP TABLE IF EXISTS core.messages;
DROP TABLE IF EXISTS core.chats;
DROP TABLE IF EXISTS core.users;
DROP TYPE IF EXISTS core.subscription_status;
DROP TYPE IF EXISTS core.subscription_provider;
DROP TYPE IF EXISTS core.subscription_plan;
DROP TYPE IF EXISTS core.chat_role;

-- Everything between this line and the rollback marker is the declarative database schema of
-- specs/auth-refactor/06-schema-reference.md, applied as written. The only lines added to it
-- are the `-- [impl->...]` coverage tags; tests/unit/test_schema_ddl.py compares this section
-- against the reference DDL with those tag lines removed.
-- [impl->req~schema-ddl-as-written~1]
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TYPE core.chat_role AS ENUM ('human', 'ai');

CREATE TYPE core.subscription_provider AS ENUM ('apple', 'google_play');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');

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

CREATE TYPE core.auth_event_result AS ENUM (
    'succeeded',
    'challenge_expired',
    'challenge_consumed',
    'challenge_identity_mismatch',
    'challenge_operation_mismatch',
    'challenge_not_found',
    'invalid_external_jwt',
    'preauth_identity_not_allowed',
    'identity_already_linked',
    'provider_not_linked',
    'provider_transition_not_allowed',
    'provider_account_already_linked',
    'blocked_user',
    'historical_identity',
    'invalid_restore_proof',
    'proof_malformed',
    'store_transaction_already_linked',
    'restore_subscription_unlinked',
    'restore_subscription_not_entitled',
    'restore_purchase_uuid_unknown',
    'restore_purchase_uuid_mismatch',
    'restore_subscription_grant_owner_mismatch',
    'restore_branch_inconsistent',
    'restore_store_state_unverified',
    'restore_source_user_inactive',
    'restore_destination_anonymous',
    'restore_destination_already_entitled',
    'anti_abuse_already_claimed',
    'native_claim_already_claimed',
    'native_claim_unavailable',
    'native_claim_write_failed',
    'devicecheck_read_budget_exhausted',
    'devicecheck_write_budget_exhausted',
    'device_recall_read_budget_exhausted',
    'device_recall_write_budget_exhausted',
    'firebase_user_unresolved',
    'idp_account_not_eligible',
    'firebase_lookup_unavailable',
    'verification_temporarily_unavailable',
    'idp_account_already_claimed',
    'registered_grant_destination_incompatible',
    'policy_rejected',
    'revocation_unconfirmed',
    'internal_error'
);
CREATE TYPE core.native_claim_provider AS ENUM ('ios_devicecheck', 'android_play_integrity');

-- [impl->req~schema-users-internal-owner~1]
-- [impl->req~schema-users-shared-table-anon-registered~1]
-- [impl->req~schema-users-no-plan-fields~1]
CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    -- [impl->req~schema-users-email-display-name-canonical~1]
    email TEXT,
    display_name TEXT,
    registered_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    -- [impl->req~schema-users-timestamps-default-on-insert~1]
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_users_registered_at ON core.users (registered_at);

CREATE TABLE core.external_identities (
    id UUID PRIMARY KEY,
    -- [impl->req~schema-users-never-hard-deleted~1]
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    provider core.identity_provider NOT NULL,
    provider_uid TEXT,
    identity_state core.identity_state NOT NULL DEFAULT 'active',
    native_claim_platform core.native_claim_provider,
    free_grant_consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    historical_at TIMESTAMPTZ,
    CHECK (
        (provider = 'anonymous' AND provider_uid IS NULL)
        OR
        (provider IN ('google', 'apple')
            AND provider_uid IS NOT NULL
            AND provider_uid <> '')
    ),
    UNIQUE (user_id),
    UNIQUE (issuer, subject)
);

CREATE UNIQUE INDEX ix_external_identities_provider_account
    ON core.external_identities (issuer, provider, provider_uid)
    WHERE provider_uid IS NOT NULL;

CREATE INDEX ix_external_identities_user_id ON core.external_identities (user_id);
CREATE INDEX ix_external_identities_provider ON core.external_identities (provider);
CREATE INDEX ix_external_identities_user_active ON core.external_identities (user_id, identity_state);

CREATE TABLE core.access_tiers (
    id TEXT PRIMARY KEY,
    monthly_credits INTEGER NOT NULL CHECK (monthly_credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE core.chats (
    id UUID PRIMARY KEY,
    -- [impl->req~schema-users-chat-single-owner~1]
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

CREATE TABLE core.subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES core.users (id),
    provider core.subscription_provider NOT NULL,
    external_id TEXT NOT NULL,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    status core.subscription_status NOT NULL,
    last_cross_account_transfer_month DATE,
    restore_bound_user_id UUID REFERENCES core.users (id),
    product_entitled_subscription_id UUID GENERATED ALWAYS AS (
        CASE WHEN status IN ('active', 'grace_period') THEN id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (id, user_id),
    UNIQUE (product_entitled_subscription_id)
);

CREATE INDEX ix_subscriptions_user_id ON core.subscriptions (user_id);

CREATE UNIQUE INDEX ix_subscriptions_provider_external_id
    ON core.subscriptions (provider, external_id);

CREATE TABLE core.store_purchase_tokens (
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    provider core.subscription_provider NOT NULL,
    identity_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    UNIQUE (provider, identity_value)
);

CREATE INDEX ix_store_purchase_tokens_user_id ON core.store_purchase_tokens (user_id);

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
    CHECK (resolved_token_value IS NULL OR resolved_token_value = identity_value),
    FOREIGN KEY (provider, external_id)
        REFERENCES core.subscriptions (provider, external_id),
    FOREIGN KEY (provider, resolved_token_value)
        REFERENCES core.store_purchase_tokens (provider, identity_value)
);

CREATE INDEX ix_store_purchases_purchase_user_id
    ON core.store_purchases (purchase_user_id);

CREATE INDEX ix_store_purchases_provider_identity_value
    ON core.store_purchases (provider, identity_value);

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

-- [impl->req~schema-users-access-via-access-grants~1]
CREATE TABLE core.access_grants (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    tier_id TEXT NOT NULL REFERENCES core.access_tiers (id),
    source core.access_grant_source NOT NULL,
    subscription_id UUID,
    status core.access_grant_status NOT NULL DEFAULT 'active',
    starts_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ends_at TIMESTAMPTZ,
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
    CHECK (
        (source = 'subscription' AND subscription_id IS NOT NULL)
        OR
        (source <> 'subscription' AND subscription_id IS NULL)
    ),
    UNIQUE (id, source),
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

CREATE UNIQUE INDEX ix_access_grants_one_per_subscription
    ON core.access_grants (subscription_id)
    WHERE source = 'subscription' AND subscription_id IS NOT NULL AND status = 'active';

CREATE UNIQUE INDEX ix_access_grants_one_active_per_user
    ON core.access_grants (user_id)
    WHERE status = 'active';


CREATE TABLE core.access_grants_anti_abuse (
    grant_id UUID PRIMARY KEY,
    grant_source core.access_grant_source NOT NULL,
    native_claim_provider core.native_claim_provider,
    idp_account_hash BYTEA,
    idp_account_hash_key_version SMALLINT,
    registered_account_grant_id UUID GENERATED ALWAYS AS (
        CASE WHEN grant_source = 'registered_account_grant' THEN grant_id END
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (grant_source IN ('anonymous_device_grant', 'registered_account_grant')),
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

CREATE INDEX ix_access_grants_anti_abuse_idp_account_hash
    ON core.access_grants_anti_abuse (idp_account_hash)
    WHERE idp_account_hash IS NOT NULL;

ALTER TABLE core.access_grants
    ADD FOREIGN KEY (anti_abuse_required_grant_id)
        REFERENCES core.access_grants_anti_abuse (grant_id)
        DEFERRABLE INITIALLY DEFERRED,
    ADD FOREIGN KEY (active_registered_account_grant_id)
        REFERENCES core.access_grants_anti_abuse (registered_account_grant_id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE UNIQUE INDEX ix_access_grants_one_free_grant_per_user_source
    ON core.access_grants (user_id, source)
    WHERE source IN ('anonymous_device_grant', 'registered_account_grant');

CREATE TABLE core.manual_grant_issuances (
    case_id TEXT PRIMARY KEY CHECK (case_id <> ''),
    grant_id UUID NOT NULL UNIQUE REFERENCES core.access_grants (id),
    user_id UUID NOT NULL REFERENCES core.users (id),
    operator TEXT NOT NULL CHECK (operator <> ''),
    reason TEXT NOT NULL CHECK (reason <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TYPE core.gate_consumption_kind AS ENUM ('web_anonymous_gate', 'registered_account_grant');

CREATE TABLE core.provider_accounts (
    id UUID PRIMARY KEY,
    provider core.identity_provider NOT NULL CHECK (provider IN ('google', 'apple')),
    provider_uid TEXT NOT NULL CHECK (provider_uid <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (provider, provider_uid)
);

CREATE TABLE core.provider_account_gate_consumptions (
    provider_account_id UUID NOT NULL REFERENCES core.provider_accounts (id),
    consumption_kind core.gate_consumption_kind NOT NULL,
    grant_id UUID NOT NULL REFERENCES core.access_grants (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider_account_id, consumption_kind)
);

CREATE INDEX ix_gate_consumptions_grant_id
    ON core.provider_account_gate_consumptions (grant_id);

-- [impl->req~schema-users-usage-via-user-monthly-usage~1]
CREATE TABLE core.user_monthly_usage (
    grant_id UUID PRIMARY KEY REFERENCES core.access_grants (id) ON DELETE CASCADE,
    monthly_period TEXT NOT NULL,
    monthly_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (monthly_used >= 0)
);

CREATE TABLE core.auth_challenges (
    id UUID PRIMARY KEY,
    challenge_id TEXT NOT NULL UNIQUE,
    operation core.auth_operation NOT NULL,
    operation_variant core.identity_provider,
    bound_external_identity_id UUID REFERENCES core.external_identities (id),
    preauth_issuer TEXT,
    preauth_subject_hash BYTEA,
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    claim_attempt_id UUID,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (claimed_at IS NULL AND claim_attempt_id IS NULL AND consumed_at IS NULL)
        OR
        (claimed_at IS NOT NULL AND claim_attempt_id IS NOT NULL)
    ),
    CHECK (
        (operation = 'create_user'
            AND operation_variant IS NOT NULL
            AND operation_variant IN ('anonymous', 'google', 'apple'))
        OR
        (operation = 'upgrade_anonymous_to_registered'
            AND operation_variant IS NOT NULL
            AND operation_variant IN ('google', 'apple'))
        OR
        (operation IN ('claim_anonymous_grant', 'claim_registered_grant')
            AND operation_variant IS NULL)
    ),
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


CREATE TABLE audit.auth_events (
    id UUID PRIMARY KEY,
    challenge_row_id UUID,
    operation core.auth_operation,
    result core.auth_event_result NOT NULL,
    actor_issuer TEXT,
    actor_subject_hash BYTEA,
    actor_subject_hash_key_version SMALLINT,
    actor_provider core.identity_provider,
    details JSONB NOT NULL DEFAULT '{"schema_version":1,"context":{},"verification":{},"resolved":{},"mutation":{},"failure":{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (jsonb_typeof(details) = 'object'),
    CHECK (details ? 'schema_version' AND jsonb_typeof(details -> 'schema_version') = 'number'),
    CHECK (details ? 'context' AND jsonb_typeof(details -> 'context') = 'object'),
    CHECK (details ? 'verification' AND jsonb_typeof(details -> 'verification') = 'object'),
    CHECK (details ? 'resolved' AND jsonb_typeof(details -> 'resolved') = 'object'),
    CHECK (details ? 'mutation' AND jsonb_typeof(details -> 'mutation') = 'object'),
    CHECK (details ? 'failure' AND jsonb_typeof(details -> 'failure') = 'object'),
    CHECK (
        (result = 'invalid_external_jwt'
            AND actor_issuer IS NULL
            AND actor_subject_hash IS NULL
            AND actor_subject_hash_key_version IS NULL
            AND actor_provider IS NULL)
        OR
        (result <> 'invalid_external_jwt'
            AND actor_issuer IS NOT NULL
            AND actor_subject_hash IS NOT NULL
            AND actor_subject_hash_key_version IS NOT NULL)
    ),
    CHECK (
        (result = 'succeeded' AND operation IS NOT NULL)
        OR
        (result <> 'succeeded')
    )
);

CREATE INDEX ix_auth_events_challenge_row_id ON audit.auth_events (challenge_row_id);
CREATE INDEX ix_auth_events_result_created_at ON audit.auth_events (result, created_at);
CREATE INDEX ix_auth_events_operation_created_at ON audit.auth_events (operation, created_at);
CREATE INDEX ix_auth_events_actor_issuer_subject_hash ON audit.auth_events (actor_issuer, actor_subject_hash);

-- migrate: rollback

DROP TABLE IF EXISTS audit.auth_events CASCADE;
DROP TABLE IF EXISTS core.auth_challenges CASCADE;
DROP TABLE IF EXISTS core.user_monthly_usage CASCADE;
DROP TABLE IF EXISTS core.provider_account_gate_consumptions CASCADE;
DROP TABLE IF EXISTS core.provider_accounts CASCADE;
DROP TABLE IF EXISTS core.manual_grant_issuances CASCADE;
DROP TABLE IF EXISTS core.access_grants_anti_abuse CASCADE;
DROP TABLE IF EXISTS core.access_grants CASCADE;
DROP TABLE IF EXISTS audit.subscription_events CASCADE;
DROP TABLE IF EXISTS core.store_purchases CASCADE;
DROP TABLE IF EXISTS core.store_purchase_tokens CASCADE;
DROP TABLE IF EXISTS core.subscriptions CASCADE;
DROP TABLE IF EXISTS core.messages CASCADE;
DROP TABLE IF EXISTS core.chats CASCADE;
DROP TABLE IF EXISTS core.access_tiers CASCADE;
DROP TABLE IF EXISTS core.external_identities CASCADE;
DROP TABLE IF EXISTS core.users CASCADE;
DROP TYPE IF EXISTS core.native_claim_provider;
DROP TYPE IF EXISTS core.gate_consumption_kind;
DROP TYPE IF EXISTS core.auth_event_result;
DROP TYPE IF EXISTS core.access_grant_status;
DROP TYPE IF EXISTS core.access_grant_source;
DROP TYPE IF EXISTS core.auth_operation;
DROP TYPE IF EXISTS core.identity_state;
DROP TYPE IF EXISTS core.identity_provider;
DROP TYPE IF EXISTS core.subscription_status;
DROP TYPE IF EXISTS core.subscription_provider;
DROP TYPE IF EXISTS core.chat_role;
DROP SCHEMA IF EXISTS audit;

-- Restore the initial release's objects, so rolling this migration back leaves the database in
-- the state 20260322_01_initial-release applied.
CREATE TYPE core.chat_role AS ENUM ('human', 'ai');
CREATE TYPE core.subscription_plan AS ENUM ('free', 'silver', 'gold', 'platinum');
CREATE TYPE core.subscription_provider AS ENUM ('apple');
CREATE TYPE core.subscription_status AS ENUM ('active', 'grace_period', 'billing_retry', 'expired', 'revoked');

CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    subscription_plan core.subscription_plan NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_users_jwt_sub ON core.users (jwt_sub);

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

CREATE TABLE core.subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id),
    provider core.subscription_provider NOT NULL,
    external_id TEXT NOT NULL,
    plan core.subscription_plan NOT NULL,
    status core.subscription_status NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_subscriptions_user_id ON core.subscriptions (user_id);
CREATE INDEX ix_subscriptions_external_id ON core.subscriptions (external_id);
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON core.subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');

CREATE TABLE core.subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES core.subscriptions (id),
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_plan core.subscription_plan,
    new_plan core.subscription_plan,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_subscription_events_subscription_id ON core.subscription_events (subscription_id);

CREATE TABLE core.usage_monthly (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id),
    month TEXT NOT NULL,
    used INTEGER NOT NULL,
    UNIQUE (user_id, month)
);

CREATE INDEX ix_usage_monthly_user_month ON core.usage_monthly (user_id, month);
