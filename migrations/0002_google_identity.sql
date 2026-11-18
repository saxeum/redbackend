-- Google OIDC sign-in.
--
-- `google_sub` is Google's stable subject claim, the only identifier we trust
-- across email changes. It is nullable: password accounts have no Google
-- identity until they sign in with Google once (which links them).
--
-- `hashed_password` becomes nullable because an account created through Google
-- has no local password.
--
-- Idempotent: safe to re-run against a database that already has the column.

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS google_sub varchar;

ALTER TABLE "user" ALTER COLUMN hashed_password DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_user_google_sub
    ON "user" (google_sub)
    WHERE google_sub IS NOT NULL;
