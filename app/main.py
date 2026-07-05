from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.routers import channels, expenses, payout_periods, transfers

app = FastAPI(title="Finance Tracker")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(channels.router)
app.include_router(payout_periods.router)
app.include_router(expenses.router)
app.include_router(transfers.router)

PLACEHOLDER_SECTIONS = {
    "overview": "Overview",
    "goals": "Goals",
    "credit": "Credit",
    "assets": "Assets",
}


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(request, "expenses.html", crud.expenses_page_data(db))


@app.get("/{section}")
def placeholder(request: Request, section: str) -> HTMLResponse:
    title = PLACEHOLDER_SECTIONS.get(section)
    if title is None:
        return templates.TemplateResponse(
            request, "placeholder.html", {"title": "Not found"}, status_code=404
        )
    return templates.TemplateResponse(request, "placeholder.html", {"title": title})
