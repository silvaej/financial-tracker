from fastapi.templating import Jinja2Templates
from starlette.requests import Request


def _current_user_context(request: Request) -> dict[str, object]:
    # get_current_user (app/auth.py) stashes the resolved user on request.state
    # so every template render gets `current_user` (e.g. the rail's avatar)
    # without threading it through each router's own render context. None on
    # login.html/unauthenticated responses, where get_current_user never ran.
    return {"current_user": getattr(request.state, "user", None)}


templates = Jinja2Templates(directory="app/templates", context_processors=[_current_user_context])
