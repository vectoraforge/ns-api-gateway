CREATE EXTENSION IF NOT EXISTS pg_partman;

CREATE TABLE chats (
    id         UUID PRIMARY KEY,
    lang       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id         BIGSERIAL NOT NULL,
    chat_id    UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('human', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_messages_chat_created ON messages (chat_id, created_at);

SELECT partman.create_parent(
    p_parent_table := 'public.messages',
    p_control := 'created_at',
    p_type := 'native',
    p_interval := 'daily'
);

UPDATE partman.part_config
SET retention = '30 days',
    retention_keep_table = false,
    retention_keep_index = false
WHERE parent_table = 'public.messages';
