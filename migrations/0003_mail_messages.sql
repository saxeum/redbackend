-- Polled mail.
--
-- One row per message, deduplicated per mailbox: polling may see the same
-- message again (no server-side cursor yet), so the unique index is what makes
-- a cycle idempotent.

CREATE TABLE IF NOT EXISTS mail_message (
    id uuid PRIMARY KEY,
    mailbox varchar(320) NOT NULL,
    remote_id varchar(255) NOT NULL,
    thread_id varchar(255) NOT NULL,
    from_address varchar(320) NOT NULL,
    subject text,
    snippet text NOT NULL DEFAULT '',
    body text NOT NULL DEFAULT '',
    received_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_mail_message_mailbox_remote_id
    ON mail_message (mailbox, remote_id);

CREATE INDEX IF NOT EXISTS ix_mail_message_received_at
    ON mail_message (received_at DESC);
