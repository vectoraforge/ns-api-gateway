-- add plans and usage tables
-- depends: 20260317_01_bvi4l-initial-release

-- migrate: apply

CREATE TABLE plans (
    tier TEXT PRIMARY KEY,
    monthly_quota INTEGER NOT NULL
);

INSERT INTO plans (tier, monthly_quota) VALUES
    ('free', 150),
    ('silver', 1500),
    ('gold', 3000),
    ('platinum', 30000);

CREATE TABLE usage_monthly (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, month)
);

CREATE INDEX ix_usage_monthly_user_month ON usage_monthly (user_id, month);

-- migrate: rollback

DROP TABLE IF EXISTS usage_monthly;
DROP TABLE IF EXISTS plans;
