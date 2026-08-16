from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app import crud
from app.config import settings


def _current_user_context(request: Request) -> dict[str, object]:
    # get_current_user (app/auth.py) stashes the resolved user on request.state
    # so every template render gets `current_user` (e.g. the rail's avatar)
    # without threading it through each router's own render context. None on
    # login.html/unauthenticated responses, where get_current_user never ran.
    user = getattr(request.state, "user", None)
    # Exposed globally so base.html can conditionally show the Admin nav
    # item -- see issue #65. Real enforcement is require_admin (app/auth.py)
    # on the actual /admin routes; this is just for hiding the link from
    # users who'd get a 404 anyway.
    is_admin = user is not None and user.email in settings.admin_email_set
    # Exposed globally (rather than threaded through every route's render
    # context) so macros.peso() and every hardcoded currency-prefix span in
    # the templates render in the signed-in user's chosen currency without
    # each call site having to pass it in.
    return {
        "current_user": user,
        "currency_symbol": crud.currency_symbol_for(user),
        "is_admin": is_admin,
    }


templates = Jinja2Templates(directory="app/templates", context_processors=[_current_user_context])
