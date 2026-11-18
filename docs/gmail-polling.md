# Testing the Gmail polling integration

A walkthrough from "no Google project" to "rows in `mail_message`, visible over
HTTP". It covers the manual path (CLI and Swagger) and the automated tests you
can run without any credentials.

Phase 1 is **read-only**: the poller lists the inbox, fetches each message and
stores it. It does not label, move, reply to or delete anything, so pointing it
at a real mailbox is safe.

```
make google-refresh-token   ──▶  GMAIL_CLIENT_ID / _SECRET / _REFRESH_TOKEN  ──▶  .env
                                                                                  │
make mail-poll ──▶ app/poller.py ──▶ services.mailbox.poll_new ──▶ repositories.mail
                                             │                            │
                                   clients.gmail (Google API)     mail_message + mailbox_cursor
                                                                          │
POST /api/v1/mail/poll ───────────────────────────────────────────────────┘
GET  /api/v1/mail/messages
```

## Credentials: two different OAuth clients

Do not reuse the sign-in client. The polled mailbox belongs to one admin
account; sign-in authenticates ordinary users. Mixing them means the login
consent screen starts asking for Gmail access.

| Purpose | Env vars | OAuth client type | Scope granted |
|---|---|---|---|
| Sign-in (Google OIDC) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Web application | `openid email profile` |
| Mailbox polling | `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | **Desktop app** | `gmail.modify` |

`gmail.modify` is used even in phase 1 so later phases (labels, replies) do not
need a second consent round. Phase 1 only issues `messages.list` and
`messages.get`.

---

## Part 1 — Google Cloud

Use a dedicated project so the mail client is independent of whatever project
holds your sign-in client.

1. **Enable the API.** Console → APIs & Services → Library → *Gmail API* →
   Enable.

2. **Consent screen.** APIs & Services → OAuth consent screen:
   - User type: **External** (a personal `@gmail.com` mailbox cannot use
     Internal).
   - Publishing status: **Testing** is fine.
   - **Test users**: add the exact address of the mailbox you will poll
     (`kirivanzin@gmail.com`). Without this, the consent screen fails with
     `access_denied`.
   - Scopes: add `https://www.googleapis.com/auth/gmail.modify`.

3. **OAuth client.** Credentials → Create credentials → OAuth client ID →
   **Desktop app**. Download the JSON and save it as `credentials.json` in the
   repository root.

   A *Desktop app* client is required: it accepts loopback redirects
   (`http://localhost:<random port>`) which is what
   `InstalledAppFlow.run_local_server(port=0)` uses. A *Web application*
   client only accepts the exact redirect URIs you registered, so it fails with
   `redirect_uri_mismatch`.

   `credentials.json` is gitignored; keep it that way.

> **Testing-mode caveat:** while the consent screen is in Testing, Google
> expires refresh tokens after **7 days**. Expect to re-run
> `make google-refresh-token` weekly during development. Publishing the app (or
> using a Workspace project) removes that limit.

---

## Part 2 — Mint a refresh token

```bash
make google-refresh-token
```

This opens a browser for consent and prints three lines, already named for the
mailbox client:

```
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
```

Add them to `.env` (not `.env.example`):

```bash
GMAIL_CLIENT_ID=<client id from the output>
GMAIL_CLIENT_SECRET=<client secret from the output>
GMAIL_REFRESH_TOKEN=<refresh token from the output>
```

```bash
chmod 600 .env
```

The refresh token is a live credential: anyone holding it can read that mailbox
until it is revoked. Do not paste it into issues, CI logs or shell history.

Offline / headless? Run the script on a machine with a browser and copy the
values across; consent has to happen in a browser once.

---

## Part 3 — Migrate and restart

```bash
make deps-up           # PostgreSQL
make db-migrate        # applies 0003_mail_messages.sql and 0004_mailbox_cursor.sql
make docker-up         # recreates the API container with the new env
```

The CLI reads `.env` directly, so `make mail-poll` works as soon as migrations
are applied. The API container only sees the variables listed in `compose.yml`;
that is why it needs the restart.

Sanity check the configuration without touching Gmail:

```bash
make mail-poll         # unconfigured → "cannot poll: set GMAIL_CLIENT_ID, ..." (exit 2)
```

---

## Part 4 — Poll

### From the CLI

```bash
make mail-poll
# inbox@example.com: mode=full listed=10 stored=10 skipped=0 cursor=9876543
```

Run it again:

```bash
make mail-poll
# inbox@example.com: mode=incremental listed=0 stored=0 skipped=0 cursor=9876543
```

`mode=full` means "no cursor yet, this is the first sync" (or the cursor was too
old — see below). `mode=incremental` asks Gmail's `history.list` for changes
since `cursor`, so an idle mailbox costs one history call and nothing else.
Messages that arrived between cycles appear as `listed=3 stored=3`, even if
`--limit` is 10 and 50 arrived — the window, not the page size, decides.

When Gmail no longer retains history back to the stored cursor (roughly a week),
the API answers `404`, the poller falls back to `mode=full` and the cycle
automatically rewinds. Nothing to do by hand; a sudden `mode=full` in the logs is
the visible symptom.

### Over HTTP

The mail routes are superuser-only. Get a token with the seeded superuser:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/login/access-token \
  -d 'username=admin@example.com' -d 'password=changethis' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

Use Google sign-in instead if password login is disabled: take the access token
the SPA stores after the `/auth` redirect and send it as the bearer token.

```bash
# Run one cycle
curl -s -X POST "http://localhost:8000/api/v1/mail/poll?limit=5" \
  -H "Authorization: Bearer $TOKEN"
# {"mailbox":"inbox@example.com","mode":"incremental","listed":5,
#  "stored":5,"skipped":0,"cursor":"9877001"}

# List what was stored (no bodies, to keep the response small)
curl -s "http://localhost:8000/api/v1/mail/messages?limit=5" \
  -H "Authorization: Bearer $TOKEN"

# One message with its body
curl -s "http://localhost:8000/api/v1/mail/messages/<id>" \
  -H "Authorization: Bearer $TOKEN"
```

Or open <http://localhost:8000/docs> and use **mail → POST /api/v1/mail/poll**.

Expected failures:

| Response | Meaning |
|---|---|
| `403 {"detail":"The user doesn't have enough privileges"}` | token belongs to a regular user |
| `404 {"detail":"Mail polling is not configured"}` | `GMAIL_*` missing from the container's env — `make docker-up` after editing `.env` |
| `401 {"detail":"Could not validate credentials"}` | token expired or malformed |

---

## Part 5 — Automated tests (no credentials)

Every layer is tested offline; nothing below contacts Google.

```bash
make test-pytest ARGS="tests/clients/test_gmail.py"          # wire format → domain
make test-pytest ARGS="tests/services/test_mailbox.py"       # polling rules, dedupe
make test-pytest ARGS="tests/repositories/test_mail.py"      # SQL against real Postgres
make test-pytest ARGS="tests/api/test_controllers_mail.py"   # HTTP contract
```

`tests/clients/test_gmail.py` replaces the discovery service with a fake that
records calls, so `to_fetched_mail` is exercised against a canned Gmail payload
(multipart parts, base64 bodies, `internalDate`). `tests/services/test_mailbox.py`
uses `FakeMailClient`/`FakeMailRepository` from `tests/fakes.py`.

The HTTP smoke suite (`make e2e`) deliberately does not poll a real mailbox. It
checks `GET /mail/messages` for a superuser and `403` for a regular user, which
proves routing, auth and serialization without side effects.

Note: `make test` / `make test-ci` **wipe** users, items and stored mail in the
configured database. Run `make db-seed` afterwards to restore the superuser, and
re-poll if you were using the data.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `cannot poll: set GMAIL_CLIENT_ID...` (exit 2) | `.env` lacks one of the three values |
| `invalid_grant` / `cannot poll: Gmail rejected the credentials` | Testing-mode 7-day expiry, password change, or access revoked at <https://myaccount.google.com/permissions> → re-run `make google-refresh-token` |
| `redirect_uri_mismatch` during consent | `credentials.json` is a *Web* client; create a *Desktop app* one |
| `Error 403: access_denied` | the mailbox address is not in the consent screen's test users |
| `403 insufficient privileges` over HTTP | not a superuser |
| `404 Mail polling is not configured` | container env missing `GMAIL_*` (restart it) |
| `relation "mail_message" does not exist` | run `make db-migrate` |
| `mode=full` on every run | the cursor table is empty (`make db-migrate`) or Gmail keeps answering 404 for the stored cursor |
| `stored=0 skipped=N` on an incremental run | those messages were already stored (a relabel re-reports them) |
| `listed=0` | inbox is empty, or the account has no messages in `INBOX` |

Inspect or reset the stored data:

```bash
make db-shell
# \d mail_message
# SELECT mailbox, count(*) FROM mail_message GROUP BY 1;
# SELECT * FROM mailbox_cursor;
# DELETE FROM mail_message;          -- start over without touching Gmail
# DELETE FROM mailbox_cursor;        -- force the next cycle to be mode=full
```

---

## Hygiene

- Revoke the token when you are done: <https://myaccount.google.com/permissions>
  → the project → Remove access. Then delete the values from `.env`.
- `credentials.json` and `GMAIL_REFRESH_TOKEN` are secrets. `.env.example` keeps
  `GMAIL_*` empty on purpose — do not fill it in and commit it.
- The consent screen shows a "Google hasn't verified this app" warning. That is
  expected for an unverified Testing app; it is not a sign of a broken setup.

## Not covered yet (phase 3)

Labels (`ai-processed`, `needs-human`), replies, escalation, and mirroring
provider-side deletions. The cursor is in place (`mailbox_cursor`), so the next
phase is the first *writer*, which brings a new failure mode: a message handled
twice if the action succeeds and the label update fails. That is where
`scripts/gmail.py` (the prototype) has useful pieces — `ensure_labels`,
`add_label`, `is_escalated`, `send_reply` — to port into
`app/clients/gmail.py` and `app/services/mailbox.py`.
