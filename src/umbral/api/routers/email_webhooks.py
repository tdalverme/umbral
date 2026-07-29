"""Private provider webhook ingress with raw-body verification."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, Request, Response

from umbral.api.routers.auth import _check_bff, _deps, _problem
from umbral.application.identity.contracts import IdentityError

router = APIRouter(prefix="/api/v1/integrations/email", tags=["Authentication"])


@router.post(
    "/resend-events",
    operation_id="receiveResendEvent",
    status_code=204,
    response_model=None,
)
async def receive_email_event(
    request: Request,
    x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False),
    x_correlation_id: str | None = Header(default=None),
) -> Response:
    try:
        _check_bff(x_umbral_bff_token)
        _deps().identity_access.process_email_webhook(
            raw_body=await request.body(),
            headers=dict(request.headers),
            now=datetime.now(timezone.utc),
        )
    except IdentityError as error:
        return _problem(error, request)
    return Response(status_code=204)
