-- initial release
-- depends:

-- migrate: apply

CREATE TABLE users (
    id UUID PRIMARY KEY,
    jwt_sub TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    name TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_users_jwt_sub ON users (jwt_sub);

CREATE TABLE chats (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    lang TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_chats_user_id ON chats (user_id);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX ix_subscriptions_external_id ON subscriptions (external_id);
CREATE UNIQUE INDEX ix_subscriptions_user_provider_active
    ON subscriptions (user_id, provider)
    WHERE status NOT IN ('expired', 'revoked');

CREATE TABLE subscription_events (
    id UUID PRIMARY KEY,
    subscription_id UUID NOT NULL REFERENCES subscriptions (id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    notification_uuid TEXT NOT NULL UNIQUE,
    old_tier TEXT,
    new_tier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscription_events_subscription_id ON subscription_events (subscription_id);

-- migrate: rollback

DROP TABLE IF EXISTS subscription_events;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS users;
