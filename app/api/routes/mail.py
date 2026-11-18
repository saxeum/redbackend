"""Mailbox operations.

Administrative surface: the polled mailbox is shared infrastructure, not any
single user's data, so everything here is superuser-only. Polling happens in
`app/poller.py` on a schedule; the POST exists for manual and development use.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ConnDep, CurrentUser
from app.api.errors import api_responses
from app.api.mappers import (
    to_mail_list_response,
    to_mail_message_detail_response,
    to_mail_poll_response,
)
from app.api.schemas import (
    MailListResponse,
    MailMessageDetailResponse,
    MailPollResponse,
)
from app.clients import gmail
from app.domain.errors import ErrorCode
from app.services import mailbox as mailbox_service

router = APIRouter(prefix="/mail", tags=["mail"])


@router.post(
    "/poll",
    response_model=MailPollResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES, ErrorCode.MAIL_NOT_CONFIGURED
    ),
)
def poll_mailbox(
    conn: ConnDep,
    actor: CurrentUser,
    limit: Annotated[
        int, Query(ge=1, le=50, description="messages to list on a full sync")
    ] = 10,
) -> MailPollResponse:
    """Store the mail added since the last cycle."""
    # Authorization first: an unsuperuser must not learn whether mail is
    # configured, and building the client costs a network round-trip.
    mailbox_service.require_superuser(actor)
    result = mailbox_service.poll_new(
        conn=conn, client=gmail.build_client(), limit=limit
    )
    return to_mail_poll_response(result)


@router.get(
    "/messages",
    response_model=MailListResponse,
    responses=api_responses(ErrorCode.INSUFFICIENT_PRIVILEGES),
)
def list_mail_messages(
    conn: ConnDep, actor: CurrentUser, skip: int = 0, limit: int = 50
) -> MailListResponse:
    """List stored mail, newest first."""
    messages, count = mailbox_service.list_messages(
        conn=conn, actor=actor, skip=skip, limit=limit
    )
    return to_mail_list_response(messages, count)


@router.get(
    "/messages/{mail_id}",
    response_model=MailMessageDetailResponse,
    responses=api_responses(
        ErrorCode.INSUFFICIENT_PRIVILEGES, ErrorCode.MAIL_NOT_FOUND
    ),
)
def read_mail_message(
    mail_id: uuid.UUID, conn: ConnDep, actor: CurrentUser
) -> MailMessageDetailResponse:
    """Read one stored message, including its body."""
    return to_mail_message_detail_response(
        mailbox_service.get_message(conn=conn, actor=actor, mail_id=mail_id)
    )
