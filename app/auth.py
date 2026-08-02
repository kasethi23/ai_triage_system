"""Bearer-token auth for the JSON API and SSE stream.

Applied to /calls*, /devices*, and the SSE stream. Twilio webhooks (/voice/*)
are intentionally NOT covered here — they authenticate via request-signature
validation instead (see app/routes/voice.py).

Policy:
  - If API_BEARER_TOKEN is set, require `Authorization: Bearer <token>`.
    EventSource clients (SSE) cannot set headers, so a `?token=` query
    parameter is accepted as an equivalent fallback.
  - If API_BEARER_TOKEN is unset: allow in local dev (with a loud warning),
    but hard-fail in production (RAILWAY_ENVIRONMENT present).
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

logger = logging.getLogger(__name__)

# auto_error=False so we can fall back to the query param and to dev-mode allow.
_bearer_scheme = HTTPBearer(auto_error=False)

_warned_no_token = False


def _warn_once() -> None:
    global _warned_no_token
    if not _warned_no_token:
        logger.warning(
            "API_BEARER_TOKEN is not set — API auth is DISABLED. "
            "This is allowed for local dev only; set API_BEARER_TOKEN in production."
        )
        _warned_no_token = True


async def require_bearer(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    expected = config.API_BEARER_TOKEN

    if not expected:
        if config.IS_PRODUCTION:
            # Never run unauthenticated in production.
            logger.error("API_BEARER_TOKEN unset in production — refusing request.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server auth is misconfigured.",
            )
        _warn_once()
        return

    presented = None
    if credentials and credentials.scheme.lower() == "bearer":
        presented = credentials.credentials
    else:
        # SSE / EventSource fallback: EventSource cannot set headers.
        presented = request.query_params.get("token")

    if presented != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
