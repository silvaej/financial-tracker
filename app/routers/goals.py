from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/goals", tags=["goals"])
templates = Jinja2Templates(directory="app/templates")


def _render_page(request: Request, db: Session, user_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "partials/goals_page.html", crud.goals_page_data(db, user_id)
    )


def _parse_channel_id(raw: str) -> int | None:
    return int(raw) if raw else None


@router.get("")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    template = "partials/goals_page.html" if request.headers.get("HX-Request") else "goals.html"
    return templates.TemplateResponse(request, template, crud.goals_page_data(db, current_user.id))


@router.post("")
def create_goal(
    request: Request,
    name: str = Form(...),
    target: float = Form(...),
    allocated: float = Form(0),
    months: int = Form(1),
    channel_id: str = Form(""),
    round_up_to_hundred: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.create_goal(
            db,
            schemas.GoalCreate(
                name=name,
                target=target,
                allocated=allocated,
                months=months,
                channel_id=_parse_channel_id(channel_id),
                round_up_to_hundred=round_up_to_hundred,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.patch("/{goal_id}")
def update_goal(
    request: Request,
    goal_id: int,
    name: str = Form(...),
    target: float = Form(...),
    allocated: float = Form(...),
    months: int = Form(...),
    channel_id: str = Form(""),
    round_up_to_hundred: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    try:
        crud.update_goal(
            db,
            goal_id,
            schemas.GoalUpdate(
                name=name,
                target=target,
                allocated=allocated,
                months=months,
                channel_id=_parse_channel_id(channel_id),
                round_up_to_hundred=round_up_to_hundred,
            ),
            current_user.id,
        )
    except crud.OwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _render_page(request, db, current_user.id)


@router.delete("/{goal_id}")
def delete_goal(
    request: Request,
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> HTMLResponse:
    crud.delete_goal(db, goal_id, current_user.id)
    return _render_page(request, db, current_user.id)
