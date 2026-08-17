from typing import Any

from authlib.integrations.starlette_client import OAuth

from app.config import settings

oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="github",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_id=settings.github_client_id,
    client_secret=settings.github_client_secret,
    client_kwargs={"scope": "read:user user:email"},
)

# Origins /auth/{provider}/start 302s the browser to when a login begins.
# These MUST appear in the CSP's form-action directive (app/main.py) or Chrome
# blocks the entire login: it enforces form-action against every hop of a
# redirect chain, not just the form's initial target (Firefox doesn't -- a
# long-standing cross-browser difference), and login.html's provider buttons
# submit a real <form> to /auth/{provider}/start, which then redirects here.
# Chrome reports such a violation against the *original* same-origin form
# target, not the redirect that actually tripped it, which makes it read like
# 'self' is rejecting a same-origin URL. See issue #129.
#
# Keep in sync with the register() calls above when adding a provider.
OAUTH_REDIRECT_ORIGINS = (
    # google's authorization_endpoint, resolved via the OIDC discovery doc above
    "https://accounts.google.com",
    # github's authorize_url above
    "https://github.com",
)


async def fetch_identity(
    provider: str, client: Any, token: dict[str, Any]
) -> tuple[str, str | None]:
    """Returns (provider_user_id, verified_email) for a just-exchanged OAuth
    token. `email` is None if the provider has no verified email on file --
    callers should treat that as a hard failure, not a missing-but-ok field."""
    if provider == "google":
        userinfo = token.get("userinfo") or {}
        provider_user_id = str(userinfo["sub"])
        email = userinfo.get("email") if userinfo.get("email_verified") else None
        return provider_user_id, email

    # GitHub isn't OIDC -- no id token/userinfo. Fetch the profile for the
    # numeric id, then the emails list for a verified primary address (the
    # profile's own `email` field is often null unless it's public).
    profile_resp = await client.get("user", token=token)
    profile = profile_resp.json()
    provider_user_id = str(profile["id"])

    emails_resp = await client.get("user/emails", token=token)
    emails = emails_resp.json()
    email = next(
        (e["email"] for e in emails if e.get("primary") and e.get("verified")),
        None,
    )
    return provider_user_id, email
