-- initial release with users, subscriptions, and usage
-- depends:

-- migrate: apply

CREATE SCHEMA IF NOT EXISTS core;

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

-- migrate: rollback

DROP TABLE IF EXISTS core.subscription_events;
DROP TABLE IF EXISTS core.subscriptions;
DROP TABLE IF EXISTS core.messages;
DROP TABLE IF EXISTS core.chats;
DROP TABLE IF EXISTS core.usage_monthly;
DROP TABLE IF EXISTS core.users;
DROP TYPE IF EXISTS core.subscription_status;
DROP TYPE IF EXISTS core.subscription_provider;
DROP TYPE IF EXISTS core.subscription_plan;
DROP TYPE IF EXISTS core.chat_role;
DROP SCHEMA IF EXISTS core;
