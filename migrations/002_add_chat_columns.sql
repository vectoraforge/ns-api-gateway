-- Add phrase, comment, lang columns to chats table
ALTER TABLE chats ADD COLUMN phrase TEXT;
ALTER TABLE chats ADD COLUMN comment TEXT;
ALTER TABLE chats ADD COLUMN lang TEXT;

-- Backfill existing rows with empty phrase (required NOT NULL)
UPDATE chats SET phrase = '' WHERE phrase IS NULL;
ALTER TABLE chats ALTER COLUMN phrase SET NOT NULL;

-- Update role CHECK constraint: 'assistant' -> 'ai'
ALTER TABLE messages DROP CONSTRAINT messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check CHECK (role IN ('human', 'ai'));

-- Update existing 'assistant' rows to 'ai'
UPDATE messages SET role = 'ai' WHERE role = 'assistant';
