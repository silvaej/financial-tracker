from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers import (
    assets,
    cashflow,
    channels,
    credit,
    expenses,
    goals,
    overview,
    payout_periods,
    transfers,
)

app = FastAPI(title="Finance Tracker")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(channels.router)
app.include_router(payout_periods.router)
app.include_router(expenses.router)
app.include_router(transfers.router)
app.include_router(assets.router)
app.include_router(goals.router)
app.include_router(credit.router)
app.include_router(overview.router)
app.include_router(cashflow.router)

PLACEHOLDER_SECTIONS: dict[str, str] = {}


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return overview.index(request, db)


@app.get("/{section}")
def placeholder(request: Request, section: str) -> HTMLResponse:
    title = PLACEHOLDER_SECTIONS.get(section)
    if title is None:
        return templates.TemplateResponse(
            request, "placeholder.html", {"title": "Not found"}, status_code=404
        )
    return templates.TemplateResponse(request, "placeholder.html", {"title": title})
