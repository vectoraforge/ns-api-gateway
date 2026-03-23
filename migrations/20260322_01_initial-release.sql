-- initial release with plans, users, subscriptions, and usage
-- depends:

-- migrate: apply

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE core.plans (
    tier TEXT PRIMARY KEY,
    monthly_quota INTEGER NOT NULL
);

INSERT INTO core.plans (tier, monthly_quota) VALUES
    ('free', 150),
    ('silver', 1500),
    ('gold', 3000),
    ('platinum', 30000);

CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    plan TEXT NOT NULL DEFAULT 'free' REFERENCES core.plans (tier),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_users_jwt_sub ON core.users (jwt_sub);

CREATE TABLE core.chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_chats_user_id ON core.chats (user_id);

CREATE TABLE core.messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES core.chats (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free' REFERENCES core.plans (tier),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscriptions_user_id ON core.subscriptions (user_id);
CREATE INDEX ix_subscriptions_external_id ON core.subscriptions (external_id);
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON core.subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');

CREATE TABLE core.subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES core.subscriptions (id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier TEXT,
    new_tier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscription_events_subscription_id ON core.subscription_events (subscription_id);

CREATE TABLE core.usage_monthly (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES core.users (id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
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
DROP TABLE IF EXISTS core.plans;
