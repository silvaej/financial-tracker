import hmac
import secrets

from fastapi import HTTPException, Request

CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def csrf_protect(request: Request) -> None:
    """Ensures the session has a CSRF token (so templates can embed it) and,
    for state-changing requests, verifies the caller sent that token back
    via the X-CSRF-Token header (set for every htmx/fetch request, see
    base.html) or a csrf_token form field (for plain <form> posts)."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    if request.method in SAFE_METHODS:
        return

    submitted = request.headers.get(CSRF_HEADER)
    if submitted is None and "form" in request.headers.get("content-type", ""):
        value = (await request.form()).get(CSRF_FORM_FIELD)
        submitted = value if isinstance(value, str) else None

    if not submitted or not hmac.compare_digest(token, submitted):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")
