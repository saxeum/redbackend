"""One-shot mailbox poll, out of band from the API.

    make mail-poll                          # newest 10 messages
    uv run python -m app.poller --limit 25

Scheduled polling belongs in a worker process that runs this same service
function; the API container never polls on its own.
"""

import argparse

from app.clients import gmail
from app.clients.gmail import MailAuthError
from app.core.db import pool
from app.domain.errors import InvalidOperation
from app.services import mailbox as mailbox_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll the configured mailbox once.")
    parser.add_argument("--limit", type=int, default=10, help="messages to list")
    args = parser.parse_args(argv)

    try:
        client = gmail.build_client()
        with pool.connection() as conn:
            result = mailbox_service.poll_new(
                conn=conn, client=client, limit=args.limit
            )
    except InvalidOperation:
        print(
            "cannot poll: set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and "
            "GMAIL_REFRESH_TOKEN in .env (see `make google-refresh-token`)"
        )
        return 2
    except MailAuthError:
        print(
            "cannot poll: Gmail rejected the credentials. The refresh token is "
            "expired (Testing-mode tokens last 7 days) or revoked.\n"
            "Re-run `make google-refresh-token` and update GMAIL_* in .env."
        )
        return 2

    print(
        f"{result.mailbox}: mode={result.mode} listed={result.listed} "
        f"stored={result.stored} skipped={result.skipped} cursor={result.cursor}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
