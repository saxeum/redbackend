-- Incremental polling.
--
-- `cursor` is the provider's opaque position token — Gmail's `historyId`. After
-- a successful cycle it is advanced in the same transaction as the messages it
-- covers, so neither can be lost on a crash.

CREATE TABLE IF NOT EXISTS mailbox_cursor (
    mailbox varchar(320) PRIMARY KEY,
    cursor varchar(255) NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
